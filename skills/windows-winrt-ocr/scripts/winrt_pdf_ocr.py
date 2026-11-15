#!/usr/bin/env python3
"""Headless hybrid PDF & image OCR using built-in Windows.Media.Ocr (WinRT)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
PS_ENGINE = Path(__file__).resolve().parent / "winrt_ocr_engine.ps1"


def normalize_winrt_lang(lang: str) -> str:
    """Map generic language hints (tur, eng, tr, en-US) to BCP-47 WinRT tags."""
    if not lang or lang == "auto":
        return "tr"
    primary = lang.split("+")[0].strip().lower()
    mapping = {
        "tur": "tr",
        "tr": "tr",
        "eng": "en-US",
        "en": "en-US",
        "en-gb": "en-GB",
        "en-us": "en-US",
        "deu": "de-DE",
        "de": "de-DE",
        "fra": "fr-FR",
        "fr": "fr-FR",
        "ara": "ar-SA",
        "ar": "ar-SA",
    }
    return mapping.get(primary, lang.split("+")[0].strip())


def list_winrt_languages() -> list[dict[str, str]]:
    """Query installed Windows.Media.Ocr language packs."""
    if platform.system() != "Windows":
        return []
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(PS_ENGINE),
        "-ListLangs",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10.0)
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    data = json.loads(proc.stdout)
    return [data] if isinstance(data, dict) else list(data)


def clean_page_lines(lines: list[str], page_num: int) -> list[str]:
    """Strip isolated page-number headers on content pages and normalize lines."""
    cleaned = [ln.strip() for ln in lines if ln and ln.strip()]
    if page_num > 3 and len(cleaned) > 2 and re.match(r"^\d{1,3}$", cleaned[0]):
        cleaned.pop(0)
    return cleaned


def lines_to_paragraphs(lines: list[str]) -> str:
    """Reconstruct readable paragraphs and de-hyphenate wrapped line breaks."""
    if not lines:
        return ""
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if current and current[-1].endswith("-") and len(current[-1]) > 1 and not current[-1].endswith("--"):
            current[-1] = current[-1][:-1] + line
        else:
            current.append(line)
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs)


def _run_ps_ocr(input_path: Path, lang_tag: str, output_json: Path | None = None) -> dict[str, Any]:
    if platform.system() != "Windows":
        raise RuntimeError("Windows WinRT OCR requires Windows 10/11.")
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(PS_ENGINE),
        "-InputPath",
        str(input_path),
        "-LangTag",
        lang_tag,
    ]
    if output_json is not None:
        cmd.extend(["-OutputJson", str(output_json)])
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300.0)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"PowerShell exited with {proc.returncode}")
    if output_json is not None and output_json.exists():
        return json.loads(output_json.read_text(encoding="utf-8-sig"))
    return json.loads(proc.stdout)


def run_winrt_ocr(
    input_path: Path,
    output_dir: Path,
    lang: str = "tr",
    mode: str = "hybrid",
    fmt: str = "md",
    dpi: int = 150,
) -> dict[str, Any]:
    """Run Windows.Media.Ocr on an image or hybrid/scanned PDF."""
    lang_tag = normalize_winrt_lang(lang)
    output_dir.mkdir(parents=True, exist_ok=True)
    ext = input_path.suffix.lower()

    if ext in IMAGE_EXTENSIONS:
        payload = _run_ps_ocr(input_path, lang_tag)
        results = payload.get("results", [])
        lines = results[0].get("lines", []) if results else []
        text = lines_to_paragraphs(clean_page_lines(lines, 1))
        out_file = output_dir / f"{input_path.stem}.{fmt}"
        if fmt == "json":
            out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        elif fmt == "txt":
            out_file.write_text(text + "\n", encoding="utf-8")
        else:
            out_file.write_text(f"# {input_path.stem}\n\n{text}\n", encoding="utf-8")
        return {
            "output": str(out_file),
            "language": payload.get("language", lang_tag),
            "digital_pages": 0,
            "ocr_pages": 1,
            "elapsed_ms": payload.get("elapsed_ms", 0),
        }

    if ext != ".pdf":
        raise ValueError(f"Unsupported input type for windows-winrt-ocr: {ext}")
    if importlib.util.find_spec("fitz") is None:
        raise RuntimeError("PyMuPDF (fitz) is required to inspect/rasterize PDF pages for windows-winrt-ocr.")

    import fitz  # type: ignore

    doc = fitz.open(str(input_path))
    total_pages = len(doc)
    page_texts: dict[int, str] = {}
    pages_to_ocr: list[int] = []
    temp_dir = Path(tempfile.mkdtemp(prefix="winrt_ocr_"))
    elapsed_ms = 0
    used_lang = lang_tag

    try:
        for pno in range(1, total_pages + 1):
            page = doc[pno - 1]
            if mode != "ocr":
                blocks = [b[4].strip() for b in page.get_text("blocks") if b[6] == 0 and b[4].strip()]
                raw_lines = [ln for blk in blocks for ln in blk.splitlines() if ln.strip()]
                digital = lines_to_paragraphs(clean_page_lines(raw_lines, pno))
                if len(digital.strip()) > 40 or mode == "digital":
                    page_texts[pno] = digital
                    continue
            pages_to_ocr.append(pno)

        if pages_to_ocr:
            for pno in pages_to_ocr:
                page = doc[pno - 1]
                saved = False
                imgs = page.get_images()
                if imgs:
                    base_img = doc.extract_image(imgs[0][0])
                    img_ext = str(base_img.get("ext", "png")).lower()
                    if img_ext in ("png", "jpg", "jpeg", "bmp", "tif", "tiff"):
                        (temp_dir / f"page_{pno:04d}.{img_ext}").write_bytes(base_img["image"])
                        saved = True
                if not saved:
                    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
                    pix.save(str(temp_dir / f"page_{pno:04d}.png"))

            json_out = temp_dir / "results.json"
            payload = _run_ps_ocr(temp_dir, lang_tag, output_json=json_out)
            elapsed_ms = int(payload.get("elapsed_ms", 0))
            used_lang = str(payload.get("language", lang_tag))
            for item in payload.get("results", []):
                pno = int(item.get("page") or 1)
                page_texts[pno] = lines_to_paragraphs(clean_page_lines(item.get("lines", []), pno))
    finally:
        doc.close()
        shutil.rmtree(temp_dir, ignore_errors=True)

    out_file = output_dir / f"{input_path.stem}.{fmt}"
    if fmt == "json":
        out_payload = {
            "source": str(input_path),
            "language": used_lang,
            "total_pages": total_pages,
            "digital_pages": total_pages - len(pages_to_ocr),
            "ocr_pages": len(pages_to_ocr),
            "pages": [{"page": p, "text": page_texts.get(p, "")} for p in range(1, total_pages + 1)],
        }
        out_file.write_text(json.dumps(out_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    elif fmt == "txt":
        chunks = [f"--- [Sayfa {p}] ---\n\n{page_texts.get(p, '').strip() or '[Boş sayfa]'}\n\n" for p in range(1, total_pages + 1)]
        out_file.write_text(f"{input_path.stem}\n{'=' * 60}\n\n" + "".join(chunks), encoding="utf-8")
    else:
        chunks = [f"## [Page {p}]\n\n{page_texts.get(p, '').strip() or '*(Empty page)*'}\n\n" for p in range(1, total_pages + 1)]
        out_file.write_text(f"# {input_path.stem}\n\n---\n\n" + "".join(chunks), encoding="utf-8")

    return {
        "output": str(out_file),
        "language": used_lang,
        "digital_pages": total_pages - len(pages_to_ocr),
        "ocr_pages": len(pages_to_ocr),
        "elapsed_ms": elapsed_ms,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Hybrid PDF & image OCR using Windows.Media.Ocr (WinRT).")
    parser.add_argument("input", nargs="?", help="PDF or image path.")
    parser.add_argument("-o", "--output-dir", default="./converted_output", help="Output directory.")
    parser.add_argument("-l", "--lang", default="tr", help="Language tag or hint (tr, en-US, en-GB, tur, eng).")
    parser.add_argument("-m", "--mode", default="hybrid", choices=("hybrid", "ocr", "digital"))
    parser.add_argument("-f", "--format", default="md", choices=("md", "txt", "json"))
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--list-langs", action="store_true", help="List installed Windows.Media.Ocr languages.")
    args = parser.parse_args()

    if args.list_langs:
        print(json.dumps(list_winrt_languages(), indent=2, ensure_ascii=False))
        return 0
    if not args.input:
        parser.error("input is required unless --list-langs is passed")

    res = run_winrt_ocr(
        input_path=Path(args.input),
        output_dir=Path(args.output_dir),
        lang=args.lang,
        mode=args.mode,
        fmt=args.format,
        dpi=args.dpi,
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
