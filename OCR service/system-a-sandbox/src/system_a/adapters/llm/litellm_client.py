"""LiteLLM (OpenAI-compatible) client — ported from legacy ``ai_verifier`` resilience:
typed errors, JSON salvage, one repair attempt, separate transport/decode budgets, in-flight semaphore.
"""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Optional

USAGE_KEYS = ("calls", "prompt_tokens", "completion_tokens", "reasoning_tokens", "ms", "call_ms",
              "transport_errors", "decode_errors", "decode_salvaged", "no_thinking_retries")
CALL_MS_SAMPLES = 20000        # cap so a 100-document run cannot grow memory without bound
SALVAGE_CUTS = 60              # how many closing positions to try when a body is cut mid-JSON

import httpx

from ...domain.contracts import AIServiceError

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.I)
_THINK = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.S | re.I)
REPAIR = ("ข้อความก่อนหน้าไม่ใช่ JSON ที่ถูกต้อง โปรดตอบใหม่เป็น JSON Object ล้วน เริ่มที่ { และจบที่ } "
          "ห้ามมี markdown หรือข้อความอื่น")


def extract_json_object(text: Any) -> dict:
    if isinstance(text, dict):
        return text
    s = _FENCE.sub("", _THINK.sub("", str(text or ""))).strip()
    start = s.find("{")
    if start < 0:
        raise ValueError("no JSON object")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(re.sub(r",\s*([}\]])", r"\1", s[start:i + 1]))
    raise ValueError("truncated JSON object")


def salvage_json_object(text: Any) -> Optional[dict]:
    """Recover the complete members of a JSON object whose body was cut off (finish_reason=length).

    Only ever returns a prefix of what the model actually printed — nothing is invented — and the caller
    uses it solely where the alternative is losing the whole answer.  Measured need: 21 of 99 baseline
    documents had a page whose page_items answer stopped mid-JSON because reasoning_tokens ate the
    max_tokens budget (e.g. 2 577 reasoning tokens of an 8 000-token completion), which turned
    ``pages_complete`` false and produced E01 on otherwise readable invoices.
    """
    s = _FENCE.sub("", _THINK.sub("", str(text or ""))).strip()
    start = s.find("{")
    if start < 0:
        return None
    fragment, cut = s[start:], len(s[start:])
    closers = {"{": "}", "[": "]"}
    for _ in range(SALVAGE_CUTS):
        pos = fragment.rfind("}", 0, cut)
        if pos < 0:
            return None
        cand, stack, in_str, esc = fragment[:pos + 1], [], False, False
        for ch in cand:
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch in closers:
                stack.append(closers[ch])
            elif ch in "}]":
                if stack and stack[-1] == ch:
                    stack.pop()
        if not in_str:
            cand = re.sub(r",\s*$", "", cand.rstrip().rstrip(","))
            try:
                return json.loads(cand + "".join(reversed(stack)))
            except ValueError:
                pass
        cut = pos
    return None


class LiteLLMClient:
    def __init__(self, base_url: str, api_key: str, *, timeout_s: float = 120, transport_retries: int = 2,
                 max_inflight: int = 6):
        self.base_url, self.api_key, self.timeout = base_url.rstrip("/"), api_key, timeout_s
        self.retries = transport_retries
        self._sem = threading.BoundedSemaphore(max_inflight)
        self._lock = threading.Lock()
        # measured usage, reported in runs/<run_id>/summary.json (AC: LLM call budget)
        self.stats: dict[str, float] = {k: 0 for k in USAGE_KEYS}
        self.stats["call_ms"] = []                                 # per-call latency samples (p95 reporting)
        self.last_usage: dict[str, int] = {}
        self.last_salvaged = False          # True when the answer had to be rescued from a truncated body

    def chat_json(self, model: str, system: str, user: str, *, temperature: float = 0.0,
                  enable_thinking: Optional[bool] = None, images: list[str] | None = None,
                  max_tokens: Optional[int] = None, json_mode: bool = True, layout: str = "system") -> dict:
        if images and layout == "v3":
            # bbox_testv3 layout: ONE user message, image(s) first, then the prompt text; no system message
            text = "\n\n".join(t for t in (system, user) if t)
            messages = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": u}} for u in images]
                         + [{"type": "text", "text": text}]}]
        else:
            content: Any = user if not images else (
                [{"type": "text", "text": user}] + [{"type": "image_url", "image_url": {"url": u}} for u in images])
            messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        self.last_salvaged = False
        body: dict = {"model": model, "messages": messages, "temperature": temperature}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if max_tokens:
            body["max_tokens"] = max_tokens
        if enable_thinking is not None:
            body["chat_template_kwargs"] = {"enable_thinking": enable_thinking}
        text = self._post(body)
        try:
            return extract_json_object(text)
        except ValueError:
            with self._lock:
                self.stats["decode_errors"] += 1
            body["messages"] = messages + [{"role": "assistant", "content": str(text)[:4000]},
                                           {"role": "user", "content": REPAIR}]
            try:
                return extract_json_object(self._post(body))
            except ValueError as first_error:
                # Last two recoveries, both of which keep the answer the model really produced:
                # (1) ask again with reasoning switched off — a page read is a transcription task, and the
                #     thinking tokens are what overflowed max_tokens in the first place;
                # (2) parse whatever members of the (still truncated) body are complete.
                # Measured on the 99-document baseline: 22 pages failed as "no JSON object" (18) or
                # "truncated JSON object" (4) — all of them with reasoning enabled.
                with self._lock:
                    self.stats["no_thinking_retries"] += 1
                body["chat_template_kwargs"] = {"enable_thinking": False}
                bodies: list[Any] = [text]
                try:
                    retry = self._post(body)
                    bodies.append(retry)
                    return extract_json_object(retry)
                except (ValueError, AIServiceError):
                    pass
                for candidate in bodies:
                    salvaged = salvage_json_object(candidate)
                    if salvaged is not None:
                        with self._lock:
                            self.stats["decode_salvaged"] += 1
                        self.last_salvaged = True         # caller keeps the page flagged as not fully read
                        return salvaged
                raise AIServiceError(f"AIResponseError: {first_error}") from first_error

    def _post(self, body: dict) -> str:
        last = None
        for attempt in range(self.retries + 1):
            t0 = time.time()
            try:
                with self._sem, httpx.Client(timeout=self.timeout) as c:
                    r = c.post(f"{self.base_url}/chat/completions", json=body,
                               headers={"Authorization": f"Bearer {self.api_key}"})
                if 400 <= r.status_code < 500:
                    raise AIServiceError(f"AIBadRequestError: HTTP {r.status_code} {r.text[:300]}")
                r.raise_for_status()
                payload = r.json()
                elapsed = (time.time() - t0) * 1000
                usage = payload.get("usage") or {}
                details = usage.get("output_tokens_details") or {}
                with self._lock:
                    self.stats["calls"] += 1
                    self.stats["ms"] += elapsed
                    if len(self.stats["call_ms"]) < CALL_MS_SAMPLES:     # for p95 latency in run reports
                        self.stats["call_ms"].append(round(elapsed, 1))
                    self.stats["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
                    self.stats["completion_tokens"] += int(usage.get("completion_tokens") or 0)
                    self.stats["reasoning_tokens"] += int(details.get("reasoning_tokens") or 0)
                self.last_usage = {k: int(v) for k, v in usage.items() if isinstance(v, int)}
                return payload["choices"][0]["message"]["content"]
            except AIServiceError:
                raise
            except Exception as e:  # transport
                last = f"{type(e).__name__}: {str(e) or 'no detail'}"
                with self._lock:
                    self.stats["transport_errors"] += 1
                if attempt < self.retries:
                    time.sleep(min(8, 2 ** attempt))
        raise AIServiceError(f"AITransportError: {last}")
