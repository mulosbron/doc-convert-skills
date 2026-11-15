---
name: chandra-ocr
description: State-of-the-art OCR (`chandra-ocr` v0.2.0 / Chandra OCR 2) that converts PDFs and images into structured Markdown, HTML, and JSON while preserving layout, tables, math, checkboxes/forms, handwriting, and 90+ languages. Use when extracting text/tables/math from scanned documents via CLI (`chandra`, `chandra_vllm`, `chandra_app`) or Python (`InferenceManager`).
version: "0.2.0"
license: Apache-2.0
metadata:
  homepage: "https://documentation.datalab.to"
  repository: "https://github.com/datalab-to/chandra"
---

# Chandra OCR 2 (`datalab-to/chandra`)

Use this skill when converting scanned PDFs, complex multi-column documents, handwritten pages, forms with checkboxes, mathematical equations, or multilingual documents (90+ languages) into structured **Markdown**, **HTML**, and **JSON** using **Chandra OCR 2** (`Python >=3.10`, code Apache-2.0, model weights modified OpenRAIL-M).

## Installation

```bash
# Base install (recommended with remote/local vLLM server)
pip install chandra-ocr

# Local HuggingFace inference (adds torch, torchvision, transformers, accelerate)
pip install "chandra-ocr[hf]"

# Interactive Streamlit web UI
pip install "chandra-ocr[app]"

# Full extras
pip install "chandra-ocr[all]"
```

From source with `uv`:
```bash
git clone https://github.com/datalab-to/chandra.git
cd chandra && uv sync
```

## CLI Usage

Supported input formats: `.pdf`, `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.tiff`, `.bmp` (single file or directory).

```bash
# Launch vLLM server container (GPU) + run OCR
chandra_vllm
chandra input.pdf ./output --method vllm

# Run locally with HuggingFace Transformers
chandra ./documents ./output --method hf

# Selective PDF pages and header/footer preservation
chandra input.pdf ./output --page-range "1-5,7,9-12" --include-headers-footers

# Launch interactive Streamlit app
chandra_app
```

### CLI Options
- `--method [hf|vllm]` — Inference backend (default: `vllm`)
- `--page-range TEXT` — Page selection for PDFs (e.g., `"1-5,7,9-12"`)
- `--max-output-tokens INTEGER` — Max tokens per page
- `--max-workers INTEGER` — Parallel workers for `vllm`
- `--include-images / --no-images` — Extract and save images (default: include)
- `--include-headers-footers / --no-headers-footers` — Include page headers/footers (default: exclude)
- `--batch-size INTEGER` — Pages per batch (default: `28` for `vllm`, `1` for `hf`)

### Output Structure
Each processed file writes a subfolder under the target output directory containing:
- `<filename>.md` — Structured Markdown
- `<filename>.html` — Layout HTML
- `<filename>_metadata.json` — Page info, token counts, and chunk metadata
- Extracted images saved inside the output directory

## Python API (`InferenceManager`)

```python
from chandra.input import load_file
from chandra.model import InferenceManager
from chandra.model.schema import BatchInputItem

images = load_file("input.pdf", config={})
batch = [BatchInputItem(image=img, prompt_type="ocr_layout") for img in images]

manager = InferenceManager(method="vllm")  # or method="hf"
results = manager.generate(batch)

for page in results:
    print(page.markdown)
    print(page.html)
    print(page.chunks)
```

## Configuration (`local.env` or Environment Variables)

```bash
MODEL_CHECKPOINT=datalab-to/chandra-ocr-2
MAX_OUTPUT_TOKENS=12384
VLLM_API_BASE=http://localhost:8000/v1
VLLM_MODEL_NAME=chandra
VLLM_GPUS=0
```

## Guardrails

- Before running Chandra locally, check device VRAM/RAM via `skills/device-aware-ocr-router/scripts/system_profiler.py`. On GPUs with `<12 GB` VRAM (e.g. 8 GB laptops) without a remote vLLM server, avoid large `--method hf` batches to prevent CUDA OOM; use `--batch-size 1 --page-range` chunks or route via `device-aware-ocr-router` to `surya-marker`, `docling`, or `rapidocr-onnx`.
- Prefer `--method vllm` for multi-page or batch throughput; reserve `--method hf` for environments without a vLLM endpoint.
- Check commercial licensing terms before commercial self-hosting (code is Apache-2.0; model weights use modified OpenRAIL-M).
