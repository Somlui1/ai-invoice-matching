#!/usr/bin/env python3
"""Batch testing script for System A Core against Paperless-ngx documents tagged 'invoice'.

Features:
- Queries Paperless-ngx API for all documents tagged 'invoice' (or custom tag).
- Downloads each document and executes System A verification pipeline (VisionPipeline + Oracle EBS + Rules V-01..V-09).
- Saves full final result for every case as JSON (<out_dir>/DMS-<id>_result.json).
- Generates a consolidated summary JSON (<out_dir>/summary.json) and console summary table.
- Supports resuming with --skip-existing, limiting test count with --limit, and execution modes (--mode production|sandbox).

Usage:
    python scripts/test_paperless_invoices.py
    python scripts/test_paperless_invoices.py --mode sandbox --limit 5
    python scripts/test_paperless_invoices.py --tag invoice --out-dir results/my_batch
    python scripts/test_paperless_invoices.py --doc-id 20
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure stdout uses UTF-8 on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Ensure 'src' is in python search path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from system_a.envfile import load_env
load_env()

from system_a.container import Settings, build_paperless
from process_pdf import process_pdf


def format_currency(val: Any) -> str:
    if val is None:
        return "-"
    try:
        return f"{float(val):,.2f}"
    except (ValueError, TypeError):
        return str(val)


def print_banner(text: str) -> None:
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80)


def run_batch(
    tag_name: str = "invoice",
    mode: str = "production",
    out_dir: Path = Path("results/paperless_invoices"),
    limit: Optional[int] = None,
    skip_existing: bool = False,
    quick: bool = False,
    specific_doc_id: Optional[int] = None,
) -> int:
    t_start = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    load_env()
    settings = Settings()

    print_banner(f"AIVA System A — Batch Invoice Verification against Paperless-ngx")
    print(f"Time:        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Paperless:   {settings.paperless_url or 'N/A'}")
    print(f"Mode:        {mode}")
    print(f"Tag filter:  '{tag_name}'")
    print(f"Output dir:  {out_dir.resolve()}")
    if limit:
        print(f"Limit:       {limit} documents")
    if quick:
        print(f"Flags:       --quick (skip heavy detail crops)")

    # 1. Connect to Paperless and resolve tag
    try:
        reader = build_paperless(settings)
    except Exception as e:
        print(f"\n[ERROR] Cannot connect to Paperless: {e}", file=sys.stderr)
        return 1

    if specific_doc_id is not None:
        print(f"\nTargeting specific Document ID: DMS-{specific_doc_id}")
        target_docs = [{"id": specific_doc_id, "title": f"DMS-{specific_doc_id}"}]
    else:
        print(f"\n[1/3] Resolving tag '{tag_name}' in Paperless-ngx...")
        try:
            matched_tags = reader.tag_ids_for([tag_name], mode="contains")
        except Exception as e:
            print(f"[ERROR] Failed to query tags: {e}", file=sys.stderr)
            return 1

        if not matched_tags:
            all_tags = [t.get("name") for t in reader.tags()]
            print(f"[ERROR] No tag matching '{tag_name}' found. Available tags: {all_tags}", file=sys.stderr)
            return 1

        tag_ids = [t[0] for t in matched_tags]
        tag_labels = [f"#{t[0]} '{t[1]}'" for t in matched_tags]
        print(f"       Found tags: {', '.join(tag_labels)}")

        print(f"\n[2/3] Fetching document list with tag '{tag_name}'...")
        try:
            doc_rows = reader.list_documents(tag_ids=tag_ids, limit=limit)
        except Exception as e:
            print(f"[ERROR] Failed to list documents: {e}", file=sys.stderr)
            return 1

        target_docs = [{"id": d.doc_id, "title": d.title or d.file_name or f"DMS-{d.doc_id}", "doc": d} for d in doc_rows]

    total_count = len(target_docs)
    print(f"       Discovered {total_count} document(s) to verify.")

    if total_count == 0:
        print("No documents found matching criteria. Exiting.")
        return 0

    # 2. Process documents
    print_banner(f"[3/3] Executing Verification for {total_count} document(s)")
    cases: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {
        "AUTO_PASS": 0,
        "REVIEW": 0,
        "HOLD": 0,
        "MANUAL_REVIEW": 0,
        "SYSTEM_ERROR": 0,
        "SKIPPED": 0,
        "FAILED": 0,
    }
    rules_counter: Dict[str, Dict[str, int]] = {}

    for idx, item in enumerate(target_docs, start=1):
        doc_id = item["id"]
        doc_title = item.get("title", f"DMS-{doc_id}")
        out_file = out_dir / f"DMS-{doc_id}_result.json"

        print(f"[{idx:3d}/{total_count:3d}] DMS-{doc_id:<5d} | {doc_title[:38]:<38}", end=" | ", flush=True)

        if skip_existing and out_file.exists():
            try:
                cached_res = json.loads(out_file.read_text(encoding="utf-8"))
                rec = (cached_res.get("recommendation") or {}).get("value", "UNKNOWN")
                print(f"[SKIPPED] Reusing existing {out_file.name} ({rec})")
                counts["SKIPPED"] += 1
                counts[rec] = counts.get(rec, 0) + 1
                cases.append({
                    "doc_id": doc_id,
                    "title": doc_title,
                    "recommendation": rec,
                    "max_severity": (cached_res.get("recommendation") or {}).get("max_severity"),
                    "output_file": str(out_file.name),
                    "skipped": True,
                })
                continue
            except Exception:
                pass  # Re-run if existing file is damaged

        t_doc_start = time.time()
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = process_pdf(
                    dms_id=doc_id,
                    output_path=out_file,
                    mode=mode,
                    quick=quick,
                    json_only=False,
                )
            elapsed = time.time() - t_doc_start
            rec = (result.get("recommendation") or {}).get("value", "UNKNOWN")
            max_sev = (result.get("recommendation") or {}).get("max_severity", "-")
            exc_codes = (result.get("recommendation") or {}).get("exception_codes") or []
            fields = result.get("normalized_fields") or {}
            inv_num = fields.get("invoice_num") or "-"
            total_val = format_currency(fields.get("grand_total"))
            curr = fields.get("currency") or "THB"

            # Count recommendation
            counts[rec] = counts.get(rec, 0) + 1

            # Count rules
            for r in result.get("rule_results") or []:
                rid = r.get("rule_id", "UNKNOWN")
                rres = r.get("result", "unknown")
                if rid not in rules_counter:
                    rules_counter[rid] = {"pass": 0, "fail": 0, "manual_review": 0, "not_evaluated": 0}
                rules_counter[rid][rres] = rules_counter[rid].get(rres, 0) + 1

            # Colored tag for terminal
            color_tag = {
                "AUTO_PASS": "\033[92mAUTO_PASS\033[0m",
                "REVIEW": "\033[93mREVIEW\033[0m",
                "HOLD": "\033[91mHOLD\033[0m",
                "MANUAL_REVIEW": "\033[95mMANUAL_REVIEW\033[0m",
                "SYSTEM_ERROR": "\033[41mSYSTEM_ERROR\033[0m",
            }.get(rec, rec)

            exc_str = f"({','.join(exc_codes)})" if exc_codes else ""
            print(f"-> {color_tag:<18} {max_sev:<6} {inv_num:<14} {total_val:>12} {curr} ({elapsed:.1f}s) {exc_str}")

            cases.append({
                "doc_id": doc_id,
                "title": doc_title,
                "recommendation": rec,
                "max_severity": max_sev,
                "exception_codes": exc_codes,
                "invoice_num": inv_num,
                "po_number": fields.get("po_number"),
                "supplier_name": fields.get("supplier_name"),
                "grand_total": fields.get("grand_total"),
                "currency": curr,
                "elapsed_s": round(elapsed, 2),
                "output_file": str(out_file.name),
                "error": None,
            })

        except Exception as e:
            elapsed = time.time() - t_doc_start
            counts["FAILED"] += 1
            print(f"-> \033[91mFAILED\033[0m: {str(e)[:45]} ({elapsed:.1f}s)")
            cases.append({
                "doc_id": doc_id,
                "title": doc_title,
                "recommendation": "SYSTEM_ERROR",
                "max_severity": "High",
                "exception_codes": ["ERR"],
                "elapsed_s": round(elapsed, 2),
                "output_file": str(out_file.name),
                "error": str(e),
            })

    total_elapsed = time.time() - t_start

    # 3. Build & save consolidated summary JSON
    summary_payload = {
        "metadata": {
            "title": "AIVA System A Batch Invoice Test Summary",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "tag": tag_name,
            "total_documents": total_count,
            "total_elapsed_s": round(total_elapsed, 1),
            "output_directory": str(out_dir.resolve()),
        },
        "statistics": {
            "counts": counts,
            "rules": rules_counter,
        },
        "cases": cases,
    }

    summary_file = out_dir / "summary.json"
    summary_file.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # 4. Print Final Report
    print_banner("Batch Test Execution Complete")
    print(f"Total Documents:     {total_count}")
    print(f"Total Duration:      {total_elapsed / 60:.1f} minutes ({total_elapsed:.1f} s)")
    print(f"Average Duration:    {total_elapsed / max(1, total_count):.1f} s / document")
    print("\n--- Recommendation Breakdown ---")
    print(f"  • AUTO_PASS:       {counts.get('AUTO_PASS', 0):3d} ({counts.get('AUTO_PASS', 0)*100/max(1, total_count):.1f}%)")
    print(f"  • REVIEW:          {counts.get('REVIEW', 0):3d} ({counts.get('REVIEW', 0)*100/max(1, total_count):.1f}%)")
    print(f"  • HOLD:            {counts.get('HOLD', 0):3d} ({counts.get('HOLD', 0)*100/max(1, total_count):.1f}%)")
    print(f"  • MANUAL_REVIEW:   {counts.get('MANUAL_REVIEW', 0):3d} ({counts.get('MANUAL_REVIEW', 0)*100/max(1, total_count):.1f}%)")
    print(f"  • SYSTEM_ERROR:    {counts.get('SYSTEM_ERROR', 0):3d} ({counts.get('SYSTEM_ERROR', 0)*100/max(1, total_count):.1f}%)")
    if counts.get("FAILED"):
        print(f"  • RUN FAILURES:    {counts.get('FAILED', 0):3d}")

    print("\n--- Rules Pass/Fail Summary ---")
    for rid in sorted(rules_counter.keys()):
        stat = rules_counter[rid]
        p, f, mr = stat.get("pass", 0), stat.get("fail", 0), stat.get("manual_review", 0)
        print(f"  • {rid:<6}: Pass: {p:2d} | Fail: {f:2d} | ManualReview: {mr:2d}")

    print(f"\nAll JSON results and summary saved to: {out_dir.resolve()}")
    print(f"Summary JSON: {summary_file.resolve()}\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AIVA System A — Batch Test on Paperless Documents Tagged 'invoice'",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--tag", default="invoice", help="Tag name in Paperless-ngx (default: 'invoice')")
    parser.add_argument(
        "--mode",
        choices=["production", "sandbox"],
        default="production",
        help="System A execution mode (production=real Oracle+Qwen; sandbox=simulators)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("results/paperless_invoices"),
        help="Directory to save individual result JSONs and summary.json (default: results/paperless_invoices)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit number of documents to verify (e.g. 5)")
    parser.add_argument("--skip-existing", action="store_true", help="Skip documents that already have a result JSON in out-dir")
    parser.add_argument("--quick", action="store_true", help="Pass --quick flag to skip crop/table perception details")
    parser.add_argument("--doc-id", type=int, default=None, help="Verify a single specific Paperless document ID (e.g. 20)")

    args = parser.parse_args()

    return run_batch(
        tag_name=args.tag,
        mode=args.mode,
        out_dir=args.out_dir,
        limit=args.limit,
        skip_existing=args.skip_existing,
        quick=args.quick,
        specific_doc_id=args.doc_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
