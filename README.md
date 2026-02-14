# LLM-based Classification Service

This service classifies input text directly with an LLM call and returns a normalized label plus a short reason.

## Features

- FastAPI service with health check (`GET /health`).
- Classification endpoint (`POST /classify`).
- Configurable label set per request.
- Optional support for OpenAI-compatible base URLs.
- Dockerized runtime with Compose examples.

## Run locally

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

## Environment variables

- `OPENAI_API_KEY`: required for LLM classification.
- `OPENAI_BASE_URL`: optional, useful for OpenAI-compatible gateways.
- `CLASSIFIER_MODEL`: optional, defaults to `gpt-4o-mini`.

If `OPENAI_API_KEY` is not set, the API returns `unknown` with a reason.

## Docker Compose

Use the production-oriented file:

```bash
docker compose up -d --build
```

A sample template is also included for customization:

- `docker-compose.sample.yml`

Example:

```bash
cp docker-compose.sample.yml docker-compose.override.yml
docker compose up -d --build
```

`docker-compose.yml` explicitly sets `platform: linux/amd64` for Proxmox x86 deployments.

## Tests

```bash
python -m pytest -q
```
