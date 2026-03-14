from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .gemini_live import GeminiLiveAdapter
from .models import WsServerEvent


@dataclass
class SessionState:
    user_id: str | None = None
    latest_frame: str | None = None
    interrupted: bool = False
    timeline: list[dict[str, Any]] = field(default_factory=list)


class SessionManager:
    def __init__(self, gemini: GeminiLiveAdapter) -> None:
        self.gemini = gemini
        self.sessions: dict[str, SessionState] = {}

    def create(self, session_id: str, user_id: str | None = None) -> None:
        self.sessions[session_id] = SessionState(user_id=user_id)

    def end(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)

    def exists(self, session_id: str) -> bool:
        return session_id in self.sessions

    async def handle_event(self, session_id: str, event_type: str, payload: dict[str, Any]) -> list[WsServerEvent]:
        state = self.sessions[session_id]
        out: list[WsServerEvent] = []

        if event_type == "interrupt":
            state.interrupted = True
            out.append(WsServerEvent(type="state_update", payload={"status": "interrupted"}))
            return out

        if event_type == "video_frame":
            state.latest_frame = payload.get("image_base64")
            out.append(WsServerEvent(type="state_update", payload={"status": "frame_received"}))
            return out

        if event_type == "audio_chunk":
            out.append(WsServerEvent(type="state_update", payload={"status": "audio_received"}))
            return out

        if event_type == "user_text":
            text = str(payload.get("text", "")).strip()
            if not text:
                out.append(WsServerEvent(type="error", payload={"message": "Empty user_text payload."}))
                return out

            if state.interrupted:
                state.interrupted = False

            reply = await self.gemini.generate(user_text=text, latest_frame=state.latest_frame)

            state.timeline.append({"user_text": text, "agent_text": reply.spoken_text})
            for chunk in self._chunk_text(reply.spoken_text):
                out.append(WsServerEvent(type="agent_text_delta", payload={"text": chunk}))
            out.append(WsServerEvent(type="agent_action_plan", payload=reply.action_plan))
            return out

        out.append(WsServerEvent(type="error", payload={"message": f"Unsupported event type: {event_type}"}))
        return out

    def _chunk_text(self, text: str) -> list[str]:
        # Simulate streaming by splitting on sentence boundaries first, then fallback chunking.
        stripped = text.strip()
        if not stripped:
            return []

        parts: list[str] = []
        for sep in [". ", "? ", "! "]:
            if sep in stripped and not parts:
                temp = stripped.split(sep)
                for idx, item in enumerate(temp):
                    item = item.strip()
                    if not item:
                        continue
                    suffix = sep.strip() if idx < len(temp) - 1 else ""
                    parts.append(f"{item}{suffix}".strip())
        if parts:
            return parts

        size = 90
        return [stripped[i : i + size] for i in range(0, len(stripped), size)]
