#!/usr/bin/env python3
"""AIVA System A — Single Document Pipeline (PDF -> Result 3.0)

Usage:
    python process_pdf.py <path/to/invoice.pdf>
    python process_pdf.py <path/to/invoice.pdf> --output result.json
    python process_pdf.py <path/to/invoice.pdf> --json-only
    python process_pdf.py <path/to/invoice.pdf> --mode sandbox

This is the primary standalone entrypoint for System A:
1. Takes a single PDF invoice
2. Extracts fields, tables, lines, and bounding boxes via Qwen Vision
3. Verifies against Oracle EBS receipts (RCV-V01 / RCV-V02)
4. Evaluates matching rules V-01 .. V-09
5. Produces the final aiva.system_a.result/3.0 payload with recommendation
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import replace
from pathlib import Path

# Ensure stdout uses UTF-8 on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Ensure 'src' is in python search path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from system_a.envfile import load_env
load_env()

from system_a.container import Settings, build_perception, build_services, perception_options
from system_a.application.orchestrator import validate
from system_a.perception.pdf_ingest import is_pdf, pdf_from_image
from system_a.perception.cache import PerceptionCache, cache_key


def format_currency(val) -> str:
    if val is None:
        return "-"
    try:
        return f"{float(val):,.2f}"
    except (ValueError, TypeError):
        return str(val)


def print_summary(res: dict, pdf_path: Path, elapsed_s: float) -> None:
    rec = res.get("recommendation", {})
    rec_val = rec.get("value", "UNKNOWN")
    rec_badge = {
        "AUTO_PASS": "\033[92m[ AUTO_PASS ]\033[0m",
        "REVIEW": "\033[93m[ REVIEW ]\033[0m",
        "HOLD": "\033[91m[ HOLD ]\033[0m",
        "MANUAL_REVIEW": "\033[95m[ MANUAL_REVIEW ]\033[0m",
        "SYSTEM_ERROR": "\033[41m[ SYSTEM_ERROR ]\033[0m",
    }.get(rec_val, f"[{rec_val}]")

    fields = res.get("normalized_fields") or {}
    oracle = res.get("oracle_snapshot") or {}
    matching = res.get("line_matching") or {}
    exceptions = res.get("exceptions") or []

    print("\n" + "=" * 70)
    print("           AIVA System A — Document Verification Result")
    print("=" * 70)
    print(f"File:            {pdf_path.name} ({elapsed_s:.1f} s)")
    print(f"Validation ID:   {res.get('request', {}).get('validation_id', '-')}")
    print(f"Recommendation:  {rec_badge} (Max Severity: {rec.get('max_severity', '-')})")
    if rec.get("reasons"):
        print(f"Reason:          {'; '.join(rec.get('reasons', []))}")

    print("\n--- Header Fields ---")
    print(f"Invoice No:      {fields.get('invoice_num') or '-'}")
    print(f"Invoice Date:    {fields.get('invoice_date') or '-'}")
    print(f"PO Number:       {fields.get('po_number') or '-'}")
    print(f"Supplier:        {fields.get('supplier_name') or '-'} (Tax ID: {fields.get('supplier_tax_id') or '-'})")
    print(f"Customer:        {fields.get('customer_name') or '-'} (Tax ID: {fields.get('customer_tax_id') or '-'})")
    print(f"Subtotal:        {format_currency(fields.get('sub_total'))} {fields.get('currency') or 'THB'}")
    print(f"VAT (7%):        {format_currency(fields.get('vat'))} {fields.get('currency') or 'THB'}")
    print(f"Grand Total:     {format_currency(fields.get('grand_total'))} {fields.get('currency') or 'THB'}")

    print("\n--- Oracle EBS Verification ---")
    if oracle.get("queried"):
        print(f"Lookup Path:     {oracle.get('lookup_path', '-')}")
        print(f"Receipt Num(s):  {', '.join(oracle.get('receipt_nums', [])) or '-'}")
        print(f"Receipt Lines:   {len(oracle.get('receipt_lines', []))} line(s) retrieved")
        print(f"Matched Groups:  {len(matching.get('groups', []))} group(s)")
    else:
        print("Lookup:          Not queried (insufficient keys or skipped)")

    print("\n--- Exceptions / Findings ---")
    if exceptions:
        for exc in exceptions:
            code = exc.get("code", "-")
            sev = exc.get("severity", "-")
            msg = exc.get("message_th") or exc.get("message_en") or "-"
            print(f"  • [{sev}] {code}: {msg}")
    else:
        print("  • No exceptions recorded. All rules passed.")

    print("=" * 70 + "\n")


def process_pdf(
    pdf_path: Path | None = None,
    dms_id: int | None = None,
    output_path: Path | None = None,
    mode: str = "production",
    quick: bool = False,
    json_only: bool = False,
    quiet: bool = False,
) -> dict:
    t0 = time.time()
    load_env()

    # Build settings
    settings = Settings()
    if mode == "production":
        settings = replace(settings, mode="production", ai_mode="litellm")
    else:
        settings = replace(settings, mode="sandbox", ai_mode="sim")

    if quick:
        settings = replace(settings, do_crops=False, do_table=False)

    if pdf_path is None and dms_id is not None:
        cache_dir = ROOT / ".cache" / "downloads"
        cache_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = cache_dir / f"DMS-{dms_id}.pdf"
        if not pdf_path.exists():
            if not json_only and not quiet:
                print(f"Fetching DMS-{dms_id} from Paperless-ngx ({settings.paperless_url})...")
            from system_a.container import build_paperless
            reader = build_paperless(settings)
            doc_bytes = reader.download(dms_id)
            pdf_path.write_bytes(doc_bytes)

    if pdf_path is None:
        raise ValueError("Either a pdf path or --dms-id must be provided")

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    data = pdf_path.read_bytes()
    pdf_bytes = data if is_pdf(data) else pdf_from_image(data)
    if not pdf_bytes:
        raise ValueError(f"Cannot read file as PDF or supported image: {pdf_path}")

    if not json_only and not quiet:
        print(f"Processing '{pdf_path.name}' ({len(pdf_bytes):,} bytes, mode={mode})...")

    # 1. Perception
    if not json_only and not quiet:
        print(" [1/3] Running Perception (OCR + Layout + BBoxes)...")
    pipe = build_perception(settings)
    doc_id = pdf_path.stem

    import hashlib
    sha = "sha256:" + hashlib.sha256(pdf_bytes).hexdigest()
    cache = PerceptionCache(settings.perception_cache)
    opts = dict(perception_options(settings))
    opts["pipeline"] = pipe.code_version
    key = cache_key(file_sha256=sha, model=settings.model_vision, prompt_version=pipe.prompt_version, options=opts)
    ext = cache.load(key, sha)
    if ext is None:
        ext = pipe.extract(pdf_bytes, package_id=f"PKG-{doc_id}", dms_doc_id=doc_id)
        cache.save(key, ext)
    elif not json_only and not quiet:
        print("       (Reusing cached OCR perception result)")

    # 2. Services & Validation
    if not json_only and not quiet:
        print(" [2/3] Querying Oracle EBS & Evaluating Rules V-01..V-09...")
    svc = build_services(settings)

    request = {
        "validation_id": f"VAL-{doc_id}-{int(time.time())}",
        "correlation_id": str(uuid.uuid4()),
        "idempotency_key": None,
        "document_revision": 1,
        "validation_round": 1,
        "source": "cli_process_pdf",
        "run_id": "single",
        "dms_doc_id": doc_id,
        "content_kind": "pdf" if is_pdf(data) else "image",
        "declared_mime": "application/pdf" if is_pdf(data) else "image",
    }

    # 3. Assemble Final Result
    if not json_only and not quiet:
        print(" [3/3] Assembling final recommendation...")
    result = validate(ext, svc, request=request)
    elapsed = time.time() - t0

    # Output handling
    if json_only:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif not quiet:
        print_summary(result, pdf_path, elapsed)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if not json_only and not quiet:
            print(f"Result written to: {output_path.resolve()}\n")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AIVA System A — Process a single PDF and produce the final result 3.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("pdf", nargs="?", type=Path, default=None, help="Path to input invoice PDF or image file")
    parser.add_argument("--dms-id", type=int, default=None, help="Fetch document directly from Paperless-ngx by doc ID")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Save final result JSON to this path")
    parser.add_argument(
        "--mode",
        choices=["production", "sandbox"],
        default="production",
        help="Execution mode (production=real Oracle+Qwen; sandbox=simulators)",
    )
    parser.add_argument("--quick", action="store_true", help="Skip detail crops/tables for faster dry-run")
    parser.add_argument("--json-only", action="store_true", help="Output only the final JSON to stdout")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress all stdout printing except errors")

    args = parser.parse_args()

    if args.pdf is None and args.dms_id is None:
        parser.error("Either a PDF file path or --dms-id must be specified.")

    try:
        process_pdf(
            pdf_path=args.pdf,
            dms_id=args.dms_id,
            output_path=args.output,
            mode=args.mode,
            quick=args.quick,
            json_only=args.json_only,
            quiet=args.quiet,
        )
        return 0
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
