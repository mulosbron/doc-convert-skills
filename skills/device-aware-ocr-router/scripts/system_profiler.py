#!/usr/bin/env python3
"""Cross-platform system & OCR capability profiler (stdlib-only).

Detects OS/architecture, CPU cores/model, RAM, free disk space, GPU/accelerator
(NVIDIA CUDA, Apple Silicon MPS, AMD ROCm, Windows DirectML/WMI), installed
document/OCR CLIs & Python packages, local vLLM/Ollama endpoints, and cloud API
readiness (booleans only, never prints secret values).
"""

from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


CLI_TOOLS: tuple[str, ...] = (
    "opendataloader-pdf",
    "chandra",
    "chandra_vllm",
    "markitdown",
    "tesseract",
    "ocrmypdf",
    "pdftotext",
    "pdfinfo",
    "pdftoppm",
    "soffice",
    "pandoc",
    "ffmpeg",
    "magick",
    "docker",
    "ollama",
    "uv",
    "surya_ocr",
    "marker_single",
    "docling",
    "paddleocr",
)

PYTHON_PACKAGES: tuple[str, ...] = (
    "pypdf",
    "pdfplumber",
    "fitz",
    "pdf2image",
    "pytesseract",
    "rapidocr_onnxruntime",
    "onnxruntime",
    "paddleocr",
    "easyocr",
    "surya",
    "marker",
    "docling",
    "chandra",
    "markitdown",
    "torch",
    "transformers",
    "faster_whisper",
    "openpyxl",
    "docx",
    "pptx",
)


def _run_cmd(cmd: list[str], timeout: float = 3.0) -> tuple[int, str, str]:
    """Run a subprocess safely without raising on missing binaries or timeouts."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, "", ""


def detect_os_info() -> dict[str, Any]:
    """Return normalized OS, architecture, and WSL status."""
    system = platform.system()
    machine = platform.machine().lower()
    is_wsl = False
    if system == "Linux":
        try:
            proc_ver = Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
            is_wsl = "microsoft" in proc_ver or "wsl" in proc_ver
        except OSError:
            pass
    return {
        "system": system,
        "release": platform.release(),
        "machine": machine,
        "is_arm64": machine in ("arm64", "aarch64"),
        "is_wsl": is_wsl,
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
    }


def detect_cpu_info(system: str) -> dict[str, Any]:
    """Detect logical/physical CPU count and brand string."""
    logical = os.cpu_count() or 1
    physical = None
    brand = platform.processor() or ""

    if system == "Windows":
        ps_cmd = (
            "$p = Get-CimInstance Win32_Processor | Select-Object -First 1 Name,NumberOfCores; "
            "if ($p) { \"$($p.Name)|$($p.NumberOfCores)\" }"
        )
        rc, out, _ = _run_cmd(["powershell", "-NoProfile", "-Command", ps_cmd], timeout=4.0)
        if rc == 0 and "|" in out:
            name_part, cores_part = out.split("|", 1)
            if name_part.strip():
                brand = name_part.strip()
            if cores_part.strip().isdigit():
                physical = int(cores_part.strip())
    elif system == "Linux":
        try:
            cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"model name\s*:\s*(.+)", cpuinfo)
            if m:
                brand = m.group(1).strip()
        except OSError:
            pass
        rc, out, _ = _run_cmd(["lscpu"], timeout=2.0)
        if rc == 0:
            cores_match = re.search(r"Core\(s\) per socket:\s*(\d+)", out)
            sockets_match = re.search(r"Socket\(s\):\s*(\d+)", out)
            if cores_match and sockets_match:
                physical = int(cores_match.group(1)) * int(sockets_match.group(1))
    elif system == "Darwin":
        rc, out, _ = _run_cmd(["sysctl", "-n", "machdep.cpu.brand_string"], timeout=2.0)
        if rc == 0 and out:
            brand = out
        rc, out, _ = _run_cmd(["sysctl", "-n", "hw.physicalcpu"], timeout=2.0)
        if rc == 0 and out.isdigit():
            physical = int(out)

    return {
        "brand": brand or "Unknown CPU",
        "logical_cores": logical,
        "physical_cores": physical or max(1, logical // 2),
    }


def detect_memory_info(system: str) -> dict[str, float]:
    """Return total and available RAM in GB using stdlib primitives."""
    total_gb = 0.0
    avail_gb = 0.0

    if system == "Windows":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):  # type: ignore[attr-defined]
            total_gb = stat.ullTotalPhys / (1024**3)
            avail_gb = stat.ullAvailPhys / (1024**3)
    elif system == "Linux":
        try:
            meminfo = Path("/proc/meminfo").read_text(encoding="utf-8", errors="ignore")
            total_m = re.search(r"MemTotal:\s+(\d+)\s+kB", meminfo)
            avail_m = re.search(r"MemAvailable:\s+(\d+)\s+kB", meminfo)
            if total_m:
                total_gb = int(total_m.group(1)) / (1024**2)
            if avail_m:
                avail_gb = int(avail_m.group(1)) / (1024**2)
        except OSError:
            pass
    elif system == "Darwin":
        rc, out, _ = _run_cmd(["sysctl", "-n", "hw.memsize"], timeout=2.0)
        if rc == 0 and out.isdigit():
            total_gb = int(out) / (1024**3)
        rc, vm_out, _ = _run_cmd(["vm_stat"], timeout=2.0)
        if rc == 0 and vm_out:
            page_m = re.search(r"page size of (\d+) bytes", vm_out)
            page_size = int(page_m.group(1)) if page_m else 4096
            free_pages = 0
            for key in ("Pages free", "Pages inactive", "Pages speculative"):
                km = re.search(rf"{key}:\s+(\d+)\.", vm_out)
                if km:
                    free_pages += int(km.group(1))
            avail_gb = (free_pages * page_size) / (1024**3)

    return {
        "total_gb": round(total_gb, 2),
        "available_gb": round(avail_gb, 2),
    }


def detect_disk_info(target_path: str | None = None) -> dict[str, float]:
    """Return free disk space in GB for the workspace/target path."""
    path = Path(target_path) if target_path else Path.cwd()
    if not path.exists():
        path = path.parent if path.parent.exists() else Path.cwd()
    usage = shutil.disk_usage(path)
    return {
        "total_gb": round(usage.total / (1024**3), 2),
        "free_gb": round(usage.free / (1024**3), 2),
    }


def detect_gpus(os_info: dict[str, Any], memory_info: dict[str, float]) -> list[dict[str, Any]]:
    """Detect CUDA, Apple Silicon MPS, ROCm, or WMI/DirectML GPUs."""
    gpus: list[dict[str, Any]] = []

    # 1. NVIDIA CUDA via nvidia-smi
    if shutil.which("nvidia-smi"):
        rc, out, _ = _run_cmd(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free,driver_version",
                "--format=csv,noheader,nounits",
            ],
            timeout=3.0,
        )
        if rc == 0 and out:
            for line in out.splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    try:
                        total_mb = float(parts[1])
                        free_mb = float(parts[2])
                    except ValueError:
                        total_mb = 0.0
                        free_mb = 0.0
                    gpus.append(
                        {
                            "vendor": "nvidia",
                            "backend": "cuda",
                            "name": parts[0],
                            "vram_total_gb": round(total_mb / 1024.0, 2),
                            "vram_free_gb": round(free_mb / 1024.0, 2),
                            "driver": parts[3] if len(parts) > 3 else "",
                        }
                    )

    # 2. Apple Silicon unified memory MPS
    if not gpus and os_info["system"] == "Darwin" and os_info["is_arm64"]:
        gpus.append(
            {
                "vendor": "apple",
                "backend": "mps",
                "name": "Apple Silicon GPU (Unified Memory)",
                "vram_total_gb": round(memory_info.get("total_gb", 0.0) * 0.75, 2),
                "vram_free_gb": round(memory_info.get("available_gb", 0.0) * 0.75, 2),
                "driver": "Metal",
            }
        )

    # 3. AMD ROCm on Linux
    if not gpus and os_info["system"] == "Linux" and shutil.which("rocm-smi"):
        rc, out, _ = _run_cmd(["rocm-smi", "--showproductname", "--showmeminfo", "vram"], timeout=3.0)
        if rc == 0 and out:
            gpus.append(
                {
                    "vendor": "amd",
                    "backend": "rocm",
                    "name": "AMD ROCm GPU",
                    "vram_total_gb": 0.0,
                    "vram_free_gb": 0.0,
                    "driver": "ROCm",
                }
            )

    # 4. Windows WMI fallback (integrated / AMD / Intel Arc without nvidia-smi)
    if not gpus and os_info["system"] == "Windows":
        ps_cmd = (
            "Get-CimInstance Win32_VideoController | "
            "ForEach-Object { \"$($_.Name)|$($_.AdapterRAM)\" }"
        )
        rc, out, _ = _run_cmd(["powershell", "-NoProfile", "-Command", ps_cmd], timeout=4.0)
        if rc == 0 and out:
            for line in out.splitlines():
                if "|" not in line:
                    continue
                name, ram_str = [x.strip() for x in line.split("|", 1)]
                if not name or "microsoft basic" in name.lower():
                    continue
                vram_gb = round(int(ram_str) / (1024**3), 2) if ram_str.isdigit() else 0.0
                vendor = "amd" if "amd" in name.lower() or "radeon" in name.lower() else (
                    "intel" if "intel" in name.lower() else "other"
                )
                gpus.append(
                    {
                        "vendor": vendor,
                        "backend": "directml",
                        "name": name,
                        "vram_total_gb": vram_gb,
                        "vram_free_gb": vram_gb,
                        "driver": "WDDM",
                    }
                )

    return gpus


def detect_installed_tools(system: str = "") -> dict[str, Any]:
    """Detect available OCR/doc CLI binaries, Tesseract/WinRT languages, and Python modules."""
    cli_found: dict[str, str | None] = {tool: shutil.which(tool) for tool in CLI_TOOLS}

    tesseract_langs: list[str] = []
    if cli_found.get("tesseract"):
        rc, out, _ = _run_cmd(["tesseract", "--list-langs"], timeout=2.5)
        if rc == 0 and out:
            tesseract_langs = [
                line.strip()
                for line in out.splitlines()[1:]
                if line.strip() and not line.lower().startswith("list of")
            ]

    windows_ocr_langs: list[str] = []
    if system == "Windows":
        ps_ocr = (
            "[Windows.Media.Ocr.OcrEngine, Windows.Foundation.UniversalApiContract, ContentType = WindowsRuntime] | Out-Null; "
            "[Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag }"
        )
        rc, out, _ = _run_cmd(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_ocr], timeout=4.0)
        if rc == 0 and out:
            windows_ocr_langs = [ln.strip() for ln in out.splitlines() if ln.strip()]

    py_modules: dict[str, bool] = {}
    for mod in PYTHON_PACKAGES:
        try:
            py_modules[mod] = importlib.util.find_spec(mod) is not None
        except (ImportError, ValueError):
            py_modules[mod] = False

    return {
        "cli": {k: v for k, v in cli_found.items() if v is not None},
        "cli_missing": [k for k, v in cli_found.items() if v is None],
        "tesseract_langs": tesseract_langs,
        "windows_ocr_langs": windows_ocr_langs,
        "python_modules": {k: v for k, v in py_modules.items() if v},
        "python_missing": [k for k, v in py_modules.items() if not v],
    }


def _probe_http_json(url: str, timeout: float = 0.4) -> dict[str, Any] | None:
    """Quick localhost HTTP JSON probe returning parsed payload or None."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if 200 <= resp.status < 300:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
    except (OSError, urllib.error.URLError, ValueError, TimeoutError):
        return None
    return None


def detect_services_and_keys(skip_network_probe: bool = False) -> dict[str, Any]:
    """Detect local vLLM/Ollama endpoints and presence (booleans only) of cloud API keys."""
    vllm_base = os.environ.get("VLLM_API_BASE", "http://127.0.0.1:8000/v1").rstrip("/")
    ollama_base = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    if not ollama_base.startswith("http"):
        ollama_base = f"http://{ollama_base}"

    vllm_active = False
    vllm_models: list[str] = []
    ollama_active = False
    ollama_vision_models: list[str] = []

    if not skip_network_probe:
        vllm_payload = _probe_http_json(f"{vllm_base}/models", timeout=0.4)
        if isinstance(vllm_payload, dict) and "data" in vllm_payload:
            vllm_active = True
            vllm_models = [str(m.get("id", "")) for m in vllm_payload.get("data", []) if isinstance(m, dict)]

        ollama_payload = _probe_http_json(f"{ollama_base}/api/tags", timeout=0.4)
        if isinstance(ollama_payload, dict) and "models" in ollama_payload:
            ollama_active = True
            vision_hints = ("vl", "vision", "ocr", "minicpm", "llava", "gemma3", "qwen2.5vl", "qwen3-vl")
            for m in ollama_payload.get("models", []):
                if isinstance(m, dict):
                    name = str(m.get("name", ""))
                    if any(h in name.lower() for h in vision_hints):
                        ollama_vision_models.append(name)

    return {
        "vllm": {
            "endpoint": vllm_base,
            "active": vllm_active,
            "models": vllm_models,
        },
        "ollama": {
            "endpoint": ollama_base,
            "active": ollama_active,
            "vision_models": ollama_vision_models,
        },
        "cloud_keys_present": {
            "openai": bool(os.environ.get("OPENAI_API_KEY")),
            "gemini": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
            "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "azure_doc_intel": bool(os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")),
        },
    }


def classify_hardware_tier(
    os_info: dict[str, Any],
    cpu_info: dict[str, Any],
    memory_info: dict[str, float],
    gpus: list[dict[str, Any]],
) -> dict[str, Any]:
    """Classify device tier and compute safe CPU/GPU parallelism limits."""
    cuda_gpus = [g for g in gpus if g.get("backend") == "cuda"]
    mps_gpus = [g for g in gpus if g.get("backend") == "mps"]
    max_cuda_vram = max((float(g.get("vram_total_gb", 0.0)) for g in cuda_gpus), default=0.0)
    total_ram = float(memory_info.get("total_gb", 0.0))
    logical_cores = int(cpu_info.get("logical_cores", 1))

    if max_cuda_vram >= 22.0:
        tier = "gpu_datacenter"
        gpu_workers = max(1, int(max_cuda_vram // 12))
    elif max_cuda_vram >= 11.5:
        tier = "gpu_high"
        gpu_workers = 1
    elif max_cuda_vram >= 5.5:
        tier = "gpu_mid"
        gpu_workers = 1
    elif max_cuda_vram > 0.0:
        tier = "gpu_low"
        gpu_workers = 1
    elif mps_gpus:
        tier = "apple_silicon_high" if total_ram >= 24.0 else "apple_silicon_std"
        gpu_workers = 1
    elif total_ram >= 16.0 and logical_cores >= 8:
        tier = "cpu_high"
        gpu_workers = 0
    elif total_ram >= 8.0:
        tier = "cpu_mid"
        gpu_workers = 0
    else:
        tier = "cpu_low"
        gpu_workers = 0

    # Leave cores and ~2 GB RAM per worker headroom so parallel subagents don't thrash
    ram_budget_workers = max(1, int(max(2.0, total_ram - 2.0) // 2.5))
    cpu_workers = max(1, min(logical_cores // 2 or 1, ram_budget_workers, 6))

    return {
        "tier": tier,
        "primary_accelerator": (
            "cuda" if cuda_gpus else ("mps" if mps_gpus else ("directml" if gpus else "cpu"))
        ),
        "max_cuda_vram_gb": round(max_cuda_vram, 2),
        "max_parallel_cpu_workers": cpu_workers,
        "max_parallel_gpu_workers": gpu_workers,
        "max_parallel_api_workers": 4,
    }


def collect_system_profile(
    target_path: str | None = None,
    skip_network_probe: bool = False,
) -> dict[str, Any]:
    """Collect complete hardware, tool, and service profile."""
    os_info = detect_os_info()
    cpu_info = detect_cpu_info(os_info["system"])
    memory_info = detect_memory_info(os_info["system"])
    disk_info = detect_disk_info(target_path)
    gpus = detect_gpus(os_info, memory_info)
    tools = detect_installed_tools(os_info["system"])
    services = detect_services_and_keys(skip_network_probe=skip_network_probe)
    classification = classify_hardware_tier(os_info, cpu_info, memory_info, gpus)

    return {
        "os": os_info,
        "cpu": cpu_info,
        "memory": memory_info,
        "disk": disk_info,
        "gpus": gpus,
        "classification": classification,
        "tools": tools,
        "services": services,
    }


def format_pretty(profile: dict[str, Any]) -> str:
    """Format a compact human-readable summary of the device profile."""
    os_i = profile["os"]
    cpu_i = profile["cpu"]
    mem_i = profile["memory"]
    disk_i = profile["disk"]
    cls_i = profile["classification"]
    tools_i = profile["tools"]
    svc_i = profile["services"]

    gpu_lines = [
        f"  - {g['name']} ({g['backend'].upper()}, {g['vram_total_gb']} GB total / {g['vram_free_gb']} GB free)"
        for g in profile["gpus"]
    ] or ["  - None detected (CPU-only mode)"]

    lines = [
        "=== Device & OCR Capability Profile ===",
        f"OS / Arch      : {os_i['system']} {os_i['release']} ({os_i['machine']})"
        + (" [WSL]" if os_i["is_wsl"] else ""),
        f"CPU            : {cpu_i['brand']} ({cpu_i['physical_cores']}C / {cpu_i['logical_cores']}T)",
        f"RAM            : {mem_i['available_gb']} GB free / {mem_i['total_gb']} GB total",
        f"Disk Free      : {disk_i['free_gb']} GB free / {disk_i['total_gb']} GB total",
        "GPUs           :",
        *gpu_lines,
        f"Hardware Tier  : {cls_i['tier']} (accel={cls_i['primary_accelerator']}, "
        f"max_cpu_workers={cls_i['max_parallel_cpu_workers']}, "
        f"max_gpu_workers={cls_i['max_parallel_gpu_workers']})",
        f"CLI Tools      : {', '.join(sorted(tools_i['cli'].keys())) or 'none'}",
        f"Python Modules : {', '.join(sorted(tools_i['python_modules'].keys())) or 'none'}",
        f"Tesseract Langs: {', '.join(tools_i['tesseract_langs']) or 'n/a'}",
        f"WinRT OCR Langs: {', '.join(tools_i.get('windows_ocr_langs', [])) or 'n/a'}",
        f"vLLM Active    : {svc_i['vllm']['active']} ({svc_i['vllm']['endpoint']})",
        f"Ollama Active  : {svc_i['ollama']['active']} (vision={svc_i['ollama']['vision_models']})",
        f"Cloud Keys     : {[k for k, v in svc_i['cloud_keys_present'].items() if v] or 'none'}",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile device hardware and OCR/doc conversion tools.")
    parser.add_argument("--path", help="Target workspace/file path for disk space check.", default=None)
    parser.add_argument("--pretty", action="store_true", help="Print human-readable summary instead of JSON.")
    parser.add_argument(
        "--no-network-probe",
        action="store_true",
        help="Skip probing localhost vLLM/Ollama ports.",
    )
    args = parser.parse_args()

    profile = collect_system_profile(
        target_path=args.path,
        skip_network_probe=args.no_network_probe,
    )
    if args.pretty:
        print(format_pretty(profile))
    else:
        print(json.dumps(profile, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
