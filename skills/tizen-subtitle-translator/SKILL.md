---
name: tizen-subtitle-translator
description: Real-time HDMI frame-capture, subtitle band OCR (Tesseract 5.5 + MNN CRNN neural fallback), and LAN/DeepL subtitle translation architecture (tizen-subtitle-translator / SubtitleTV). Use when building or debugging TV/video-frame subtitle OCR pipelines, tuning row-projection text-band detection, running MNN/Tesseract persistent C++ OCR workers, or deploying/maintaining Tizen WGT + .NET root overlay stacks.
---

# Tizen Subtitle Translator (`tizen-subtitle-translator` / `SubtitleTV`)

Source repository: `https://github.com/ismkdc/tizen-subtitle-translator`.

Captures live HDMI frames (`720x540` / `720x576` Y-plane) on rooted Samsung Tizen TVs, isolates subtitle bands, runs **Tesseract 5.5** or an **MNN CRNN** neural OCR worker (`ocr-workers/`), translates via **DeepL** or a LAN **NLLB-200 / Argos** Python server (`servers/`), and renders an EFL notification overlay (`overlay/`).

## OCR Pipeline & Game-Subtitle Lessons

When extracting burned-in subtitles from compressed/game frames (`docs/OCR.md`, `runner/Program.cs`):

1. **ROI & row-projection band detection (`region` `x/y/w/h` 0–1):**
   - Count pixels brighter than `max(190, ocr.threshold)` (`155` default).
   - Pick contiguous bands with count `>= max(8, maxCount/3)` and `height >= 8`.
   - Reject solid UI lines/frames (`maxRow > 0.70 * width`), score by `xExtent * height` to ignore small HUD icons, and extend crop up to 40 px if a second band starts within 16 rows.
2. **Pre-processing (`P5` PGM):**
   - Crop raw grayscale Y-plane, **invert** (light text -> dark ink on light paper), and **upscale 2x** (nearest-neighbor).
   - **Avoid hard binary thresholding** (`>155 ? 0 : 255`): keeping anti-aliased edges yields significantly better accuracy on game/TV fonts.
3. **Dual-engine OCR (`ocr-workers/`):**
   - **Fast primary:** Tesseract `--psm 7` (single line) or `--psm 6` (multi-line block) parsing TSV (`level=5`, `conf >= ocr.minConfidence` `55`), or persistent C++ `ocr-worker` (`READY` / `RESULT\tconf\tms\ttext`).
   - **Accurate fallback (`ocr.fallback: true`):** Persistent C++ `neural-worker` (`rec.mnn` + `rec-keys.txt`, resized to height 48, 3-channel, greedy decode, `ocr.neuralMinConfidence: 70`). Automatically restarted by the runner on crash.
4. **Post-OCR cleanup:** `CleanOcr()` strips trailing junk after `.`/`?`/`!`, preserves speaker prefixes (`Name:`), removes HUD prefixes (`==>`, `|`), and `Valid()` rejects fragments <2 words or excessive punctuation.

## Translation & Latency Budget (`docs/TRANSLATION.md`, `servers/`)

| Backend | Endpoint / Key | Typical LAN Latency | Notes |
|---|---|---|---|
| **Argos / OPUS-MT** | `servers/translate-server.py` (`:18880`) | ~30–50 ms (~0.2–0.3 s e2e) | Fastest; literal quality |
| **NLLB-200 600M int8** | `servers/nllb-server.py` (`:18881`) | ~100–165 ms (~0.3–0.5 s e2e) | CTranslate2 (`beam_size=1`); preserves `Speaker:` prefix; **CC-BY-NC 4.0** |
| **DeepL** | `/opt/usr/subtitle-ocr/deepl-key` | ~300–900 ms (~0.6–1.2 s e2e) | Used when `translate.endpoint` is empty or as fallback |

- Runner caches up to 300 entries keyed by `target|text` and runs translation asynchronously in `TranslateLoop` so OCR/UI stay unblocked.
- HTTP contract: `POST /translate` `{ "text", "source", "target" }` -> `{ "tr", "ms" }`.

## Tizen Deployment & Security Boundaries

- **Root & mount namespace:** `helper-dotnet/` (`127.0.0.1:18765`) launches `SubtitleRunner.dll` via `unshare -m` bind-mounting `/opt/usr/subtitle-ocr` -> `/run/subtitle-ocr` and invoking `dotnet` (note: upstream `scripts/deploy-tv.py` deploys `.NET` sources; `tesseract`, `tessdata/eng.traineddata`, `neural-worker`, `rec.mnn`, `rec-keys.txt`, and `deepl-key` are placed in `/opt/usr/subtitle-ocr/`).
- **Capture & network safety:**
  - `libdisplay-capture-api.so.0` (`ppicapture`) whitelist workaround (`exec -a /usr/bin/tzcapturesample`) is strictly for personal, rooted hardware use.
  - Vetro `:8099` (`/exec` executes unauthenticated root commands) and the unauthenticated helper (`127.0.0.1:18765`) must never be exposed to untrusted networks.
  - Keep `/opt/usr/subtitle-ocr/deepl-key` at mode `600` and never commit API keys.
