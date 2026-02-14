# LLM-based Classification Service (No DuckDuckGo)

This service classifies input text directly with an LLM call instead of using DuckDuckGo search lookups.

## Run locally
# Receipt Budget Tracker

A Flask app that processes uploaded receipt images, extracts line items, auto-categorizes each item, and tracks month-to-date spending against per-category budgets.

## Features

- Upload receipt images (`.png`, `.jpg`, etc.).
- OCR extraction with `pytesseract`.
- Parse receipt line items and amounts.
- Categorize items using:
  1. Existing keyword classifications.
  2. DuckDuckGo Instant Answer lookup fallback.
  3. User prompt when no category match is found.
- Persist budgets, classifications, pending uncategorized items, and expense history in `data/store.json`.
- Dashboard for monthly category totals and budget remaining.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

Example request:

```bash
curl -X POST http://localhost:8080/classify \
  -H 'content-type: application/json' \
  -d '{"text":"Urgent request to reset password with external link"}'
```

## Containerize for Proxmox (x86)

1. Provision a Debian/Ubuntu VM in Proxmox on an x86 host.
2. Install Docker + Compose plugin.
3. Clone this repository and create `.env`:

```bash
OPENAI_API_KEY=your_key_here
CLASSIFIER_MODEL=gpt-4o-mini
# Optional for local/self-hosted OpenAI-compatible endpoint
# OPENAI_BASE_URL=http://your-endpoint:11434/v1
```

4. Build and run amd64 image:

```bash
docker compose up -d --build
```

`docker-compose.yml` explicitly sets `platform: linux/amd64` for Proxmox x86 deployments.

## Environment variables

- `OPENAI_API_KEY`: required for LLM classification.
- `OPENAI_BASE_URL`: optional, useful for OpenAI-compatible gateways.
- `CLASSIFIER_MODEL`: defaults to `gpt-4o-mini`.

If `OPENAI_API_KEY` is not set, the API returns `unknown` with a reason.
```

Install the Tesseract engine on your OS (required by `pytesseract`):

- Debian/Ubuntu: `sudo apt-get install tesseract-ocr`
- macOS (Homebrew): `brew install tesseract`

## Run

```bash
python app.py
```

Open http://localhost:5000.

## Run with Docker

If you have a published image for this app, pull and run it like this:

```bash
docker pull <registry>/<namespace>/receipt-budget-tracker:latest
docker run --rm -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/uploads:/app/uploads \
  <registry>/<namespace>/receipt-budget-tracker:latest
```

If you are building and running locally from this repo, use:

```bash
docker build -t receipt-budget-tracker:local .
docker run --rm -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/uploads:/app/uploads \
  receipt-budget-tracker:local
```

### Mount points

- `/app/data` → persists `store.json` (budgets, classifications, expenses, pending items).
- `/app/uploads` → persists uploaded receipt files.

Both mounts are optional, but recommended so data survives container restarts.

## Image upload format

The receipt upload endpoint is `POST /upload` and expects:

- `Content-Type: multipart/form-data`
- File field name: `receipt`
- Max payload size: **10 MB** per upload

Example `curl` upload:

```bash
curl -X POST http://localhost:5000/upload \
  -F "receipt=@/path/to/receipt.jpg"
```

The app relies on Pillow + Tesseract OCR, so use clear receipt images (PNG or JPEG recommended).

## Notes

- Receipts with non-standard formatting may require manual category assignment.
- The web lookup step is best-effort and may not classify every item.
