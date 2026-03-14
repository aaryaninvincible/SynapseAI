# Architecture (v0)

## Components

1. Web App (React + Vite)
- Starts sessions via REST.
- Maintains websocket channel for live events.
- Sends user text events and sampled screen frames.
- Renders transcript + action plan timeline.

2. Agent API (FastAPI)
- Session lifecycle (`/session/start`, `/session/{id}/end`).
- WebSocket endpoint (`/ws/{session_id}`) for multimodal events.
- Session manager with per-session in-memory state.
- Gemini adapter (mock fallback when key/package unavailable).

3. Google Cloud Target (next iteration)
- Cloud Run for backend service.
- Firestore for session/timeline persistence.
- Cloud Storage for frame artifacts.

## Event Loop

Inbound client events:

- `user_text`
- `video_frame`
- `audio_chunk` (reserved in schema)
- `interrupt`

Outbound server events:

- `agent_text_delta`
- `agent_action_plan`
- `state_update`
- `error`

## Design Notes

- The backend is intentionally stateful per websocket session in v0.
- In production we should move session state to Firestore/Redis for scale-out.
- Gemini Live adapter currently supports basic text response with tool-style JSON output pattern.

