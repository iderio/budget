from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
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


LANDING_PAGE = """<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
    <title>LLM Classification API</title>
    <style>
      body { font-family: system-ui, sans-serif; margin: 2rem; line-height: 1.4; }
      code { background: #f2f2f2; padding: 0.2rem 0.4rem; border-radius: 4px; }
    </style>
  </head>
  <body>
    <h1>LLM Classification API</h1>
    <p>Service is running.</p>
    <ul>
      <li><a href=\"/docs\">Interactive API docs</a></li>
      <li><code>GET /health</code></li>
      <li><code>POST /classify</code></li>
    </ul>
  </body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(content=LANDING_PAGE)


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
