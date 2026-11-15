---
name: markitdown
description: Convert PDF, DOCX, PPTX, XLSX, XLS, images, audio, HTML, CSV/JSON/XML, ZIP archives, EPUB, and YouTube URLs into clean, token-efficient Markdown for LLMs using Microsoft MarkItDown (`markitdown`, `markitdown-mcp`, and `markitdown-ocr`). Use when extracting LLM-ready text from office docs, scanned files, or local URIs via CLI, Python, or MCP.
license: MIT
metadata:
  homepage: "https://github.com/microsoft/markitdown"
  repository: "https://github.com/microsoft/markitdown"
---

# Microsoft MarkItDown (`microsoft/markitdown`)

Use this skill when converting files into structured, token-efficient **Markdown** for LLMs and RAG pipelines using **MarkItDown** (`Python 3.10–3.14`, MIT).

## Supported Inputs
PDF, PowerPoint (`.pptx`), Word (`.docx`), Excel (`.xlsx`, `.xls`), Images (EXIF + LLM captioning / OCR), Audio (EXIF + transcription), HTML, text data (`CSV`, `JSON`, `XML`), `ZIP` archives, `EPUB`, Outlook messages, and YouTube URLs.

## Installation

```bash
# Install everything (PDF, Office, audio, YouTube, Azure extras)
pip install "markitdown[all]"

# Or install only needed format extras:
pip install "markitdown[pdf,docx,pptx,xlsx]"
# Available extras: all, pptx, docx, xlsx, xls, pdf, outlook,
#   az-doc-intel, az-content-understanding, audio-transcription, youtube-transcription

# Optional MCP server & LLM-Vision OCR plugin:
pip install markitdown-mcp
pip install markitdown-ocr openai
```

## CLI Usage

```bash
# Convert to stdout or file
markitdown path-to-file.pdf > document.md
markitdown path-to-file.pdf -o document.md

# Pipe from stdin
cat path-to-file.pdf | markitdown

# Plugins (disabled by default)
markitdown --list-plugins
markitdown --use-plugins document.pdf

# With markitdown-ocr (OCR on images inside PDF/DOCX/PPTX/XLSX via OpenAI-compatible Vision LLM)
markitdown document.pdf --use-plugins --llm-client openai --llm-model gpt-4o

# With Azure Document Intelligence or Azure Content Understanding
markitdown path-to-file.pdf -o document.md -d -e "<document_intelligence_endpoint>"
markitdown path-to-file.pdf --use-cu --cu-endpoint "<content_understanding_endpoint>"
```

## Python API

### Basic Conversion
```python
from markitdown import MarkItDown

md = MarkItDown(enable_plugins=False)
result = md.convert("report.xlsx")
print(result.markdown)
```

### With `markitdown-ocr` Plugin & Vision LLM
```python
from markitdown import MarkItDown
from openai import OpenAI

md = MarkItDown(
    enable_plugins=True,
    llm_client=OpenAI(max_retries=5),
    llm_model="gpt-4o",
    llm_prompt="Extract all text from this image, preserving table structure.",
)
result = md.convert("document_with_images.pdf")
print(result.markdown)
```

### Narrower Helpers for Untrusted Contexts
Prefer `convert_local()` or `convert_stream()` over generic `convert()` when accepting untrusted inputs.

## MCP Server (`markitdown-mcp`)

Exposes `convert_to_markdown(uri)` supporting `http:`, `https:`, `file:`, and `data:` URIs:

```bash
# STDIO (default)
markitdown-mcp

# Streamable HTTP / SSE (localhost only by default)
markitdown-mcp --http --host 127.0.0.1 --port 3001
```

Docker STDIO mount for Claude Desktop / MCP clients:
```bash
docker run -i --rm -v /path/to/data:/workdir markitdown-mcp:latest
```

## Guardrails

- MarkItDown optimizes for **LLM/RAG text analysis**, not pixel-accurate visual formatting for human print output.
- If `markitdown-ocr` loads without an `llm_client`, OCR is silently skipped and built-in non-OCR conversion runs instead.
- Keep `markitdown-mcp --http` bound to `127.0.0.1` so arbitrary local `file:` URIs are not exposed on a network interface.
