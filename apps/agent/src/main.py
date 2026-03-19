from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .browser_automation import BrowserAutomationService
from .config import get_settings
from .gemini_live import GeminiLiveAdapter
from .models import EndSessionResponse, StartSessionRequest, StartSessionResponse, WsClientEvent
from .persistence import PersistenceService
from .session_manager import SessionManager

settings = get_settings()
gemini = GeminiLiveAdapter(
    api_keys=settings.google_api_keys,
    openrouter_api_key=settings.openrouter_api_key,
    anthropic_api_key=settings.anthropic_api_key,
    sarvam_api_key=settings.sarvam_api_key,
    live_model=settings.gemini_live_model,
    fallback_model=settings.gemini_fallback_model,
    default_provider=settings.default_provider,
    default_model=settings.default_model,
)
persistence = PersistenceService(project_id=settings.gcp_project_id, bucket_name=settings.gcs_bucket_name)
browser_automation = BrowserAutomationService(
    cdp_url=settings.browser_cdp_url,
    headless=settings.browser_headless,
)
sessions = SessionManager(gemini=gemini, persistence=persistence, browser_automation=browser_automation)

app = FastAPI(title="Synapse AI Agent API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins if settings.allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, object]:
    return {"status": "ok", "agent": "synapse-ai", **gemini.status()}


@app.post("/session/start", response_model=StartSessionResponse)
async def start_session(body: StartSessionRequest) -> StartSessionResponse:
    session_id = str(uuid4())
    sessions.create(session_id, body.user_id)
    sessions.set_preferences(
        session_id,
        provider=(body.provider or settings.default_provider),
        model=(body.model or settings.default_model or None),
    )
    return StartSessionResponse(session_id=session_id, ws_url=f"/ws/{session_id}")


@app.post("/session/{session_id}/end", response_model=EndSessionResponse)
async def end_session(session_id: str) -> EndSessionResponse:
    if not sessions.exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    await gemini.close_session(session_id)
    sessions.end(session_id)
    return EndSessionResponse(ok=True)


@app.websocket("/ws/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str) -> None:
    if not sessions.exists(session_id):
        await websocket.close(code=1008)
        return

    await websocket.accept()

    try:
        while True:
            raw = await websocket.receive_json()
            event = WsClientEvent.model_validate(raw)
            responses = await sessions.handle_event(session_id, event.type, event.payload)
            for item in responses:
                await websocket.send_json(item.model_dump())
    except WebSocketDisconnect:
        await gemini.close_session(session_id)
        return
    except Exception as exc:
        await websocket.send_json({"type": "error", "payload": {"message": str(exc)}})
        await websocket.close(code=1011)
