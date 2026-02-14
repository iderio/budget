# LLM-based Classification Service (No DuckDuckGo)

This service classifies input text directly with an LLM call instead of using DuckDuckGo search lookups.

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
