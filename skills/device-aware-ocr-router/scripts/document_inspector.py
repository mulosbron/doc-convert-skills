#!/usr/bin/env python3
"""Document & batch directory inspector for OCR/conversion routing.

Inspects single files or directories, detects format categories, and classifies
PDFs as `digital`, `hybrid`, or `scanned` using PyMuPDF (`fitz`), `pypdf`,
Poppler (`pdfinfo`/`pdftotext`), or a pure-Python fallback heuristic.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


EXTENSION_CATEGORIES: dict[str, str] = {
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".tif": "image",
    ".tiff": "image",
    ".bmp": "image",
    ".gif": "image",
    ".docx": "office_word",
    ".doc": "office_word",
    ".odt": "office_word",
    ".rtf": "office_word",
    ".xlsx": "office_sheet",
    ".xls": "office_sheet",
    ".ods": "office_sheet",
    ".csv": "office_sheet",
    ".tsv": "office_sheet",
    ".pptx": "office_slide",
    ".ppt": "office_slide",
    ".odp": "office_slide",
    ".mp3": "audio_video",
    ".wav": "audio_video",
    ".m4a": "audio_video",
    ".ogg": "audio_video",
    ".flac": "audio_video",
    ".webm": "audio_video",
    ".mp4": "audio_video",
    ".mkv": "audio_video",
    ".mov": "audio_video",
    ".html": "markup_web",
    ".htm": "markup_web",
    ".md": "markup_web",
    ".txt": "markup_web",
    ".xml": "markup_web",
    ".json": "markup_web",
    ".epub": "markup_web",
}


def _classify_pdf_metrics(page_count: int, sampled_chars: int, sampled_pages: int, image_count: int) -> str:
    """Classify PDF into digital, hybrid, scanned, or unknown."""
    if sampled_pages <= 0:
        return "unknown"
    avg_chars = sampled_chars / sampled_pages
    if avg_chars >= 80:
        if image_count > sampled_pages * 2 and avg_chars < 200:
            return "hybrid"
        return "digital"
    if avg_chars >= 15:
        return "hybrid"
    return "scanned"


def _inspect_pdf_fitz(path: Path, sample_limit: int) -> dict[str, Any]:
    import fitz  # type: ignore

    doc = fitz.open(str(path))
    try:
        page_count = len(doc)
        sample_indices = _pick_sample_indices(page_count, sample_limit)
        total_chars = 0
        image_count = 0
        for idx in sample_indices:
            page = doc[idx]
            text = page.get_text("text") or ""
            total_chars += len(text.strip())
            image_count += len(page.get_images(full=False))
        kind = _classify_pdf_metrics(page_count, total_chars, len(sample_indices), image_count)
        return {
            "inspector": "pymupdf",
            "page_count": page_count,
            "sampled_pages": len(sample_indices),
            "total_sampled_chars": total_chars,
            "avg_chars_per_page": round(total_chars / max(1, len(sample_indices)), 1),
            "sampled_images": image_count,
            "pdf_kind": kind,
            "ocr_required": kind in ("scanned", "hybrid"),
        }
    finally:
        doc.close()


def _inspect_pdf_pypdf(path: Path, sample_limit: int) -> dict[str, Any]:
    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(str(path))
    page_count = len(reader.pages)
    sample_indices = _pick_sample_indices(page_count, sample_limit)
    total_chars = 0
    image_count = 0
    for idx in sample_indices:
        page = reader.pages[idx]
        text = page.extract_text() or ""
        total_chars += len(text.strip())
        try:
            image_count += len(page.images)
        except Exception:
            pass
    kind = _classify_pdf_metrics(page_count, total_chars, len(sample_indices), image_count)
    return {
        "inspector": "pypdf",
        "page_count": page_count,
        "sampled_pages": len(sample_indices),
        "total_sampled_chars": total_chars,
        "avg_chars_per_page": round(total_chars / max(1, len(sample_indices)), 1),
        "sampled_images": image_count,
        "pdf_kind": kind,
        "ocr_required": kind in ("scanned", "hybrid"),
    }


def _inspect_pdf_poppler(path: Path, sample_limit: int) -> dict[str, Any]:
    page_count = 0
    if shutil.which("pdfinfo"):
        proc = subprocess.run(
            ["pdfinfo", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5.0,
        )
        m = re.search(r"Pages:\s*(\d+)", proc.stdout)
        if m:
            page_count = int(m.group(1))
    last_page = max(1, min(sample_limit, page_count or sample_limit))
    proc_txt = subprocess.run(
        ["pdftotext", "-f", "1", "-l", str(last_page), str(path), "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=8.0,
    )
    total_chars = len(proc_txt.stdout.strip())
    kind = _classify_pdf_metrics(page_count or last_page, total_chars, last_page, 0)
    return {
        "inspector": "poppler",
        "page_count": page_count or last_page,
        "sampled_pages": last_page,
        "total_sampled_chars": total_chars,
        "avg_chars_per_page": round(total_chars / max(1, last_page), 1),
        "sampled_images": 0,
        "pdf_kind": kind,
        "ocr_required": kind in ("scanned", "hybrid"),
    }


def _inspect_pdf_heuristic(path: Path) -> dict[str, Any]:
    """Stdlib-only raw PDF marker heuristic when no PDF parser is installed."""
    raw = path.read_bytes()[: 2 * 1024 * 1024]
    pages_est = len(re.findall(rb"/Type\s*/Page\b", raw))
    has_font = b"/Font" in raw
    has_image = b"/Subtype /Image" in raw or b"/Subtype/Image" in raw
    if has_image and not has_font:
        kind = "scanned"
    elif has_font and not has_image:
        kind = "digital"
    elif has_font and has_image:
        kind = "hybrid"
    else:
        kind = "unknown"
    return {
        "inspector": "stdlib-heuristic",
        "page_count": max(1, pages_est) if pages_est else None,
        "sampled_pages": 0,
        "total_sampled_chars": None,
        "avg_chars_per_page": None,
        "sampled_images": None,
        "pdf_kind": kind,
        "ocr_required": kind in ("scanned", "hybrid", "unknown"),
    }


def _pick_sample_indices(page_count: int, sample_limit: int) -> list[int]:
    """Pick first, middle, and last pages (up to sample_limit) so page 1 never fools routing."""
    if page_count <= 0:
        return []
    if page_count <= sample_limit:
        return list(range(page_count))
    indices = {0, page_count // 2, page_count - 1}
    step = max(1, page_count // sample_limit)
    for i in range(0, page_count, step):
        if len(indices) >= sample_limit:
            break
        indices.add(i)
    return sorted(indices)[:sample_limit]


def inspect_pdf(path: Path, sample_limit: int = 5) -> dict[str, Any]:
    """Inspect a PDF using the best available local parser."""
    if importlib.util.find_spec("fitz") is not None:
        try:
            return _inspect_pdf_fitz(path, sample_limit)
        except Exception:
            pass
    if importlib.util.find_spec("pypdf") is not None:
        try:
            return _inspect_pdf_pypdf(path, sample_limit)
        except Exception:
            pass
    if shutil.which("pdftotext"):
        try:
            return _inspect_pdf_poppler(path, sample_limit)
        except Exception:
            pass
    return _inspect_pdf_heuristic(path)


def inspect_file(path: Path, sample_limit: int = 5) -> dict[str, Any]:
    """Inspect a single document file."""
    ext = path.suffix.lower()
    category = EXTENSION_CATEGORIES.get(ext, "other")
    size_bytes = path.stat().st_size if path.exists() else 0
    result: dict[str, Any] = {
        "path": str(path),
        "name": path.name,
        "extension": ext,
        "category": category,
        "size_mb": round(size_bytes / (1024**2), 3),
        "ocr_required": category == "image",
    }
    if category == "pdf" and path.exists():
        result["pdf"] = inspect_pdf(path, sample_limit=sample_limit)
        result["ocr_required"] = result["pdf"]["ocr_required"]
    return result


def inspect_target(target: str, max_files: int = 100, sample_limit: int = 5) -> dict[str, Any]:
    """Inspect a file or directory of files."""
    path = Path(target)
    if not path.exists():
        return {"error": f"Path not found: {target}", "files": [], "count": 0}

    if path.is_file():
        files = [inspect_file(path, sample_limit=sample_limit)]
        is_batch = False
    else:
        candidates = sorted(p for p in path.rglob("*") if p.is_file())[:max_files]
        files = [inspect_file(p, sample_limit=sample_limit) for p in candidates]
        is_batch = True

    category_counts: dict[str, int] = {}
    ocr_files = 0
    total_mb = 0.0
    for f in files:
        cat = f["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1
        if f.get("ocr_required"):
            ocr_files += 1
        total_mb += float(f.get("size_mb", 0.0))

    return {
        "target": str(path),
        "is_batch": is_batch,
        "count": len(files),
        "total_size_mb": round(total_mb, 3),
        "category_counts": category_counts,
        "ocr_required_count": ocr_files,
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect documents for OCR/conversion routing.")
    parser.add_argument("target", help="File or directory path to inspect.")
    parser.add_argument("--max-files", type=int, default=100, help="Max files when inspecting a directory.")
    parser.add_argument("--sample-pages", type=int, default=5, help="Pages to sample per PDF.")
    args = parser.parse_args()

    result = inspect_target(args.target, max_files=args.max_files, sample_limit=args.sample_pages)
    print(json.dumps(result, indent=2))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
