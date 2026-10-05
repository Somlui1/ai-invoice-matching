"""Production AI services (Qwen on GB300 via LiteLLM) implementing the domain ports."""
from __future__ import annotations

import json

from ...domain.standard import load_prompt
from .litellm_client import LiteLLMClient


class LiteLLMLineMatcher:
    def __init__(self, client: LiteLLMClient, model: str):
        self.c, self.model, self.system = client, model, load_prompt("v07_match")

    def propose(self, invoice_lines, receipt_lines):
        user = json.dumps({"INVOICE_LINES": invoice_lines, "RECEIPT_LINES": receipt_lines}, ensure_ascii=False)
        return self.c.chat_json(self.model, self.system, user, enable_thinking=True)


class LiteLLMQtyJudge:
    def __init__(self, client: LiteLLMClient, model: str):
        self.c, self.model, self.system = client, model, load_prompt("v08_qty")

    def judge(self, payload):
        return self.c.chat_json(self.model, self.system, json.dumps(payload, ensure_ascii=False),
                                temperature=0.0, enable_thinking=True)


class LiteLLMEntityJudge:
    def __init__(self, client: LiteLLMClient, model: str):
        self.c, self.model, self.system = client, model, load_prompt("v05_entity")

    def name_equivalent(self, invoice_name, candidates):
        r = self.c.chat_json(self.model, self.system, json.dumps(
            {"task": "name", "INVOICE_NAME": invoice_name, "CANDIDATES": candidates}, ensure_ascii=False))
        return r.get("name", r)

    def parse_address(self, address):
        r = self.c.chat_json(self.model, self.system, json.dumps(
            {"task": "address", "INVOICE_ADDRESS": address}, ensure_ascii=False))
        return r.get("address", r)
