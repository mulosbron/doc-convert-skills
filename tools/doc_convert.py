#!/usr/bin/env python3
"""Unified CLI entrypoint for device-aware OCR routing and document conversion.

Subcommands:
  profile    Profile host CPU/RAM/GPU/VRAM and installed OCR/document tools
  inspect    Inspect a file or directory (digital vs hybrid vs scanned PDF)
  recommend  Recommend the optimal OCR/conversion engine & worker budget
  convert    Execute (or dry-run) conversion with quality validation gates
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "skills" / "device-aware-ocr-router" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from doc_convert_runner import run_conversion_pipeline  # noqa: E402
from document_inspector import inspect_target  # noqa: E402
from ocr_recommender import recommend_for_document  # noqa: E402
from system_profiler import collect_system_profile, format_pretty  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Device-aware OCR & document conversion CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prof = sub.add_parser("profile", help="Profile device hardware & installed OCR/doc tools.")
    p_prof.add_argument("--path", default=None)
    p_prof.add_argument("--pretty", action="store_true")
    p_prof.add_argument("--no-network-probe", action="store_true")

    p_insp = sub.add_parser("inspect", help="Inspect file or directory for document/PDF routing.")
    p_insp.add_argument("target")
    p_insp.add_argument("--max-files", type=int, default=100)
    p_insp.add_argument("--sample-pages", type=int, default=5)

    p_rec = sub.add_parser("recommend", help="Recommend optimal OCR/conversion route for this device.")
    p_rec.add_argument("target", nargs="?", default=None)
    p_rec.add_argument("--goal", default="markdown")
    p_rec.add_argument("--privacy", default="local-only", choices=("local-only", "allow-cloud"))
    p_rec.add_argument("--quality", default="balanced", choices=("fast", "balanced", "max"))
    p_rec.add_argument("--lang", default="eng")
    p_rec.add_argument("--complexity", default="standard")
    p_rec.add_argument("--doc-type", default=None, choices=("scanned-pdf", "digital-pdf", "image", "office-doc", "audio"))
    p_rec.add_argument("--no-network-probe", action="store_true")

    p_conv = sub.add_parser("convert", help="Run device-aware conversion pipeline with validation.")
    p_conv.add_argument("target")
    p_conv.add_argument("-o", "--output", default=None)
    p_conv.add_argument("--engine", default="auto")
    p_conv.add_argument("--goal", default="markdown")
    p_conv.add_argument("--privacy", default="local-only", choices=("local-only", "allow-cloud"))
    p_conv.add_argument("--quality", default="balanced", choices=("fast", "balanced", "max"))
    p_conv.add_argument("--lang", default="eng")
    p_conv.add_argument("--complexity", default="standard")
    p_conv.add_argument("--workers", default="auto")
    p_conv.add_argument("--dry-run", action="store_true")
    p_conv.add_argument("--no-network-probe", action="store_true")

    args = parser.parse_args()

    if args.command == "profile":
        profile = collect_system_profile(target_path=args.path, skip_network_probe=args.no_network_probe)
        print(format_pretty(profile) if args.pretty else json.dumps(profile, indent=2, ensure_ascii=False))
        return 0

    if args.command == "inspect":
        res = inspect_target(args.target, max_files=args.max_files, sample_limit=args.sample_pages)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 1 if "error" in res else 0

    if args.command == "recommend":
        profile = collect_system_profile(target_path=args.target, skip_network_probe=args.no_network_probe)
        doc_info = None
        batch_count = 1
        if args.target:
            insp = inspect_target(args.target)
            if "error" in insp:
                print(json.dumps(insp, indent=2, ensure_ascii=False))
                return 1
            batch_count = max(1, insp["count"])
            if insp["files"]:
                doc_info = insp["files"][0]
        elif args.doc_type:
            synthetic = {
                "scanned-pdf": {"category": "pdf", "ocr_required": True, "pdf": {"pdf_kind": "scanned"}},
                "digital-pdf": {"category": "pdf", "ocr_required": False, "pdf": {"pdf_kind": "digital"}},
                "image": {"category": "image", "ocr_required": True},
                "office-doc": {"category": "office_word", "ocr_required": False},
                "audio": {"category": "audio_video", "ocr_required": False},
            }
            doc_info = synthetic[args.doc_type]
        rec = recommend_for_document(
            profile=profile,
            doc_info=doc_info,
            goal=args.goal,
            privacy=args.privacy,
            quality=args.quality,
            lang=args.lang,
            complexity=args.complexity,
            batch_count=batch_count,
        )
        print(json.dumps(rec, indent=2, ensure_ascii=False))
        return 0

    if args.command == "convert":
        summary = run_conversion_pipeline(
            target=args.target,
            output_dir=args.output,
            engine=args.engine,
            goal=args.goal,
            privacy=args.privacy,
            quality=args.quality,
            lang=args.lang,
            complexity=args.complexity,
            workers=args.workers,
            dry_run=args.dry_run,
            no_network_probe=args.no_network_probe,
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 1 if "error" in summary else 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
