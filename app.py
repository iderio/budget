import base64
import json
import logging
import os
import re
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pytesseract
import requests
from flask import Flask, redirect, render_template, request, url_for
from PIL import Image

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
STORE_FILE = DATA_DIR / "store.json"

DEFAULT_CATEGORIES = [
    "Groceries",
    "Dining",
    "Transport",
    "Health",
    "Household",
    "Utilities",
    "Entertainment",
    "Personal Care",
    "Other",
]

KEYWORD_MAP = {
    "Groceries": ["milk", "bread", "apple", "banana", "eggs", "rice", "vegetable", "grocery"],
    "Dining": ["burger", "pizza", "coffee", "restaurant", "cafe", "sandwich"],
    "Transport": ["fuel", "gas", "uber", "taxi", "metro", "bus", "parking"],
    "Health": ["pharmacy", "medicine", "vitamin", "clinic", "hospital"],
    "Household": ["detergent", "soap", "towel", "cleaner", "paper"],
    "Utilities": ["electric", "water", "internet", "phone", "utility"],
    "Entertainment": ["movie", "game", "streaming", "concert", "book"],
    "Personal Care": ["shampoo", "toothpaste", "lotion", "deodorant"],
}


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
logger = logging.getLogger(__name__)


def configure_logging():
    if logger.handlers:
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False


configure_logging()


def ensure_storage():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if not STORE_FILE.exists():
        seed = {
            "budgets": {cat: 0 for cat in DEFAULT_CATEGORIES},
            "classifications": {
                keyword: category for category, items in KEYWORD_MAP.items() for keyword in items
            },
            "expenses": {},
            "pending": {},
            "recent_uploads": [],
        }
        STORE_FILE.write_text(json.dumps(seed, indent=2))


def load_store():
    ensure_storage()
    store = json.loads(STORE_FILE.read_text())
    store.setdefault("recent_uploads", [])
    return store


def save_store(store):
    STORE_FILE.write_text(json.dumps(store, indent=2))


def current_month_key() -> str:
    return datetime.now().strftime("%Y-%m")


def parse_line_items(text: str):
    items = []

    def _append_item(name_token: str, amount_token: str):
        name = re.sub(r"\s+", " ", name_token).strip("- :|")
        if len(re.findall(r"[A-Za-z]", name)) < 2:
            return

        if re.search(r"\b(total|subtotal|tax|change|cash|visa|mastercard)\b", name, re.IGNORECASE):
            return

        normalized_amount = (
            amount_token.replace("$", "")
            .replace("€", "")
            .replace("£", "")
            .replace(",", ".")
        )
        try:
            amount = float(normalized_amount)
        except ValueError:
            return

        items.append({"name": name, "amount": amount})

    # First pass: preserve line-based extraction for well-formed OCR output.
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "|" in line:
            continue
        match = re.search(r"(.+?)\s+([\$€£]?\d+[\.,]\d{2})(?:\s*[A-Za-z])?$", line)
        if match:
            _append_item(match.group(1), match.group(2))

    # Fallback: OCR can collapse receipts into pipe-delimited fragments.
    if not items:
        for fragment in re.split(r"\|", text):
            segment = fragment.strip()
            if not segment:
                continue

            match = re.search(r"(.+?)\s+([\$€£]?\d+[\.,]\d{2})(?:\s*[A-Za-z])?$", segment)
            if match:
                _append_item(match.group(1), match.group(2))

    return items




def parse_line_items_with_openai(image_path: Path):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return []

    model = os.getenv("OPENAI_RECEIPT_MODEL", "gpt-4.1-mini")

    mime = "image/jpeg"
    suffix = image_path.suffix.lower()
    if suffix == ".png":
        mime = "image/png"
    elif suffix in {".webp"}:
        mime = "image/webp"

    b64_image = base64.b64encode(image_path.read_bytes()).decode("ascii")

    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "amount": {"type": "number"},
                    },
                    "required": ["name", "amount"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }

    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Extract purchased line items from this receipt image. "
                            "Return JSON only with `items`, where each item has `name` and numeric `amount`. "
                            "Exclude totals, taxes, payments, and store metadata."
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:{mime};base64,{b64_image}",
                    },
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "receipt_line_items",
                "schema": schema,
                "strict": True,
            }
        },
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        content = response.json()
    except requests.RequestException:
        logger.exception("OpenAI receipt extraction request failed")
        return []

    output_text = content.get("output_text", "")
    if not output_text:
        return []

    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError:
        logger.warning("OpenAI receipt extraction returned non-JSON output")
        return []

    items = []
    for raw_item in parsed.get("items", []):
        if not isinstance(raw_item, dict):
            continue
        name = str(raw_item.get("name", "")).strip()
        if not name:
            continue
        try:
            amount = float(raw_item.get("amount"))
        except (TypeError, ValueError):
            continue
        items.append({"name": name, "amount": amount})

    return items

def classify_from_existing(item_name: str, classifications: dict):
    normalized = item_name.lower()
    for keyword, category in classifications.items():
        if keyword in normalized:
            return category
    return None


def classify_from_web(item_name: str):
    try:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": item_name, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=6,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        return None

    candidate_texts = [payload.get("AbstractText", "")]
    for topic in payload.get("RelatedTopics", [])[:5]:
        if isinstance(topic, dict):
            candidate_texts.append(topic.get("Text", ""))

    corpus = " ".join(candidate_texts).lower()
    if not corpus:
        return None

    hints = {
        "Groceries": ["food", "produce", "supermarket"],
        "Dining": ["restaurant", "coffee", "drink", "meal"],
        "Transport": ["transport", "vehicle", "fuel", "transit"],
        "Health": ["medical", "medicine", "pharmacy", "health"],
        "Household": ["home", "cleaning", "household"],
        "Utilities": ["utility", "electric", "internet", "telecom"],
        "Entertainment": ["music", "movie", "game", "entertainment"],
        "Personal Care": ["cosmetic", "hygiene", "care"],
    }

    for category, words in hints.items():
        if any(word in corpus for word in words):
            return category
    return None


def extract_text_from_image(path: Path):
    image = Image.open(path)
    return pytesseract.image_to_string(image)


def month_summary(store):
    month = current_month_key()
    totals = defaultdict(float)
    for entry in store["expenses"].get(month, []):
        totals[entry["category"]] += float(entry["amount"])

    rows = []
    for category in sorted(set(list(store["budgets"].keys()) + list(totals.keys()))):
        budget = float(store["budgets"].get(category, 0))
        spent = round(totals.get(category, 0), 2)
        rows.append(
            {
                "category": category,
                "budget": budget,
                "spent": spent,
                "remaining": round(budget - spent, 2),
            }
        )
    return rows


@app.route("/", methods=["GET"])
def index():
    store = load_store()
    summary = month_summary(store)
    pendings = list(store["pending"].values())
    recent_uploads = list(reversed(store.get("recent_uploads", [])))
    return render_template(
        "index.html",
        summary=summary,
        categories=sorted(store["budgets"].keys()),
        pending_batches=pendings,
        recent_uploads=recent_uploads,
        month=current_month_key(),
    )


@app.route("/set-budget", methods=["POST"])
def set_budget():
    store = load_store()
    category = request.form.get("category", "").strip()
    amount = request.form.get("amount", "0").strip()

    if category:
        if category not in store["budgets"]:
            store["budgets"][category] = 0
        try:
            store["budgets"][category] = float(amount)
        except ValueError:
            pass
        save_store(store)

    return redirect(url_for("index"))


@app.route("/upload", methods=["POST"])
def upload_receipt():
    logger.info(
        "Upload request received: path=%s content_type=%s content_length=%s file_fields=%s",
        request.path,
        request.content_type,
        request.content_length,
        list(request.files.keys()),
    )
    receipt = request.files.get("receipt")
    if not receipt or receipt.filename == "":
        logger.warning(
            "Upload rejected: missing or empty 'receipt' file field. available_fields=%s",
            list(request.files.keys()),
        )
        return redirect(url_for("index"))

    store = load_store()
    file_id = f"{uuid.uuid4().hex}_{receipt.filename}"
    saved_path = UPLOAD_DIR / file_id
    logger.info(
        "Saving upload filename='%s' mimetype='%s' to path=%s",
        receipt.filename,
        receipt.mimetype,
        saved_path,
    )
    try:
        receipt.save(saved_path)
    except Exception:
        logger.exception("Failed to persist uploaded receipt '%s'", receipt.filename)
        return redirect(url_for("index"))
    logger.info("Saved uploaded receipt '%s' to %s", receipt.filename, saved_path)

    raw_items = []
    use_openai_parser = os.getenv("USE_OPENAI_RECEIPT_PARSER", "").lower() in {"1", "true", "yes"}
    if use_openai_parser:
        raw_items = parse_line_items_with_openai(saved_path)
        logger.info(
            "OpenAI extraction complete for '%s': parsed_items=%s",
            receipt.filename,
            len(raw_items),
        )

    text = ""
    if not raw_items:
        try:
            text = extract_text_from_image(saved_path)
        except Exception:
            logger.exception("Failed to extract OCR text from uploaded receipt '%s'", receipt.filename)
            return redirect(url_for("index"))
        logger.info(
            "OCR extraction complete for '%s': text_length=%s",
            receipt.filename,
            len(text),
        )

        raw_items = parse_line_items(text)
        logger.info("Parsed %s line item(s) from receipt '%s'", len(raw_items), receipt.filename)

    if not raw_items:
        logger.warning(
            "No line items parsed from receipt '%s'. OCR preview='%s'",
            receipt.filename,
            re.sub(r"\s+", " ", text[:160]).strip(),
        )
    resolved = []
    unresolved = []
    upload_items = []

    for item in raw_items:
        category = classify_from_existing(item["name"], store["classifications"])
        if not category:
            category = classify_from_web(item["name"])
            if category:
                store["classifications"][item["name"].lower()] = category

        payload = {**item, "category": category or ""}
        if category:
            logger.debug("Classified item '%s' as '%s'", item["name"], category)
            resolved.append(payload)
            upload_items.append({**payload, "status": "classified"})
        else:
            logger.debug("Could not classify item '%s'", item["name"])
            unresolved.append(payload)
            upload_items.append({**payload, "status": "needs_input"})

    month = current_month_key()
    store["expenses"].setdefault(month, [])
    store["expenses"][month].extend(resolved)

    if unresolved:
        batch_id = uuid.uuid4().hex
        store["pending"][batch_id] = {"id": batch_id, "items": unresolved}
        logger.info(
            "Receipt '%s' has %s unresolved item(s) pending clarification",
            receipt.filename,
            len(unresolved),
        )

    if raw_items:
        store["recent_uploads"].append(
            {
                "id": uuid.uuid4().hex,
                "filename": receipt.filename,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "items": upload_items,
                "total": round(sum(item["amount"] for item in raw_items), 2),
            }
        )
        store["recent_uploads"] = store["recent_uploads"][-5:]

    save_store(store)
    logger.info(
        "Processed receipt '%s': resolved=%s, unresolved=%s",
        receipt.filename,
        len(resolved),
        len(unresolved),
    )
    return redirect(url_for("index"))


@app.route("/resolve", methods=["POST"])
def resolve_pending():
    store = load_store()
    batch_id = request.form.get("batch_id")
    batch = store["pending"].get(batch_id)
    if not batch:
        return redirect(url_for("index"))

    month = current_month_key()
    store["expenses"].setdefault(month, [])

    for idx, item in enumerate(batch["items"]):
        category = request.form.get(f"category_{idx}", "Other")
        if category not in store["budgets"]:
            store["budgets"][category] = 0
        store["classifications"][item["name"].lower()] = category
        store["expenses"][month].append({
            "name": item["name"],
            "amount": item["amount"],
            "category": category,
        })

    store["pending"].pop(batch_id, None)
    save_store(store)
    return redirect(url_for("index"))


if __name__ == "__main__":
    ensure_storage()
    app.run(host="0.0.0.0", port=5000, debug=True)
