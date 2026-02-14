from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.classifier import ClassificationError, classify_with_llm

app = FastAPI(title="LLM Classification API", version="1.0.0")


class ClassificationRequest(BaseModel):
    text: str = Field(..., description="Text to classify")
    labels: list[str] | None = Field(
        default=None,
        description="Optional allowed labels. Defaults to malicious/suspicious/benign/unknown.",
    )


class ClassificationResponse(BaseModel):
    label: str
    reason: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/classify", response_model=ClassificationResponse)
def classify(payload: ClassificationRequest) -> ClassificationResponse:
    try:
        result = classify_with_llm(payload.text, payload.labels)
    except ClassificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=502, detail=f"LLM classification failed: {exc}") from exc

    return ClassificationResponse(**result)
