#!/usr/bin/env python3
"""Hardware- and document-aware OCR & conversion route recommender."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from document_inspector import inspect_target  # noqa: E402
from system_profiler import collect_system_profile  # noqa: E402


def _has_cli(profile: dict[str, Any], name: str) -> bool:
    return name in profile.get("tools", {}).get("cli", {})


def _has_mod(profile: dict[str, Any], name: str) -> bool:
    return bool(profile.get("tools", {}).get("python_modules", {}).get(name))


def _tesseract_lang_flag(lang: str) -> str:
    if not lang or lang == "auto":
        return "eng"
    return lang


def _build_ocr_candidates(
    profile: dict[str, Any],
    goal: str,
    privacy: str,
    quality: str,
    lang: str,
    complexity: str,
) -> list[dict[str, Any]]:
    """Score and rank OCR engines for the given device profile and document traits."""
    cls_i = profile["classification"]
    tier = cls_i["tier"]
    vram_gb = float(cls_i.get("max_cuda_vram_gb", 0.0))
    ram_gb = float(profile.get("memory", {}).get("total_gb", 0.0))
    accel = cls_i.get("primary_accelerator", "cpu")
    svc = profile.get("services", {})
    vllm_active = bool(svc.get("vllm", {}).get("active"))
    ollama_vision = svc.get("ollama", {}).get("vision_models", [])
    cloud_keys = svc.get("cloud_keys_present", {})
    has_cloud = any(cloud_keys.values())
    tess_langs = profile.get("tools", {}).get("tesseract_langs", [])
    tess_lang = _tesseract_lang_flag(lang)

    is_heavy_layout = complexity in ("tables", "math", "handwriting", "forms", "medical")
    candidates: list[dict[str, Any]] = []

    # 1. Chandra OCR 2 via vLLM endpoint (remote or local high-VRAM server)
    if vllm_active or tier == "gpu_datacenter":
        score = 96 if (is_heavy_layout or quality == "max") else 86
        if vllm_active:
            score += 6
        installed = _has_cli(profile, "chandra") or _has_mod(profile, "chandra")
        candidates.append(
            {
                "engine": "chandra-ocr-vllm",
                "skill": "chandra-ocr",
                "score": score,
                "installed": installed and (vllm_active or _has_cli(profile, "chandra_vllm")),
                "device_fit": "optimal" if vllm_active or vram_gb >= 22.0 else "requires-vllm-server",
                "command_template": "chandra {input} {output_dir} --method vllm --max-workers {workers}",
                "install_hint": "pip install chandra-ocr",
                "recommended_workers": 4 if vllm_active else max(1, cls_i.get("max_parallel_gpu_workers", 1)),
                "reason": (
                    "Active vLLM endpoint or >=22 GB VRAM detected; Chandra OCR 2 delivers top layout/table/math/handwriting accuracy."
                ),
            }
        )

    # 2. Chandra OCR 2 local HuggingFace (optimal >=16 GB VRAM / >=24 GB Apple Silicon; tight fallback on 8 GB if already installed)
    chandra_hf_installed = (_has_cli(profile, "chandra") or _has_mod(profile, "chandra")) and _has_mod(profile, "torch")
    if tier in ("gpu_datacenter", "gpu_high", "apple_silicon_high") or (tier == "gpu_mid" and chandra_hf_installed):
        batch_size = 4 if vram_gb >= 22.0 else 1
        if tier == "gpu_mid":
            hf_score = 68
            device_fit = "tight-vram-risk"
            hf_reason = (
                f"Installed locally, but {vram_gb} GB VRAM is tight for full-precision Chandra HF; "
                "use `--batch-size 1` with `--page-range` chunks or prefer Surya/Docling/RapidOCR."
            )
        else:
            hf_score = 88 if is_heavy_layout else 78
            device_fit = "good" if vram_gb >= 16.0 else "tight-memory"
            hf_reason = "Local HF inference fits high-VRAM CUDA or >=24 GB Apple Silicon; keep workers=1 to avoid OOM."
        candidates.append(
            {
                "engine": "chandra-ocr-hf",
                "skill": "chandra-ocr",
                "score": hf_score,
                "installed": chandra_hf_installed,
                "device_fit": device_fit,
                "command_template": f"chandra {{input}} {{output_dir}} --method hf --batch-size {batch_size}",
                "install_hint": 'pip install "chandra-ocr[hf]"',
                "recommended_workers": 1,
                "reason": hf_reason,
            }
        )

    # 3. Surya / Marker-PDF (sweet spot for 6-12 GB VRAM like RTX 4070 Laptop 8 GB, or MPS)
    if accel in ("cuda", "mps") or ram_gb >= 12.0:
        score = 91 if (tier == "gpu_mid" and is_heavy_layout) else (84 if accel in ("cuda", "mps") else 68)
        if quality == "fast" and accel == "cpu":
            score -= 10
        installed = _has_cli(profile, "marker_single") or _has_cli(profile, "surya_ocr") or _has_mod(profile, "surya")
        candidates.append(
            {
                "engine": "surya-marker",
                "skill": "device-aware-ocr-router",
                "score": score,
                "installed": installed,
                "device_fit": "optimal" if tier in ("gpu_mid", "gpu_high", "apple_silicon_std", "apple_silicon_high") else "cpu-heavy",
                "command_template": "marker_single {input} --output_dir {output_dir}",
                "install_hint": "pip install marker-pdf surya-ocr",
                "recommended_workers": 1 if accel in ("cuda", "mps") else 1,
                "reason": (
                    f"Fits {vram_gb or ram_gb} GB {'VRAM' if accel == 'cuda' else 'RAM'} comfortably (~3-5 GB VRAM) "
                    "with strong multilingual, math, and table extraction."
                ),
            }
        )

    # 4. Docling (IBM layout + table + RapidOCR/Tesseract)
    docling_score = 87 if (complexity == "tables" or tier in ("gpu_mid", "cpu_high", "apple_silicon_std")) else 77
    candidates.append(
        {
            "engine": "docling",
            "skill": "device-aware-ocr-router",
            "score": docling_score,
            "installed": _has_cli(profile, "docling") or _has_mod(profile, "docling"),
            "device_fit": "optimal" if ram_gb >= 12.0 else "tight-ram",
            "command_template": "docling {input} --to md --output {output_dir}",
            "install_hint": "pip install docling",
            "recommended_workers": 1 if accel == "cuda" else min(2, cls_i.get("max_parallel_cpu_workers", 1)),
            "reason": "Strong table structure recovery and layout analysis with low VRAM (~2-4 GB) or CPU fallback.",
        }
    )

    # 5. Local Ollama Vision OCR (4-bit quantized VLM if Ollama already has a vision model)
    if ollama_vision:
        candidates.append(
            {
                "engine": "ollama-vision-ocr",
                "skill": "device-aware-ocr-router",
                "score": 85 if is_heavy_layout else 76,
                "installed": True,
                "device_fit": "optimal",
                "command_template": f"# Use Ollama vision model '{ollama_vision[0]}' page-by-page",
                "install_hint": f"ollama pull {ollama_vision[0]}",
                "recommended_workers": 1,
                "reason": f"Local quantized vision model ready in Ollama ({', '.join(ollama_vision[:3])}); fits mid-VRAM GPUs.",
            }
        )

    # 6. RapidOCR (ONNX Runtime — ultra-fast on CPU & low/mid GPU, great for batch!)
    rapid_score = 85 if (tier in ("cpu_low", "cpu_mid", "gpu_low") or quality == "fast") else 79
    if _has_mod(profile, "rapidocr_onnxruntime") or _has_mod(profile, "onnxruntime"):
        rapid_score += 4
    candidates.append(
        {
            "engine": "rapidocr-onnx",
            "skill": "device-aware-ocr-router",
            "score": rapid_score,
            "installed": _has_mod(profile, "rapidocr_onnxruntime"),
            "device_fit": "optimal",
            "command_template": "python doc_convert_runner.py {input} --engine rapidocr-onnx --output {output_dir}",
            "install_hint": "pip install rapidocr-onnxruntime pymupdf",
            "recommended_workers": cls_i.get("max_parallel_cpu_workers", 1),
            "reason": "Lightweight ONNX OCR (~300 MB RAM); ideal on CPU-only devices or high-throughput parallel batches.",
        }
    )

    # 7. OCRmyPDF / Tesseract (best for searchable-pdf goal, low RAM, Turkish/90+ langs)
    tess_installed = _has_cli(profile, "tesseract") or _has_cli(profile, "ocrmypdf")
    tess_score = 94 if goal == "searchable-pdf" else (82 if tier in ("cpu_low", "cpu_mid") else 72)
    if lang != "auto" and any(part in tess_langs for part in lang.split("+")):
        tess_score += 4
    candidates.append(
        {
            "engine": "ocrmypdf-tesseract",
            "skill": "pdf-official",
            "score": tess_score,
            "installed": tess_installed,
            "device_fit": "optimal",
            "command_template": f"ocrmypdf -l {tess_lang} --deskew --skip-text {{input}} {{output_pdf}}",
            "install_hint": "pip install ocrmypdf  # plus system tesseract-ocr + tesseract-ocr-tur",
            "recommended_workers": cls_i.get("max_parallel_cpu_workers", 1),
            "reason": "Low-memory CPU OCR ideal for searchable PDFs, clean scans, and parallel CPU worker scaling.",
        }
    )

    # 7b. Windows Native WinRT OCR (Windows 10/11 built-in Windows.Media.Ocr — 0 VRAM, 0 model download)
    if profile.get("os", {}).get("system") == "Windows":
        win_ocr_langs = profile.get("tools", {}).get("windows_ocr_langs", [])
        win_installed = len(win_ocr_langs) > 0
        win_score = 90 if (quality == "fast" and not is_heavy_layout) else (85 if not is_heavy_layout else 74)
        if goal == "searchable-pdf":
            win_score -= 12
        candidates.append(
            {
                "engine": "windows-winrt-ocr",
                "skill": "windows-winrt-ocr",
                "score": win_score,
                "installed": win_installed,
                "device_fit": "optimal",
                "command_template": f"python skills/windows-winrt-ocr/scripts/winrt_pdf_ocr.py {{input}} -o {{output_dir}} -l {lang.split('+')[0] or 'tr'}",
                "install_hint": "Built into Windows 10/11 (add OCR language packs in ms-settings:regionlanguage)",
                "recommended_workers": min(4, cls_i.get("max_parallel_cpu_workers", 1)),
                "reason": (
                    f"Built-in Windows.Media.Ocr (0 GB VRAM, installed langs={win_ocr_langs or ['auto']}); "
                    "ideal for fast offline prose/hybrid PDFs without external ML weights."
                ),
            }
        )

    # 8. Cloud Vision via MarkItDown-OCR (only when privacy allows cloud)
    if privacy == "allow-cloud":
        cloud_score = 92 if (has_cloud and is_heavy_layout and tier.startswith("cpu")) else (84 if has_cloud else 55)
        candidates.append(
            {
                "engine": "markitdown-cloud-ocr",
                "skill": "markitdown",
                "score": cloud_score,
                "installed": _has_cli(profile, "markitdown") and has_cloud,
                "device_fit": "cloud-api",
                "command_template": "markitdown {input} --use-plugins -o {output_md}",
                "install_hint": "pip install markitdown[all] markitdown-ocr openai",
                "recommended_workers": cls_i.get("max_parallel_api_workers", 4),
                "reason": "Offloads heavy VLM OCR to cloud Vision API; requires zero local VRAM and scales via parallel API workers.",
            }
        )

    # Sort by score descending, then installed status
    candidates.sort(key=lambda c: (c["score"], 1 if c["installed"] else 0), reverse=True)
    return candidates


def recommend_for_document(
    profile: dict[str, Any],
    doc_info: dict[str, Any] | None = None,
    goal: str = "markdown",
    privacy: str = "local-only",
    quality: str = "balanced",
    lang: str = "eng",
    complexity: str = "standard",
    batch_count: int = 1,
) -> dict[str, Any]:
    """Produce a complete, device-aware OCR & conversion recommendation."""
    cls_i = profile["classification"]
    category = (doc_info or {}).get("category", "pdf")
    pdf_info = (doc_info or {}).get("pdf", {})
    pdf_kind = pdf_info.get("pdf_kind", "scanned")
    ocr_required = bool((doc_info or {}).get("ocr_required", category in ("pdf", "image")))
    warnings: list[str] = []

    if cls_i["tier"] == "gpu_mid" and _has_cli(profile, "chandra") and not profile["services"]["vllm"]["active"]:
        warnings.append(
            f"Detected {cls_i['max_cuda_vram_gb']} GB VRAM (gpu_mid) with chandra installed but no active vLLM server: "
            "avoid full-precision `chandra --method hf` for large batches to prevent CUDA OOM; prefer surya-marker, docling, rapidocr-onnx, or a remote/quantized vLLM server."
        )

    if category == "pdf" and not ocr_required and pdf_kind == "digital":
        # Native digital PDF: never waste GPU VLM OCR!
        primary_installed = _has_cli(profile, "opendataloader-pdf")
        candidates = [
            {
                "engine": "opendataloader-pdf",
                "skill": "pdf-conversion-router",
                "score": 98,
                "installed": primary_installed,
                "device_fit": "optimal",
                "command_template": "opendataloader-pdf -f markdown-with-html --image-output off {input}",
                "install_hint": "pip install opendataloader-pdf",
                "recommended_workers": cls_i.get("max_parallel_cpu_workers", 1),
                "reason": "Digital PDF with selectable text detected; native structural extraction is faster and cleaner than OCR.",
            },
            {
                "engine": "pymupdf-pdfplumber",
                "skill": "pdf-official",
                "score": 90,
                "installed": _has_mod(profile, "fitz") or _has_mod(profile, "pdfplumber"),
                "device_fit": "optimal",
                "command_template": "python doc_convert_runner.py {input} --engine pymupdf-pdfplumber --output {output_dir}",
                "install_hint": "pip install pymupdf pdfplumber",
                "recommended_workers": cls_i.get("max_parallel_cpu_workers", 1),
                "reason": "Installed Python native PDF + table extractor; zero GPU overhead.",
            },
            {
                "engine": "markitdown",
                "skill": "markitdown",
                "score": 82,
                "installed": _has_cli(profile, "markitdown") or _has_mod(profile, "markitdown"),
                "device_fit": "optimal",
                "command_template": "markitdown {input} -o {output_md}",
                "install_hint": 'pip install "markitdown[pdf]"',
                "recommended_workers": cls_i.get("max_parallel_cpu_workers", 1),
                "reason": "Fast LLM-ready Markdown extraction for simple digital PDFs.",
            },
        ]
    elif category in ("office_word", "office_sheet", "office_slide"):
        skill_map = {
            "office_word": "docx-official",
            "office_sheet": "xlsx-official",
            "office_slide": "pptx-official",
        }
        candidates = [
            {
                "engine": "markitdown" if goal in ("markdown", "markdown-with-html", "text") else "office-native",
                "skill": "markitdown" if goal in ("markdown", "markdown-with-html", "text") else skill_map[category],
                "score": 95,
                "installed": _has_cli(profile, "markitdown") or _has_mod(profile, "openpyxl") or _has_mod(profile, "docx"),
                "device_fit": "optimal",
                "command_template": "markitdown {input} -o {output_md}" if goal.startswith("markdown") else f"# Use {skill_map[category]} / libreoffice",
                "install_hint": 'pip install "markitdown[docx,pptx,xlsx]" python-docx openpyxl python-pptx',
                "recommended_workers": cls_i.get("max_parallel_cpu_workers", 1),
                "reason": "Structured Office document; extract directly via OOXML/MarkItDown without OCR.",
            },
            {
                "engine": "libreoffice-headless",
                "skill": "libreoffice",
                "score": 85,
                "installed": _has_cli(profile, "soffice"),
                "device_fit": "optimal",
                "command_template": "soffice --headless --convert-to pdf {input} --outdir {output_dir}",
                "install_hint": "Install LibreOffice (soffice)",
                "recommended_workers": 1,
                "reason": "High-fidelity Office-to-PDF/ODF conversion via LibreOffice.",
            },
        ]
    elif category == "markup_web":
        candidates = [
            {
                "engine": "markitdown",
                "skill": "markitdown",
                "score": 96,
                "installed": _has_cli(profile, "markitdown") or _has_mod(profile, "markitdown"),
                "device_fit": "optimal",
                "command_template": "markitdown {input} -o {output_md}",
                "install_hint": "pip install markitdown",
                "recommended_workers": cls_i.get("max_parallel_cpu_workers", 1),
                "reason": "Markup/text/EPUB input requires no OCR; convert directly via MarkItDown or Pandoc.",
            }
        ]
    elif category == "audio_video":
        use_cuda = cls_i["primary_accelerator"] == "cuda" and cls_i.get("max_cuda_vram_gb", 0.0) >= 4.0
        compute_type = "float16" if use_cuda else "int8"
        device_flag = "cuda" if use_cuda else "cpu"
        candidates = [
            {
                "engine": "faster-whisper",
                "skill": "audio-transcriber",
                "score": 95,
                "installed": _has_mod(profile, "faster_whisper"),
                "device_fit": "optimal",
                "command_template": f"# faster-whisper device={device_flag} compute_type={compute_type}",
                "install_hint": "pip install faster-whisper",
                "recommended_workers": 1 if use_cuda else min(2, cls_i.get("max_parallel_cpu_workers", 1)),
                "reason": f"Selected {device_flag} ({compute_type}) based on device accelerator profile.",
            }
        ]
    else:
        # Scanned PDF, hybrid PDF, or image -> hardware-aware OCR ranking!
        candidates = _build_ocr_candidates(
            profile=profile,
            goal=goal,
            privacy=privacy,
            quality=quality,
            lang=lang,
            complexity=complexity,
        )

    best = candidates[0]
    installed_candidates = [c for c in candidates if c["installed"]]
    ready_now = installed_candidates[0] if installed_candidates else None

    rec_workers = int(best.get("recommended_workers", 1))
    if batch_count <= 1:
        exec_mode = "single"
        effective_workers = 1
    elif rec_workers <= 1:
        exec_mode = "sequential"
        effective_workers = 1
    else:
        exec_mode = "parallel_subagents"
        effective_workers = min(batch_count, rec_workers)

    return {
        "device_summary": {
            "tier": cls_i["tier"],
            "accelerator": cls_i["primary_accelerator"],
            "vram_gb": cls_i["max_cuda_vram_gb"],
            "ram_gb": profile["memory"]["total_gb"],
            "logical_cores": profile["cpu"]["logical_cores"],
        },
        "document_summary": {
            "category": category,
            "pdf_kind": pdf_kind if category == "pdf" else None,
            "ocr_required": ocr_required,
            "goal": goal,
            "privacy": privacy,
            "quality": quality,
            "complexity": complexity,
            "lang": lang,
        },
        "recommended": best,
        "ready_now": ready_now,
        "alternatives": candidates[1:5],
        "orchestration": {
            "execution_mode": exec_mode,
            "max_parallel_workers": effective_workers,
            "batch_count": batch_count,
            "note": (
                "Single file execution."
                if exec_mode == "single"
                else (
                    "Run sequentially (1 worker) so GPU VRAM / local model memory does not thrash or OOM."
                    if exec_mode == "sequential"
                    else f"Safe to fan out up to {effective_workers} parallel workers/subagents."
                )
            ),
        },
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Recommend optimal OCR/conversion route for this device.")
    parser.add_argument("target", nargs="?", default=None, help="Optional file or directory to inspect.")
    parser.add_argument("--goal", default="markdown", choices=("markdown", "markdown-with-html", "html", "json", "text", "docx", "searchable-pdf"))
    parser.add_argument("--privacy", default="local-only", choices=("local-only", "allow-cloud"))
    parser.add_argument("--quality", default="balanced", choices=("fast", "balanced", "max"))
    parser.add_argument("--lang", default="eng", help="Language hint (e.g. eng, tur, tur+eng).")
    parser.add_argument("--complexity", default="standard", choices=("standard", "tables", "math", "handwriting", "forms", "medical", "slides"))
    parser.add_argument("--doc-type", default=None, choices=("scanned-pdf", "digital-pdf", "image", "office-doc", "audio"), help="Synthetic doc type when no target path is given.")
    parser.add_argument("--no-network-probe", action="store_true", help="Skip localhost vLLM/Ollama probe.")
    args = parser.parse_args()

    profile = collect_system_profile(target_path=args.target, skip_network_probe=args.no_network_probe)

    doc_info: dict[str, Any] | None = None
    batch_count = 1
    if args.target:
        inspected = inspect_target(args.target)
        if "error" in inspected:
            print(json.dumps(inspected, indent=2))
            return 1
        batch_count = max(1, inspected["count"])
        if inspected["files"]:
            # Pick most demanding file (prefer OCR-required PDF/image) for top-level route preview
            files_sorted = sorted(
                inspected["files"],
                key=lambda f: (1 if f.get("ocr_required") else 0, float(f.get("size_mb", 0.0))),
                reverse=True,
            )
            doc_info = files_sorted[0]
    elif args.doc_type:
        synthetic_map = {
            "scanned-pdf": {"category": "pdf", "ocr_required": True, "pdf": {"pdf_kind": "scanned"}},
            "digital-pdf": {"category": "pdf", "ocr_required": False, "pdf": {"pdf_kind": "digital"}},
            "image": {"category": "image", "ocr_required": True},
            "office-doc": {"category": "office_word", "ocr_required": False},
            "audio": {"category": "audio_video", "ocr_required": False},
        }
        doc_info = synthetic_map[args.doc_type]

    rec = recommend_for_document(
        profile=profile,
        doc_info=doc_info,
        goal=args.goal,
        privacy=args.privacy,
        quality=args.quality,
        lang=args.lang,
        complexity=args.complexity,
        batch_count=batch_count,
    )
    print(json.dumps(rec, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
