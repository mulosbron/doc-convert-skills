#!/usr/bin/env python3
"""Unified device-aware document conversion runner & output quality validator."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from document_inspector import inspect_target  # noqa: E402
from ocr_recommender import recommend_for_document  # noqa: E402
from system_profiler import collect_system_profile  # noqa: E402


def validate_output_file(output_path: Path) -> dict[str, Any]:
    """Run post-conversion quality gates on a generated text/Markdown/HTML/JSON file."""
    if not output_path.exists():
        return {"passed": False, "reason": "Output file was not created.", "size_bytes": 0}

    size_bytes = output_path.stat().st_size
    if size_bytes == 0:
        return {"passed": False, "reason": "Output file is empty (0 bytes).", "size_bytes": 0}

    if output_path.suffix.lower() in (".pdf", ".docx", ".xlsx", ".pptx"):
        return {
            "passed": True,
            "size_bytes": size_bytes,
            "note": "Binary output created and non-empty.",
        }

    text = output_path.read_text(encoding="utf-8", errors="replace")
    stripped = text.strip()
    if len(stripped) < 10:
        return {
            "passed": False,
            "reason": f"Extracted text is suspiciously short ({len(stripped)} chars).",
            "size_bytes": size_bytes,
            "char_count": len(stripped),
        }

    replacement_chars = text.count("\ufffd")
    garble_ratio = replacement_chars / max(1, len(text))
    lines = [ln for ln in text.splitlines() if ln.strip()]
    has_markdown_structure = any(
        ln.lstrip().startswith(("#", "|", "-", "*")) for ln in lines
    )

    passed = garble_ratio < 0.02
    return {
        "passed": passed,
        "reason": "OK" if passed else f"High replacement-character ratio ({garble_ratio:.2%}).",
        "size_bytes": size_bytes,
        "char_count": len(stripped),
        "line_count": len(lines),
        "garble_ratio": round(garble_ratio, 4),
        "has_markdown_structure": has_markdown_structure,
    }


def _run_pymupdf_pdfplumber(input_path: Path, output_dir: Path) -> tuple[bool, Path, str]:
    """Extract digital PDF text and tables into clean Markdown using pdfplumber/fitz/pypdf."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{input_path.stem}.md"
    sections: list[str] = [f"# {input_path.name}\n"]

    if importlib.util.find_spec("pdfplumber") is not None:
        import pdfplumber  # type: ignore

        with pdfplumber.open(str(input_path)) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                sections.append(f"\n## Page {idx}\n")
                text = (page.extract_text(layout=False) or "").strip()
                if text:
                    sections.append(text + "\n")
                tables = page.extract_tables() or []
                for t_idx, table in enumerate(tables, start=1):
                    clean_rows = [
                        [("" if c is None else str(c).replace("\n", " ").strip()) for c in row]
                        for row in table
                        if row and any(c is not None and str(c).strip() for c in row)
                    ]
                    if not clean_rows:
                        continue
                    header = clean_rows[0]
                    sections.append(f"\n### Table {t_idx} (Page {idx})\n")
                    sections.append("| " + " | ".join(header) + " |")
                    sections.append("| " + " | ".join("---" for _ in header) + " |")
                    for row in clean_rows[1:]:
                        padded = row + [""] * max(0, len(header) - len(row))
                        sections.append("| " + " | ".join(padded[: len(header)]) + " |")
                    sections.append("")
        out_file.write_text("\n".join(sections), encoding="utf-8")
        return True, out_file, "Extracted via pdfplumber"

    if importlib.util.find_spec("fitz") is not None:
        import fitz  # type: ignore

        doc = fitz.open(str(input_path))
        try:
            for idx, page in enumerate(doc, start=1):
                sections.append(f"\n## Page {idx}\n")
                sections.append((page.get_text("text") or "").strip() + "\n")
        finally:
            doc.close()
        out_file.write_text("\n".join(sections), encoding="utf-8")
        return True, out_file, "Extracted via pymupdf"

    if importlib.util.find_spec("pypdf") is not None:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(input_path))
        for idx, page in enumerate(reader.pages, start=1):
            sections.append(f"\n## Page {idx}\n")
            sections.append((page.extract_text() or "").strip() + "\n")
        out_file.write_text("\n".join(sections), encoding="utf-8")
        return True, out_file, "Extracted via pypdf"

    return False, out_file, "None of pdfplumber, fitz, or pypdf are installed."


def _run_rapidocr_onnx(input_path: Path, output_dir: Path) -> tuple[bool, Path, str]:
    """Run RapidOCR (ONNX Runtime) over an image or PDF pages rendered by PyMuPDF."""
    if importlib.util.find_spec("rapidocr_onnxruntime") is None:
        return False, output_dir / f"{input_path.stem}.md", "rapidocr_onnxruntime is not installed."

    from rapidocr_onnxruntime import RapidOCR  # type: ignore

    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{input_path.stem}.md"
    ocr = RapidOCR()
    sections: list[str] = [f"# {input_path.name}\n"]

    if input_path.suffix.lower() == ".pdf":
        if importlib.util.find_spec("fitz") is None:
            return False, out_file, "PyMuPDF (fitz) is required to rasterize PDF pages for rapidocr-onnx."
        import fitz  # type: ignore

        doc = fitz.open(str(input_path))
        try:
            for idx, page in enumerate(doc, start=1):
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                result, _ = ocr(img_bytes)
                lines = [item[1] for item in (result or []) if len(item) >= 2]
                sections.append(f"\n## Page {idx}\n")
                sections.append("\n".join(lines) + "\n")
        finally:
            doc.close()
    else:
        result, _ = ocr(str(input_path))
        lines = [item[1] for item in (result or []) if len(item) >= 2]
        sections.append("\n".join(lines) + "\n")

    out_file.write_text("\n".join(sections), encoding="utf-8")
    return True, out_file, "Extracted via rapidocr-onnx"


def _build_cli_command(engine: str, input_path: Path, output_dir: Path, lang: str, workers: int) -> tuple[list[str], Path]:
    """Map an engine identifier to its concrete CLI invocation and expected output path."""
    stem = input_path.stem
    if engine == "opendataloader-pdf":
        return (
            ["opendataloader-pdf", "-f", "markdown-with-html", "--image-output", "off", "-o", str(output_dir), str(input_path)],
            output_dir / f"{stem}.md",
        )
    if engine == "chandra-ocr-vllm":
        return (
            ["chandra", str(input_path), str(output_dir), "--method", "vllm", "--max-workers", str(workers)],
            output_dir / stem / f"{stem}.md",
        )
    if engine == "chandra-ocr-hf":
        return (
            ["chandra", str(input_path), str(output_dir), "--method", "hf", "--batch-size", "1"],
            output_dir / stem / f"{stem}.md",
        )
    if engine == "surya-marker":
        return (
            ["marker_single", str(input_path), "--output_dir", str(output_dir)],
            output_dir / stem / f"{stem}.md",
        )
    if engine == "docling":
        return (
            ["docling", str(input_path), "--to", "md", "--output", str(output_dir)],
            output_dir / f"{stem}.md",
        )
    if engine == "ocrmypdf-tesseract":
        out_pdf = output_dir / f"{stem}.ocr.pdf"
        return (
            ["ocrmypdf", "-l", lang or "eng", "--deskew", "--skip-text", str(input_path), str(out_pdf)],
            out_pdf,
        )
    if engine in ("markitdown", "markitdown-cloud-ocr"):
        out_md = output_dir / f"{stem}.md"
        cmd = ["markitdown", str(input_path), "-o", str(out_md)]
        if engine == "markitdown-cloud-ocr":
            cmd.append("--use-plugins")
        return cmd, out_md
    if engine == "libreoffice-headless":
        return (
            ["soffice", "--headless", "--convert-to", "pdf", str(input_path), "--outdir", str(output_dir)],
            output_dir / f"{stem}.pdf",
        )
    return [], output_dir / f"{stem}.md"


def process_single_file(
    file_info: dict[str, Any],
    profile: dict[str, Any],
    output_dir: Path,
    engine_override: str,
    goal: str,
    privacy: str,
    quality: str,
    lang: str,
    complexity: str,
    prefer_installed: bool,
    dry_run: bool,
) -> dict[str, Any]:
    """Plan, optionally execute, and validate conversion for one file."""
    input_path = Path(file_info["path"])
    started = time.perf_counter()

    rec = recommend_for_document(
        profile=profile,
        doc_info=file_info,
        goal=goal,
        privacy=privacy,
        quality=quality,
        lang=lang,
        complexity=complexity,
        batch_count=1,
    )

    chosen = rec["recommended"]
    if engine_override not in ("auto", "ready-now"):
        chosen_engine = engine_override
    elif (engine_override == "ready-now" or (prefer_installed and not chosen["installed"])) and rec.get("ready_now"):
        chosen = rec["ready_now"]
        chosen_engine = chosen["engine"]
    else:
        chosen_engine = chosen["engine"]

    if dry_run:
        return {
            "input": str(input_path),
            "status": "dry_run",
            "selected_engine": chosen_engine,
            "installed": chosen.get("installed"),
            "command": chosen.get("command_template"),
            "install_hint": chosen.get("install_hint"),
            "warnings": rec.get("warnings", []),
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    ok = False
    out_path = output_dir / f"{input_path.stem}.md"
    message = ""

    if chosen_engine == "pymupdf-pdfplumber":
        ok, out_path, message = _run_pymupdf_pdfplumber(input_path, output_dir)
    elif chosen_engine == "rapidocr-onnx":
        ok, out_path, message = _run_rapidocr_onnx(input_path, output_dir)
    elif chosen_engine == "windows-winrt-ocr":
        winrt_scripts = SCRIPTS_DIR.parent.parent / "windows-winrt-ocr" / "scripts"
        if str(winrt_scripts) not in sys.path:
            sys.path.insert(0, str(winrt_scripts))
        from winrt_pdf_ocr import run_winrt_ocr  # type: ignore

        try:
            win_res = run_winrt_ocr(input_path=input_path, output_dir=output_dir, lang=lang or "tr", mode="hybrid", fmt="md")
            out_path = Path(win_res["output"])
            ok = True
            message = f"Extracted via windows-winrt-ocr ({win_res['digital_pages']} digital, {win_res['ocr_pages']} OCR)"
        except Exception as exc:
            ok = False
            message = str(exc)
    else:
        cmd, out_path = _build_cli_command(chosen_engine, input_path, output_dir, lang=lang, workers=1)
        if not cmd:
            return {
                "input": str(input_path),
                "status": "failed",
                "selected_engine": chosen_engine,
                "error": f"No built-in execution adapter for engine '{chosen_engine}'.",
            }
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600.0,
            )
            ok = proc.returncode == 0
            message = proc.stderr.strip() or proc.stdout.strip() or f"Exited with code {proc.returncode}"
        except FileNotFoundError:
            ok = False
            message = f"Executable '{cmd[0]}' not found. Install hint: {chosen.get('install_hint', '')}"
        except subprocess.TimeoutExpired:
            ok = False
            message = "Conversion timed out after 600s."

    elapsed = round(time.perf_counter() - started, 2)
    validation = validate_output_file(out_path) if ok else {"passed": False, "reason": message}
    status = "ok" if (ok and validation.get("passed")) else ("needs_review" if ok else "failed")

    return {
        "input": str(input_path),
        "output": str(out_path),
        "status": status,
        "selected_engine": chosen_engine,
        "elapsed_sec": elapsed,
        "message": message,
        "validation": validation,
    }


def run_conversion_pipeline(
    target: str,
    output_dir: str | None = None,
    engine: str = "auto",
    goal: str = "markdown",
    privacy: str = "local-only",
    quality: str = "balanced",
    lang: str = "eng",
    complexity: str = "standard",
    workers: str = "auto",
    prefer_installed: bool = True,
    dry_run: bool = False,
    no_network_probe: bool = False,
) -> dict[str, Any]:
    """Run device-aware conversion across a single file or batch directory."""
    profile = collect_system_profile(target_path=target, skip_network_probe=no_network_probe)
    inspected = inspect_target(target)
    if "error" in inspected:
        return {"error": inspected["error"]}

    files = inspected.get("files", [])
    if not files:
        return {"error": f"No files found in {target}"}

    target_path = Path(target)
    out_base = Path(output_dir) if output_dir else (
        (target_path.parent if target_path.is_file() else target_path) / "converted_output"
    )

    batch_rec = recommend_for_document(
        profile=profile,
        doc_info=files[0],
        goal=goal,
        privacy=privacy,
        quality=quality,
        lang=lang,
        complexity=complexity,
        batch_count=len(files),
    )
    safe_max_workers = int(batch_rec["orchestration"]["max_parallel_workers"])
    if workers == "auto":
        actual_workers = safe_max_workers
    else:
        requested = max(1, int(workers))
        actual_workers = min(requested, max(1, safe_max_workers)) if len(files) > 1 else 1

    results: list[dict[str, Any]] = []
    if actual_workers <= 1 or len(files) == 1 or dry_run:
        for f in files:
            results.append(
                process_single_file(
                    file_info=f,
                    profile=profile,
                    output_dir=out_base,
                    engine_override=engine,
                    goal=goal,
                    privacy=privacy,
                    quality=quality,
                    lang=lang,
                    complexity=complexity,
                    prefer_installed=prefer_installed,
                    dry_run=dry_run,
                )
            )
    else:
        with ThreadPoolExecutor(max_workers=actual_workers) as pool:
            futures = [
                pool.submit(
                    process_single_file,
                    f,
                    profile,
                    out_base,
                    engine,
                    goal,
                    privacy,
                    quality,
                    lang,
                    complexity,
                    prefer_installed,
                    dry_run,
                )
                for f in files
            ]
            for fut in as_completed(futures):
                results.append(fut.result())

    return {
        "target": str(target_path),
        "output_dir": str(out_base),
        "device_tier": profile["classification"]["tier"],
        "execution_mode": "dry_run" if dry_run else ("parallel" if actual_workers > 1 else "sequential"),
        "workers_used": actual_workers,
        "total_files": len(files),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute device-aware document conversion with quality validation.")
    parser.add_argument("target", help="File or directory to convert.")
    parser.add_argument("--output", "-o", default=None, help="Output directory.")
    parser.add_argument("--engine", default="auto", help="Engine override (auto, ready-now, or explicit engine name).")
    parser.add_argument("--goal", default="markdown")
    parser.add_argument("--privacy", default="local-only", choices=("local-only", "allow-cloud"))
    parser.add_argument("--quality", default="balanced", choices=("fast", "balanced", "max"))
    parser.add_argument("--lang", default="eng")
    parser.add_argument("--complexity", default="standard")
    parser.add_argument("--workers", default="auto", help="'auto' or integer worker count (clamped to hardware budget).")
    parser.add_argument("--strict-top-engine", action="store_true", help="Do not fall back to ready-now installed engine.")
    parser.add_argument("--dry-run", action="store_true", help="Plan only without executing conversions.")
    parser.add_argument("--no-network-probe", action="store_true")
    args = parser.parse_args()

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
        prefer_installed=not args.strict_top_engine,
        dry_run=args.dry_run,
        no_network_probe=args.no_network_probe,
    )
    print(json.dumps(summary, indent=2))
    return 1 if "error" in summary else 0


if __name__ == "__main__":
    raise SystemExit(main())
