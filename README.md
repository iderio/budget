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
```

Install the Tesseract engine on your OS (required by `pytesseract`):

- Debian/Ubuntu: `sudo apt-get install tesseract-ocr`
- macOS (Homebrew): `brew install tesseract`

## Run

```bash
python app.py
```

Open http://localhost:5000.

## Notes

- Receipts with non-standard formatting may require manual category assignment.
- The web lookup step is best-effort and may not classify every item.
