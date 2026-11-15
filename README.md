# Document & Conversion Skills (`doc-convert-skills`)

A standardized collection of **23 OCR, document processing, and universal file conversion skills**, plus **device-aware OCR routing CLI tools** (`tools/doc_convert.py`) and **multi-agent orchestration specs** built for Antigravity, Claude Code, Codex, Gemini CLI, Cursor, and Windsurf.

## Categories

- **OCR & Multi-Format Converters (7)**: `device-aware-ocr-router` (hardware/OS/GPU/RAM profiler, PDF digital-vs-scanned inspector, optimal OCR selector, bounded runner & validator), `windows-winrt-ocr` (built-in Windows 10/11 `Windows.Media.Ocr` zero-VRAM local OCR + hybrid PDF extractor), `chandra-ocr` (Chandra OCR 2 for scanned PDFs/math/tables/handwriting), `tizen-subtitle-translator` (real-time HDMI subtitle band OCR via Tesseract 5.5 + MNN CRNN & LAN/DeepL translation), `markitdown` (Microsoft MarkItDown CLI + `markitdown-mcp` + `markitdown-ocr`), `convertx` (self-hosted 1,000+ format converter via Docker/Bun), `audio-transcriber` (Whisper audio/video to Markdown & SRT/VTT)
- **PDF Intelligence & Structured Extraction (4)**: `pdf-conversion-router`, `pdf-official`, `doc2math` (document-to-mathematical specification JSON), `obsidian-markdown` (Obsidian Flavored Markdown formatting, wikilinks, embeds, callouts)
- **Office Suites, Spreadsheets & Slides (10)**: `docx-official`, `xlsx-official`, `bilig-workpaper`, `googlesheets-automation`, `pptx-official`, `python-pptx-generator`, `frontend-slides`, `2slides-ppt-generator`, `libreoffice` (`writer`, `calc`, `impress`, `draw`, `base`), `office-productivity`
- **File Management & Trust Metadata (2)**: `file-organizer`, `akf-trust-metadata` (AI provenance/compliance metadata embedded into DOCX/PDF/images)

## Structure

```text
doc-convert-skills/
├── AGENTS.md
├── CLAUDE.md
├── README.md
├── plugin.json
├── gemini-extension.json
├── .claude-plugin/plugin.json
├── .codex-plugin/plugin.json
├── agents/
│   ├── README.md
│   ├── batch-orchestrator-agent.md
│   ├── doc-profiler-agent.md
│   ├── fidelity-validator-agent.md
│   └── ocr-conversion-worker.md
├── tools/
│   └── doc_convert.py
├── tests/
│   └── test_device_aware_ocr_router.py
└── skills/
    └── <skill-name>/SKILL.md (23 skills)
```

## Quick Start (Device-Aware OCR Routing)

```bash
# 1. Inspect host hardware, GPU VRAM, Windows WinRT langs, and installed OCR/PDF tools
python tools/doc_convert.py profile --pretty

# 2. Recommend the best OCR/conversion engine for a target file or folder
python tools/doc_convert.py recommend path/to/doc.pdf --lang tur+eng --complexity tables

# 3. Preview or run conversion with hardware-bounded parallelism & quality gates
python tools/doc_convert.py convert path/to/doc.pdf --dry-run
```
