import json
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
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.search(r"(.+?)\s+([\$€£]?\d+[\.,]\d{2})$", line)
        if not match:
            continue
        name = re.sub(r"\s+", " ", match.group(1)).strip("- ")
        amount_token = match.group(2).replace("$", "").replace("€", "").replace("£", "").replace(",", ".")
        try:
            amount = float(amount_token)
        except ValueError:
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
    receipt = request.files.get("receipt")
    if not receipt or receipt.filename == "":
        return redirect(url_for("index"))

    store = load_store()
    file_id = f"{uuid.uuid4().hex}_{receipt.filename}"
    saved_path = UPLOAD_DIR / file_id
    receipt.save(saved_path)

    try:
        text = extract_text_from_image(saved_path)
    except Exception:
        return redirect(url_for("index"))

    raw_items = parse_line_items(text)
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
            resolved.append(payload)
            upload_items.append({**payload, "status": "classified"})
        else:
            unresolved.append(payload)
            upload_items.append({**payload, "status": "needs_input"})

    month = current_month_key()
    store["expenses"].setdefault(month, [])
    store["expenses"][month].extend(resolved)

    if unresolved:
        batch_id = uuid.uuid4().hex
        store["pending"][batch_id] = {"id": batch_id, "items": unresolved}

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
