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
- `ALLOWED_ORIGINS`: comma-separated CORS origins.
- `GEMINI_LIVE_MODEL`: defaults to `gemini-2.0-flash-live-001`.
- `GEMINI_FALLBACK_MODEL`: defaults to `gemini-2.5-flash`.
- `GCP_PROJECT_ID`: enables Firestore persistence when set with valid auth.
- `GCS_BUCKET_NAME`: optional; stores periodic frame snapshots as text blobs.

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
- explicit session end from UI
- per-session Gemini Live connection with fallback to non-live generation
- optional Firestore session/events persistence and optional Cloud Storage frame snapshots

Next: replace the mock branch with full Gemini Live streaming audio/video IO.
