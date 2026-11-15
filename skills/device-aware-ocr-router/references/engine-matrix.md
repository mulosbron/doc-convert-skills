# Device-Aware OCR & Document Engine Matrix

## 1. Hardware Tiers & Safe Concurrency

| Tier | Criteria | Safe Parallel GPU Workers | Safe Parallel CPU Workers | Recommended Local OCR Engines |
|---|---|---|---|---|
| `gpu_datacenter` | CUDA VRAM >= 22 GB | `max(1, vram // 12)` | Up to 6 | `chandra-ocr-vllm`, `chandra-ocr-hf`, `surya-marker`, `docling` |
| `gpu_high` | CUDA VRAM 12–21 GB | `1` | Up to 6 | `surya-marker`, `chandra-ocr-hf` (`--batch-size 1`), `docling` |
| `gpu_mid` | CUDA VRAM 6–11 GB (e.g. 8 GB laptop GPU) | `1` (sequential!) | Up to 6 | `surya-marker`, `docling`, `ollama-vision-ocr` (4-bit), `rapidocr-onnx`; avoid full-precision `chandra --method hf` on large batches |
| `gpu_low` | CUDA VRAM < 6 GB | `1` | Up to 4 | `rapidocr-onnx`, `paddleocr`, `ocrmypdf-tesseract` |
| `apple_silicon_high` | macOS `arm64`, RAM >= 24 GB | `1` | Up to 6 | `surya-marker` (MPS), `docling`, `chandra-ocr-hf` (`--batch-size 1`), `ocrmypdf-tesseract` |
| `apple_silicon_std` | macOS `arm64`, RAM < 24 GB | `1` | Up to 4 | `surya-marker` (MPS), `docling`, `rapidocr-onnx`, `ocrmypdf-tesseract` |
| `cpu_high` | No GPU, RAM >= 16 GB, >= 8 threads | `0` | Up to 6 | `windows-winrt-ocr` (Windows), `rapidocr-onnx`, `docling`, `ocrmypdf-tesseract` |
| `cpu_mid` / `cpu_low` | No GPU, RAM < 16 GB | `0` | 1–3 | `windows-winrt-ocr` (Windows), `rapidocr-onnx`, `ocrmypdf-tesseract` (or `markitdown-cloud-ocr` if cloud allowed) |

## 2. Document Type Routing

| Document Class | First Choice (Zero/Low Cost) | High-Fidelity / Complex Fallback |
|---|---|---|
| **Digital PDF** (selectable text) | `opendataloader-pdf` (`markdown-with-html`) -> `pymupdf-pdfplumber` -> `markitdown` | `docling` (only if complex multi-span tables fail native extraction) |
| **Scanned PDF / Image** (tables, math, handwriting, forms) | On >=22 GB VRAM or active vLLM: `chandra-ocr-vllm`. On 8 GB VRAM: `surya-marker` / `docling` / `ollama-vision-ocr` | `rapidocr-onnx` -> `ocrmypdf-tesseract` (`-l tur+eng`) -> `markitdown-cloud-ocr` |
| **Searchable PDF Output** (`--goal searchable-pdf`) | `ocrmypdf -l <lang> --deskew --skip-text` | Pre-process skew/contrast with ImageMagick/OpenCV then retry `ocrmypdf` |
| **Office Docs** (`.docx`, `.xlsx`, `.pptx`) | `markitdown` (LLM Markdown) or `docx-official` / `xlsx-official` / `pptx-official` | `libreoffice` (`soffice --headless --convert-to pdf`) |
| **Audio / Video** | `faster-whisper` (`float16` CUDA if VRAM >= 4 GB, else `int8` CPU) | OpenAI/cloud transcription if `allow-cloud` |

## 3. Turkish & Multilingual Notes

- **Tesseract / OCRmyPDF**: Verify `tur` appears in `tesseract --list-langs` before running `-l tur+eng`. On Windows, install via UB-Mannheim Tesseract installer or `winget install UB-Mannheim.TesseractOCR` and select Turkish traineddata.
- **Surya / Marker / Chandra OCR 2 / RapidOCR / Docling**: Native multilingual support including Turkish diacritics (`ç, ğ, ı, İ, ö, ş, ü`). Always validate UTF-8 output for `\ufffd` replacement characters or missing diacritics.
