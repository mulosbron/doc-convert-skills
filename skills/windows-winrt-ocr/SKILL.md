---
name: windows-winrt-ocr
description: >-
  Built-in Windows 10/11 local OCR using the native WinRT Windows.Media.Ocr.OcrEngine
  API with zero external ML model downloads and zero GPU VRAM usage. Supports
  per-page hybrid PDF extraction (instant digital text via PyMuPDF + fast WinRT
  OCR only on scanned pages), image OCR, Turkish (tr) and installed Windows OCR
  language packs. Use on Windows machines when fast, offline, low-footprint CPU
  OCR is needed without installing Tesseract or large VLM weights.
version: "1.0.0"
license: MIT
metadata:
  category: ocr
  platform: windows
  triggers: windows ocr, winrt ocr, local windows ocr, Windows.Media.Ocr, offline pdf ocr windows, turkish ocr windows
---

# Windows Native WinRT OCR (`Windows.Media.Ocr`)

Uses the built-in **Windows 10/11 WinRT `Windows.Media.Ocr.OcrEngine`** via PowerShell and a smart per-page hybrid Python CLI (`winrt_pdf_ocr.py`), requiring **0 GB VRAM** and **zero OCR model downloads**.

## When to Use

- Running on **Windows 10/11** where Tesseract or GPU VLM engines are not installed or VRAM is limited.
- Converting **hybrid PDFs** (mix of digital selectable-text pages and scanned image pages) quickly: digital pages extract in milliseconds via PyMuPDF (`fitz`) while only scanned pages go to `Windows.Media.Ocr`.
- Offline/private OCR for clean printed documents in **Turkish (`tr`)**, **English (`en-US` / `en-GB`)**, or any installed Windows OCR language pack.

## Check Installed Windows OCR Languages

```powershell
python skills/windows-winrt-ocr/scripts/winrt_pdf_ocr.py --list-langs
```

Or directly via PowerShell:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File skills/windows-winrt-ocr/scripts/winrt_ocr_engine.ps1 -ListLangs
```

To install additional languages (e.g., Turkish `tr`, German `de-DE`): open `ms-settings:regionlanguage` -> Add a language -> include **Optical character recognition**.

## CLI Usage

### 1. Hybrid PDF or Image OCR (Python CLI)
```bash
# Smart hybrid PDF (digital pages direct, scanned pages via Windows.Media.Ocr)
python skills/windows-winrt-ocr/scripts/winrt_pdf_ocr.py input.pdf -o ./converted_output -l tr -m hybrid -f md

# Force OCR on every page (150 DPI grayscale fallback if raw image stream absent)
python skills/windows-winrt-ocr/scripts/winrt_pdf_ocr.py scanned.pdf -o ./converted_output -l en-GB -m ocr -f txt

# Single image OCR
python skills/windows-winrt-ocr/scripts/winrt_pdf_ocr.py receipt.png -o ./converted_output -l tr -f md
```

### 2. Direct PowerShell WinRT Engine (Images / Directory)
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File skills/windows-winrt-ocr/scripts/winrt_ocr_engine.ps1 -InputPath .\pages -LangTag tr -OutputJson .\ocr.json
```

## Architecture Notes

- **Fast Image Extraction**: When a PDF page is scanned, `winrt_pdf_ocr.py` extracts the embedded image stream directly (`doc.extract_image`) when possible instead of full-page re-rendering, falling back to `150 DPI` grayscale pixmap only when needed.
- **Persistent Engine Session**: `winrt_ocr_engine.ps1` initializes `Windows.Media.Ocr.OcrEngine` once per batch and loops across all images in a single PowerShell process, avoiding per-page startup overhead.
- **De-hyphenation & Cleanup**: Joins wrapped line-break hyphens and strips isolated page-number headers.

## Guardrails & Limitations

- **Windows-only**: `Windows.Media.Ocr` is available only on native Windows 10/11 (not Linux/macOS; WSL requires invoking Windows `powershell.exe` with Windows paths).
- **Complex Layouts**: Ideal for linear prose, books, reports, and clean scans. For complex multi-span tables, mathematical equations, or handwriting, prefer `surya-marker`, `docling`, or `chandra-ocr`.
