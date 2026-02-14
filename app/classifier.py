import json
import os
from typing import Sequence

DEFAULT_LABELS = ["malicious", "suspicious", "benign", "unknown"]


class ClassificationError(RuntimeError):
    """Raised when classification cannot be completed."""


def _build_prompt(text: str, labels: Sequence[str]) -> str:
    joined = ", ".join(labels)
    return (
        "Classify the provided input into exactly one label from this set: "
        f"{joined}.\n"
        "Respond with strict JSON in this shape: "
        '{"label": "<one label>", "reason": "<short reason>"}.\n'
        f"Input: {text}"
    )


def _normalize_label(raw_label: str, labels: Sequence[str]) -> str:
    clean = raw_label.strip().lower()
    for label in labels:
        if clean == label.lower():
            return label
    return "unknown"


def classify_with_llm(text: str, labels: Sequence[str] | None = None) -> dict[str, str]:
    if not text or not text.strip():
        raise ClassificationError("Input text is required for classification.")

    target_labels = list(labels or DEFAULT_LABELS)
    model = os.getenv("CLASSIFIER_MODEL", "gpt-4o-mini")
    base_url = os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return {
            "label": "unknown",
            "reason": "OPENAI_API_KEY is not set, so LLM classification was skipped.",
        }

    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        raise ClassificationError("openai package is not installed.") from exc

    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": "You are a concise security classifier.",
            },
            {
                "role": "user",
                "content": _build_prompt(text, target_labels),
            },
        ],
        temperature=0,
    )

    raw = response.output_text.strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ClassificationError(f"Model did not return valid JSON: {raw}") from exc

    label = _normalize_label(payload.get("label", "unknown"), target_labels)
    reason = str(payload.get("reason", "No reason supplied.")).strip() or "No reason supplied."
    return {"label": label, "reason": reason}
