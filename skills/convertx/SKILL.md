---
name: convertx
description: Self-hosted universal file converter (`C4illin/ConvertX` v0.20.0) built with TypeScript, Bun, and Elysia, supporting 1,000+ format conversions across 22 engines (FFmpeg, ImageMagick, GraphicsMagick, LibreOffice, Pandoc, Calibre, Inkscape, Vips, XeLaTeX, MarkItDown, Assimp, pdftops, etc.). Use when deploying or automating multi-format media, document, e-book, image, vector, or 3D file conversion via Docker.
version: "0.20.0"
metadata:
  homepage: "https://github.com/C4illin/ConvertX"
  repository: "https://github.com/C4illin/ConvertX"
---

# ConvertX (`C4illin/ConvertX`)

Use this skill when you need a single self-hosted web app and Docker container capable of converting **1,000+ file formats** across documents, images, vectors, video/audio, e-books, spreadsheets, contacts, data files, and 3D assets.

## Integrated Conversion Engines

| Engine | Domain | Formats (From -> To) |
|---|---|---|
| `FFmpeg` | Video & audio | ~472 -> ~199 |
| `ImageMagick` / `GraphicsMagick` | Raster images | 245 / 167 -> 183 / 130 |
| `Vips` / `libjxl` / `libheif` | Fast images, JPEG XL, HEIF | 45 / 11 / 2 -> 23 / 11 / 4 |
| `Pandoc` | Markup & documents | 43 -> 65 |
| `LibreOffice` | Office documents | 41 -> 22 |
| `Calibre` | E-books | 26 -> 19 |
| `Inkscape` / `resvg` / `dvisvgm` | Vector graphics & SVG | 7 / 1 / 4 -> 17 / 1 / 2 |
| `Potrace` / `VTracer` | Raster -> Vector | 4 / 8 -> 11 / 1 |
| `XeLaTeX` / `DjVuLibre` / `pdftops` | LaTeX, DjVu, PDF/PS | 1 / 2 / 1 -> 1 / 2 / 2 |
| `Markitdown` | Docs -> Markdown | 6 -> 1 |
| `Dasel` / `msgconvert` / VCF->CSV | Data files, Outlook, contacts | 5 / 1 / 1 -> 4 / 1 / 1 |
| `Assimp` | 3D assets | 77 -> 23 |

## Deployment (Docker / Docker Compose)

Images: `ghcr.io/c4illin/convertx:latest` or `c4illin/convertx:latest` (default port `3000`).

```yaml
services:
  convertx:
    image: ghcr.io/c4illin/convertx
    container_name: convertx
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      - PUID=1000
      - PGID=1000
      - JWT_SECRET=replace-with-a-long-secret-string
      # - HTTP_ALLOWED=true # enable only for local non-HTTPS access
    volumes:
      - ./data:/app/data
```

Or one-off container:
```bash
docker run -p 3000:3000 -e PUID=1000 -e PGID=1000 -v ./data:/app/data ghcr.io/c4illin/convertx
```

## Key Environment Variables

- `JWT_SECRET` — Secret used to sign auth JWTs (auto-generated via `randomUUID()` if unset)
- `PUID` / `PGID` / `UMASK` — Host file ownership & creation mask for `./data` (default `PUID=0`)
- `ACCOUNT_REGISTRATION` — Allow new user registration (default: `false`)
- `HTTP_ALLOWED` — Allow login/cookies over plain HTTP locally (default: `false`; set `true` only locally)
- `ALLOW_UNAUTHENTICATED` — Bypass login locally (default: `false`; never expose to internet)
- `AUTO_DELETE_EVERY_N_HOURS` — Auto-purge converted files after `N` hours (default: `24`, `0` disables)
- `MAX_CONVERT_PROCESS` — Max concurrent conversion jobs (default: `0` unlimited)
- `FFMPEG_ARGS` / `FFMPEG_OUTPUT_ARGS` — Extra FFmpeg input/output flags (e.g., `-hwaccel vaapi`, `-preset veryfast`)
- `WEBROOT` / `BRANDING` / `PORT` — Subpath mount (e.g. `/convert`), header branding, listen port (`3000`)

## Local Development (Bun)

```bash
git clone https://github.com/C4illin/ConvertX.git
cd ConvertX
bun install
bun run dev
```

## Guardrails

- Never expose ConvertX publicly with `ALLOW_UNAUTHENTICATED=true` or `ACCOUNT_REGISTRATION=true`.
- Match `PUID`/`PGID` to the host directory owner before mounting `./data:/app/data` to avoid SQLite/file permission failures.
- If a single CLI conversion suffices locally (e.g., one file via `pandoc`, `ffmpeg`, or `soffice --headless`), prefer running the direct tool rather than spinning up the full container.
