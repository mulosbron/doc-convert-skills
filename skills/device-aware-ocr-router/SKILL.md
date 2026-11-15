---
name: device-aware-ocr-router
description: >-
  Profiles the current machine's hardware (CPU, RAM, GPU/VRAM, Apple Silicon MPS,
  installed OCR/PDF binaries, local vLLM/Ollama servers, and cloud keys), inspects
  target documents (digital vs scanned PDF, images, Office, audio), selects the
  optimal OCR/conversion engine and safe parallel worker budget, executes
  sequentially or via bounded parallel subagents, and validates output quality.
  Use before running OCR or batch document conversions.
version: "1.0.0"
license: MIT
metadata:
  category: routing-and-orchestration
  triggers: best ocr for this machine, device ocr, system specs ocr, batch document conversion, scanned pdf ocr, hardware aware conversion
---

# Device-Aware OCR & Document Conversion Router

Never guess an OCR engine or spawn unbounded parallel GPU workers without first reading the host device's capabilities and the source document's structure.

## Workflow (Sequential Discovery -> Bounded Execution -> Validation)

### Step 1: Profile the Device
Run the zero-dependency hardware & environment profiler (or `python tools/doc_convert.py profile --pretty`):

```bash
python skills/device-aware-ocr-router/scripts/system_profiler.py --pretty
```

For machine-readable JSON:
```bash
python skills/device-aware-ocr-router/scripts/system_profiler.py
```

Key signals captured:
- **Accelerator & VRAM**: CUDA (`nvidia-smi`), Apple Silicon MPS, ROCm, Windows DirectML, or CPU-only
- **RAM & CPU**: Total/available RAM (GB), physical/logical cores, disk free space
- **Hardware Tier**: `gpu_datacenter` (>=22 GB VRAM), `gpu_high` (12–21 GB), `gpu_mid` (6–11 GB), `gpu_low` (<6 GB), `apple_silicon_high` / `apple_silicon_std`, `cpu_high` / `cpu_mid` / `cpu_low`
- **Installed Binaries & Modules**: `opendataloader-pdf`, `chandra`, `tesseract` (+ installed languages), `windows_ocr_langs` (`Windows.Media.Ocr` WinRT packs on Windows), `ocrmypdf`, `marker_single`/`surya`, `docling`, `rapidocr_onnxruntime`, `markitdown`, `pymupdf`/`pdfplumber`/`pypdf`, `soffice`, `ffmpeg`
- **Active Local Endpoints & Keys**: `VLLM_API_BASE`, Ollama vision models, cloud key booleans (never prints secret values)

### Step 2: Inspect the Target Document(s)
Run the inspector (or `python tools/doc_convert.py inspect "<path>"`):

```bash
python skills/device-aware-ocr-router/scripts/document_inspector.py "<path>"
```

Determines:
- File category (`pdf`, `image`, `office_word`, `office_sheet`, `office_slide`, `audio_video`, `markup_web`)
- For PDFs: samples first, middle, and last pages (never trusting page 1 alone) to classify `digital` (selectable text, no OCR needed) vs `hybrid` vs `scanned` (OCR required).

### Step 3: Choose the Optimal Engine & Concurrency Budget
Run the recommender (or `python tools/doc_convert.py recommend "<path>"`):

```bash
python skills/device-aware-ocr-router/scripts/ocr_recommender.py "<path>" --goal markdown --privacy local-only --lang tur+eng --complexity tables
```

See [Engine Matrix](./references/engine-matrix.md) for the full hardware-tier decision rules. Highlights:
- **Digital PDF**: Always prefer `opendataloader-pdf` -> `pymupdf-pdfplumber` -> `markitdown` (zero OCR cost).
- **Scanned PDF on >=22 GB VRAM or active vLLM**: Prefer `chandra-ocr-vllm` (`chandra-ocr` skill).
- **Scanned PDF on 6–11 GB VRAM (e.g. RTX 4070 Laptop 8 GB)**: Avoid full-precision local `chandra --method hf` on large batches (OOM risk); prefer `surya-marker`, `docling`, `ollama-vision-ocr`, `windows-winrt-ocr` (on Windows for fast prose/hybrid PDFs), or `rapidocr-onnx` — and keep GPU workers at `1`.
- **CPU-only / Low-RAM**: On Windows 10/11, `windows-winrt-ocr` (`Windows.Media.Ocr`) works out of the box with zero downloads and zero VRAM; cross-platform prefer `rapidocr-onnx` or `ocrmypdf-tesseract` (`-l tur+eng`), scaling cleanly across `max_parallel_cpu_workers`.

### Step 4: Execute (Sequential or Bounded Parallel Subagents)
Preview first with `--dry-run`, then execute via `doc_convert_runner.py` (or `python tools/doc_convert.py convert "<path>"`):

```bash
python skills/device-aware-ocr-router/scripts/doc_convert_runner.py "<path>" --output "./converted_output" --dry-run
python skills/device-aware-ocr-router/scripts/doc_convert_runner.py "<path>" --output "./converted_output" --workers auto
```

For multi-document batches requiring LLM/subagent post-processing or custom repair, follow the agent roles in [Batch Orchestrator Agent](../../agents/batch-orchestrator-agent.md):
- **Sequential** when `orchestration.execution_mode == "sequential"` (GPU VRAM contention).
- **Parallel Subagents** up to `orchestration.max_parallel_workers` when running CPU OCR, native digital PDF extraction, or cloud/remote vLLM APIs.

### Step 5: Validation Gate
`doc_convert_runner.py` automatically checks non-empty output, UTF-8 validity, minimum character count, replacement-character (`\ufffd`) garble ratio, and Markdown structure. If a file is flagged `needs_review` or `failed`, hand off to [Fidelity Validator Agent](../../agents/fidelity-validator-agent.md) for targeted retry with the next fallback engine.
