# ScreenSense Support Copilot

Real-time multimodal support agent scaffold for Gemini Live hackathon tracks.

## Monorepo Layout

- `apps/agent`: FastAPI websocket backend (session + agent loop).
- `apps/web`: React + Vite frontend (session UI + screen frame streaming).
- `docs`: architecture and API contract notes.
- `infra/cloudrun`: container/deploy helpers.

## Quick Start

### 1. Backend

```bash
cd apps/agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
```

### 2. Frontend

```bash
cd apps/web
npm install
npm run dev
```

Set `VITE_AGENT_BASE_URL` in `apps/web/.env.local` if backend is not on `http://localhost:8000`.

## Environment

Backend env vars:

- `GOOGLE_API_KEY`: Gemini key (optional in this scaffold, falls back to mock response mode).
- `OPENROUTER_API_KEY`: optional OpenRouter key for routed fallback.
- `ANTHROPIC_API_KEY`: optional Claude key (`provider=anthropic` or `provider=claude`).
- `SARVAM_API_KEY`: reserved for Sarvam integration (document workflow/custom adapter).
- `DEFAULT_LLM_PROVIDER`: default provider for new sessions (`gemini`, `openrouter`, `anthropic`).
- `DEFAULT_LLM_MODEL`: optional model override used by selected provider.
- `ALLOWED_ORIGINS`: comma-separated CORS origins.
- `GEMINI_LIVE_MODEL`: defaults to `gemini-2.0-flash-live-001`.
- `GEMINI_FALLBACK_MODEL`: defaults to `gemini-2.5-flash`.
- `GCP_PROJECT_ID`: enables Firestore persistence when set with valid auth.
- `GCS_BUCKET_NAME`: optional; stores periodic frame snapshots as text blobs.
- `BROWSER_CDP_URL`: optional CDP websocket endpoint for remote action execution (example: `ws://127.0.0.1:9222`).
- `BROWSER_HEADLESS`: optional, defaults to `true` for local Playwright browser launch when CDP URL is not set.

### Optional: Remote Browser Runner (Lightpanda compatible)

To execute action plans in a backend-controlled browser:

1. Start a CDP-compatible browser (Lightpanda example):
```bash
docker run -d --name lightpanda -p 9222:9222 lightpanda/browser:nightly
```
2. Set backend env:
```bash
BROWSER_CDP_URL=ws://127.0.0.1:9222
```
3. In the web UI action panel, use `Run Remote` and provide a start URL.

This lets Synapse execute `navigate/click/type/scroll/wait` steps in the remote browser session.

## Current Status

This is a working v0 scaffold:

- session start/end APIs
- websocket event loop
- user text -> agent response flow
- chunked agent text deltas (stream-like UX)
- interruption event handling
- periodic screen-frame upload from browser
- Gemini request includes latest screenshot as multimodal input when API key is configured
- mic audio chunk streaming from browser to backend websocket
- action plan JSON returned to frontend
- provider/model routing per session (`/session/start` accepts `provider` and `model`)
- explicit session end from UI
- per-session Gemini Live connection with fallback to non-live generation
- optional Firestore session/events persistence and optional Cloud Storage frame snapshots
- cross-session conversational context reuse based on `user_id`

Next: replace the mock branch with full Gemini Live streaming audio/video IO.

## Deployment

- Cloud Run script: `infra/cloudrun/deploy.ps1`
- Notes: `infra/cloudrun/README.md`
- Render Blueprint: `render.yaml` (backend)

### Render Backend Quick Deploy

1. Push this repo to GitHub.
2. In Render, click **New +** -> **Blueprint** and select this repo.
3. In the created `synapse-agent` service, set secret env var `GOOGLE_API_KEY`.
4. Deploy and copy the backend URL (for example `https://synapse-agent.onrender.com`).
5. Set frontend API base on Vercel:

```bash
cd apps/web
npx vercel env rm VITE_AGENT_BASE_URL production -y
npx vercel env add VITE_AGENT_BASE_URL production --value https://<your-render-url>
npx vercel deploy --prod -y
```
