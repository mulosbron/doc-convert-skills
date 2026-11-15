#!/usr/bin/env python3
"""Unit & integration tests for device-aware OCR routing, Windows WinRT OCR, and CLI tools."""

from __future__ import annotations

import importlib.util
import json
import platform
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "skills" / "device-aware-ocr-router" / "scripts"
WINRT_SCRIPTS_DIR = REPO_ROOT / "skills" / "windows-winrt-ocr" / "scripts"
TOOLS_DIR = REPO_ROOT / "tools"

for p in (SCRIPTS_DIR, WINRT_SCRIPTS_DIR, TOOLS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from doc_convert_runner import run_conversion_pipeline, validate_output_file  # noqa: E402
from document_inspector import inspect_target  # noqa: E402
from ocr_recommender import recommend_for_document  # noqa: E402
from system_profiler import classify_hardware_tier, collect_system_profile  # noqa: E402
from winrt_pdf_ocr import list_winrt_languages, run_winrt_ocr  # noqa: E402


def _make_profile(
    tier_vram_gb: float = 0.0,
    ram_gb: float = 16.0,
    cores: int = 8,
    system: str = "Windows",
    arm64: bool = False,
    vllm_active: bool = False,
    cloud_openai: bool = False,
    cli_tools: dict[str, str] | None = None,
    py_mods: dict[str, bool] | None = None,
    win_ocr_langs: list[str] | None = None,
) -> dict:
    os_info = {"system": system, "release": "11", "machine": "arm64" if arm64 else "amd64", "is_arm64": arm64, "is_wsl": False}
    cpu_info = {"brand": "Test CPU", "logical_cores": cores, "physical_cores": max(1, cores // 2)}
    memory_info = {"total_gb": ram_gb, "available_gb": round(ram_gb * 0.7, 2)}
    gpus = []
    if tier_vram_gb > 0:
        gpus.append({"vendor": "nvidia", "backend": "cuda", "name": "Test GPU", "vram_total_gb": tier_vram_gb, "vram_free_gb": tier_vram_gb})
    elif system == "Darwin" and arm64:
        gpus.append({"vendor": "apple", "backend": "mps", "name": "Apple Silicon", "vram_total_gb": round(ram_gb * 0.75, 2), "vram_free_gb": round(ram_gb * 0.5, 2)})

    classification = classify_hardware_tier(os_info, cpu_info, memory_info, gpus)
    return {
        "os": os_info,
        "cpu": cpu_info,
        "memory": memory_info,
        "disk": {"total_gb": 500.0, "free_gb": 100.0},
        "gpus": gpus,
        "classification": classification,
        "tools": {
            "cli": cli_tools or {},
            "cli_missing": [],
            "tesseract_langs": ["eng", "tur"] if "tesseract" in (cli_tools or {}) else [],
            "windows_ocr_langs": (["tr", "en-GB"] if (win_ocr_langs is None and system == "Windows") else (win_ocr_langs or [])),
            "python_modules": py_mods or {},
            "python_missing": [],
        },
        "services": {
            "vllm": {"endpoint": "http://127.0.0.1:8000/v1", "active": vllm_active, "models": ["chandra"] if vllm_active else []},
            "ollama": {"endpoint": "http://127.0.0.1:11434", "active": False, "vision_models": []},
            "cloud_keys_present": {"openai": cloud_openai, "gemini": False, "anthropic": False, "azure_doc_intel": False},
        },
    }


class TestHardwareClassificationAndRouting(unittest.TestCase):
    def test_tier_classification(self) -> None:
        dc = _make_profile(tier_vram_gb=24.0, ram_gb=64.0, cores=32)
        self.assertEqual(dc["classification"]["tier"], "gpu_datacenter")
        self.assertGreaterEqual(dc["classification"]["max_parallel_gpu_workers"], 2)

        mid = _make_profile(tier_vram_gb=8.0, ram_gb=64.0, cores=32)
        self.assertEqual(mid["classification"]["tier"], "gpu_mid")
        self.assertEqual(mid["classification"]["max_parallel_gpu_workers"], 1)

        apple = _make_profile(tier_vram_gb=0.0, ram_gb=32.0, cores=12, system="Darwin", arm64=True)
        self.assertEqual(apple["classification"]["tier"], "apple_silicon_high")

        cpu_low = _make_profile(tier_vram_gb=0.0, ram_gb=4.0, cores=4, system="Linux")
        self.assertEqual(cpu_low["classification"]["tier"], "cpu_low")

    def test_8gb_gpu_avoids_chandra_hf_primary_and_runs_sequentially(self) -> None:
        prof = _make_profile(
            tier_vram_gb=8.0,
            ram_gb=64.0,
            cores=32,
            cli_tools={"chandra": "/usr/bin/chandra"},
            py_mods={"torch": True, "chandra": True},
        )
        rec = recommend_for_document(
            prof,
            doc_info={"category": "pdf", "ocr_required": True, "pdf": {"pdf_kind": "scanned"}},
            complexity="tables",
            lang="tur+eng",
            batch_count=5,
        )
        self.assertEqual(rec["recommended"]["engine"], "surya-marker")
        self.assertEqual(rec["orchestration"]["execution_mode"], "sequential")
        self.assertEqual(rec["orchestration"]["max_parallel_workers"], 1)
        self.assertTrue(any("gpu_mid" in w for w in rec["warnings"]))
        self.assertIsNotNone(rec["ready_now"])
        self.assertIn(rec["ready_now"]["engine"], ("windows-winrt-ocr", "chandra-ocr-hf"))

    def test_windows_cpu_fast_prefers_windows_winrt_ocr_and_linux_excludes_it(self) -> None:
        win_prof = _make_profile(tier_vram_gb=0.0, ram_gb=16.0, cores=8, system="Windows")
        rec_win = recommend_for_document(
            win_prof,
            doc_info={"category": "pdf", "ocr_required": True, "pdf": {"pdf_kind": "scanned"}},
            quality="fast",
            lang="tr",
        )
        self.assertEqual(rec_win["recommended"]["engine"], "windows-winrt-ocr")
        self.assertTrue(rec_win["recommended"]["installed"])

        linux_prof = _make_profile(tier_vram_gb=0.0, ram_gb=16.0, cores=8, system="Linux")
        rec_linux = recommend_for_document(
            linux_prof,
            doc_info={"category": "pdf", "ocr_required": True, "pdf": {"pdf_kind": "scanned"}},
            quality="fast",
        )
        all_engines = [rec_linux["recommended"]["engine"]] + [a["engine"] for a in rec_linux["alternatives"]]
        self.assertNotIn("windows-winrt-ocr", all_engines)

    def test_datacenter_or_vllm_picks_chandra_vllm(self) -> None:
        prof = _make_profile(tier_vram_gb=24.0, ram_gb=128.0, cores=32, vllm_active=True)
        rec = recommend_for_document(
            prof,
            doc_info={"category": "pdf", "ocr_required": True, "pdf": {"pdf_kind": "scanned"}},
            complexity="math",
            batch_count=4,
        )
        self.assertEqual(rec["recommended"]["engine"], "chandra-ocr-vllm")
        self.assertEqual(rec["orchestration"]["execution_mode"], "parallel_subagents")

    def test_digital_pdf_avoids_ocr_and_allows_parallel_cpu(self) -> None:
        prof = _make_profile(tier_vram_gb=8.0, ram_gb=32.0, cores=16, py_mods={"fitz": True, "pdfplumber": True})
        rec = recommend_for_document(
            prof,
            doc_info={"category": "pdf", "ocr_required": False, "pdf": {"pdf_kind": "digital"}},
            batch_count=4,
        )
        self.assertEqual(rec["recommended"]["engine"], "opendataloader-pdf")
        self.assertEqual(rec["ready_now"]["engine"], "pymupdf-pdfplumber")
        self.assertEqual(rec["orchestration"]["execution_mode"], "parallel_subagents")
        self.assertEqual(rec["orchestration"]["max_parallel_workers"], 4)

    def test_privacy_local_only_excludes_cloud_ocr(self) -> None:
        prof = _make_profile(tier_vram_gb=0.0, ram_gb=8.0, cores=4, cloud_openai=True)
        rec_local = recommend_for_document(
            prof,
            doc_info={"category": "pdf", "ocr_required": True, "pdf": {"pdf_kind": "scanned"}},
            privacy="local-only",
        )
        engines_local = [rec_local["recommended"]["engine"]] + [a["engine"] for a in rec_local["alternatives"]]
        self.assertNotIn("markitdown-cloud-ocr", engines_local)

        rec_cloud = recommend_for_document(
            prof,
            doc_info={"category": "pdf", "ocr_required": True, "pdf": {"pdf_kind": "scanned"}},
            privacy="allow-cloud",
            complexity="tables",
        )
        self.assertEqual(rec_cloud["recommended"]["engine"], "markitdown-cloud-ocr")

    def test_markup_web_avoids_ocr(self) -> None:
        prof = _make_profile(tier_vram_gb=8.0, ram_gb=16.0, cores=8)
        rec = recommend_for_document(
            prof,
            doc_info={"category": "markup_web", "ocr_required": False},
        )
        self.assertEqual(rec["recommended"]["engine"], "markitdown")


class TestLiveInspectionRunnerAndWinRT(unittest.TestCase):
    def test_live_profile_runs_cleanly(self) -> None:
        profile = collect_system_profile(skip_network_probe=True)
        self.assertIn("tier", profile["classification"])
        self.assertGreater(profile["cpu"]["logical_cores"], 0)
        self.assertGreater(profile["memory"]["total_gb"], 0)
        if platform.system() == "Windows":
            self.assertIn("windows_ocr_langs", profile["tools"])

    @unittest.skipUnless(importlib.util.find_spec("fitz") is not None, "PyMuPDF (fitz) required for synthetic PDF test")
    def test_inspect_and_convert_real_digital_pdf(self) -> None:
        import fitz  # type: ignore

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "sample_digital.pdf"
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text(
                (72, 72),
                "Quarterly Financial Summary\nRevenue increased by 24% in Istanbul & Ankara regions.\n"
                + ("Detailed audit line item with verified numbers and labels.\n" * 4),
            )
            doc.save(str(pdf_path))
            doc.close()

            inspected = inspect_target(str(pdf_path))
            self.assertEqual(inspected["count"], 1)
            self.assertEqual(inspected["files"][0]["pdf"]["pdf_kind"], "digital")
            self.assertFalse(inspected["files"][0]["ocr_required"])

            out_dir = tmp_path / "out"
            run_res = run_conversion_pipeline(
                target=str(pdf_path),
                output_dir=str(out_dir),
                prefer_installed=True,
                no_network_probe=True,
            )
            self.assertEqual(run_res["total_files"], 1)
            first = run_res["results"][0]
            self.assertEqual(first["status"], "ok")
            self.assertTrue(first["validation"]["passed"])
            out_md = Path(first["output"]).read_text(encoding="utf-8")
            self.assertIn("Quarterly Financial Summary", out_md)

    @unittest.skipUnless(
        platform.system() == "Windows" and importlib.util.find_spec("fitz") is not None,
        "Windows + PyMuPDF required for live Windows.Media.Ocr test",
    )
    def test_live_windows_winrt_ocr_image_and_pdf(self) -> None:
        import fitz  # type: ignore

        langs = list_winrt_languages()
        self.assertGreater(len(langs), 0)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Render a real raster image (no text layer) and run Windows.Media.Ocr
            src_doc = fitz.open()
            p = src_doc.new_page()
            p.insert_text((72, 100), "INVOICE TOTAL 1250 USD", fontsize=24)
            img_path = tmp_path / "scan_sample.png"
            p.get_pixmap(dpi=150).save(str(img_path))
            src_doc.close()

            res = run_winrt_ocr(img_path, tmp_path / "out", lang="en-GB", fmt="md")
            out_text = Path(res["output"]).read_text(encoding="utf-8")
            self.assertIn("INVOICE", out_text.upper())
            self.assertIn("1250", out_text)

    def test_validate_output_file_rejects_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.md"
            empty.write_text("", encoding="utf-8")
            res = validate_output_file(empty)
            self.assertFalse(res["passed"])

    def test_unified_cli_tool(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "doc_convert.py"), "recommend", "--doc-type", "scanned-pdf", "--no-network-probe"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15.0,
            check=True,
        )
        payload = json.loads(proc.stdout)
        self.assertIn("recommended", payload)
        self.assertIn("orchestration", payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
