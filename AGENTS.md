# Document Intelligence, OCR & File Conversion Skills

A standardized collection of **23 skills**, **Python CLI routing tools** (`tools/doc_convert.py`), **hardware/document profiler scripts**, and **orchestration agents** (`agents/`) for OCR (including native Windows WinRT `Windows.Media.Ocr`), document-to-Markdown/Obsidian extraction, document-to-math formalization, PDF routing/manipulation, Office & Google Sheets automation (`DOCX`, `PPTX`, `XLSX`, `ODT`/`ODS`), provenance metadata (`AKF`), audio transcription, live TV/game subtitle OCR, and universal multi-format file conversion.

## Skills

### OCR & Multi-Format Conversion Engines
| Skill | Read when |
|---|---|
| `skills/device-aware-ocr-router/SKILL.md` | **Start here for OCR or batch conversion.** Profiles device specs (CPU, RAM, GPU/VRAM, MPS, installed tools, Windows WinRT langs, vLLM/Ollama), inspects files, picks the optimal OCR/conversion engine, bounds parallelism safely, and validates outputs. |
| `skills/windows-winrt-ocr/SKILL.md` | Native Windows 10/11 built-in WinRT OCR (`Windows.Media.Ocr.OcrEngine`) with zero external model downloads, zero VRAM, and per-page hybrid PDF extraction (`fitz` + PowerShell WinRT). |
| `skills/chandra-ocr/SKILL.md` | Layout-aware OCR (`chandra-ocr`) converting scanned PDFs/images with tables, math, forms, handwriting, and 90+ languages into Markdown/HTML/JSON. |
| `skills/tizen-subtitle-translator/SKILL.md` | Real-time HDMI/game subtitle band OCR (Tesseract 5.5 + MNN CRNN workers, Y-plane row projection) and LAN/DeepL translation on Tizen (`SubtitleTV`). |
| `skills/markitdown/SKILL.md` | Microsoft `markitdown` CLI, Python API, `markitdown-mcp`, and `markitdown-ocr` converting PDF/Office/images/audio/HTML/ZIP/EPUB into LLM-ready Markdown. |
| `skills/convertx/SKILL.md` | Self-hosted universal converter (`ConvertX`) wrapping FFmpeg, ImageMagick, LibreOffice, Pandoc, Calibre, Inkscape, Vips, Assimp, and MarkItDown across 1,000+ format pairs. |
| `skills/audio-transcriber/SKILL.md` | Transcribing audio/video (`MP3`, `WAV`, `M4A`, `OGG`, `FLAC`, `WEBM`) to Markdown transcripts, SRT/VTT captions, and summaries via Whisper/Faster-Whisper. |

### PDF Intelligence & Structured Extraction
| Skill | Read when |
|---|---|
| `skills/pdf-conversion-router/SKILL.md` | Choosing the optimal route/settings when converting a PDF (digital, scanned/OCR, tables, slides, multi-column) to Markdown, HTML, text, JSON, or DOCX. |
| `skills/pdf-official/SKILL.md` | PDF merging/splitting, text/table extraction (`pypdf`, `pdfplumber`), form inspection/filling, annotations, and PDF-to-image scripts. |
| `skills/doc2math/SKILL.md` | Converting narrative technical documents and research excerpts into grounded Mathematical Problem Specifications (JSON) with zero-inference evidence citations. |
| `skills/obsidian-markdown/SKILL.md` | Formatting converted Markdown notes with Obsidian Flavored Markdown (`[[wikilinks]]`, `![[embeds]]`, callouts, YAML frontmatter properties). |

### Office Documents, Spreadsheets & Presentations
| Skill | Read when |
|---|---|
| `skills/docx-official/SKILL.md` | Creating, editing, analyzing, unpacking OOXML, and redlining Word `.docx` files. |
| `skills/xlsx-official/SKILL.md` | Building, auditing, and recalculating Excel `.xlsx` workbooks (`openpyxl`, `recalc.py`, zero formula errors). |
| `skills/bilig-workpaper/SKILL.md` | Deterministic formula-backed WorkPaper JSON and MCP tools for spreadsheets/XLSX verification without driving Excel UI. |
| `skills/googlesheets-automation/SKILL.md` | Reading, writing, formatting, filtering, and managing Google Sheets spreadsheets programmatically via Rube MCP. |
| `skills/pptx-official/SKILL.md` | Creating, editing, unpacking OOXML, generating thumbnails, `html2pptx`, and extracting `.pptx` decks. |
| `skills/python-pptx-generator/SKILL.md` | Generating runnable `python-pptx` scripts to build structured PowerPoint slide decks. |
| `skills/frontend-slides/SKILL.md` | Converting `.ppt`/`.pptx` decks or outlines into zero-dependency interactive HTML presentations. |
| `skills/2slides-ppt-generator/SKILL.md` | Summarizing documents into presentation decks with narration/PDF export via the 2slides API. |
| `skills/libreoffice/SKILL.md` | LibreOffice automation & format conversion across nested `writer`, `calc`, `impress`, `draw`, and `base` sub-skills. |
| `skills/office-productivity/SKILL.md` | End-to-end office document, spreadsheet, presentation, and LibreOffice/MS Office format conversion workflow bundle. |

### File Management & Trust Metadata
| Skill | Read when |
|---|---|
| `skills/file-organizer/SKILL.md` | Analyzing directory clutter, finding duplicate files, renaming, and structuring local files. |
| `skills/akf-trust-metadata/SKILL.md` | Stamping, inspecting, and auditing AI provenance/trust/compliance metadata (`EU AI Act`, `HIPAA`, `SOX`) across 20+ file formats (`DOCX`, `PDF`, images, code). |

## Usage

When working in this skill pack:
1. Run `python tools/doc_convert.py profile --pretty` (or `skills/device-aware-ocr-router/scripts/system_profiler.py`) before choosing a local OCR engine or spawning parallel workers, so engine choice and concurrency match the host's real CPU, RAM, and GPU VRAM.
2. Classify the source format and desired output (LLM-ready Markdown vs human-formatted Office/PDF vs media/archive conversion) using `document_inspector.py` / `ocr_recommender.py`.
3. Read the matching `skills/<skill>/SKILL.md` file (and `agents/` specs for sequential GPU vs parallel CPU/API batch execution).
4. Respect licensing, local path isolation, and tool-selection guardrails (avoid heavy VLM OCR when native text/OOXML extraction suffices, and never exceed `max_parallel_gpu_workers` on low/mid-VRAM GPUs).
