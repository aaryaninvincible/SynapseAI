from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .browser_automation import BrowserAutomationService
from .gemini_live import GeminiLiveAdapter
from .models import WsServerEvent
from .persistence import PersistenceService


@dataclass
class SessionState:
    user_id: str | None = None
    latest_frame: str | None = None
    interrupted: bool = False
    frame_count: int = 0
    audio_chunk_count: int = 0
    timeline: list[dict[str, Any]] = field(default_factory=list)


class SessionManager:
    def __init__(
        self,
        gemini: GeminiLiveAdapter,
        persistence: PersistenceService,
        browser_automation: BrowserAutomationService | None = None,
    ) -> None:
        self.gemini = gemini
        self.persistence = persistence
        self.browser_automation = browser_automation
        self.sessions: dict[str, SessionState] = {}

    def create(self, session_id: str, user_id: str | None = None) -> None:
        self.sessions[session_id] = SessionState(user_id=user_id)
        self.persistence.session_started(session_id, user_id)

    def end(self, session_id: str) -> None:
        state = self.sessions.pop(session_id, None)
        if state:
            self.persistence.session_ended(
                session_id,
                {
                    "frame_count": state.frame_count,
                    "audio_chunk_count": state.audio_chunk_count,
                    "timeline_size": len(state.timeline),
                },
            )

    def exists(self, session_id: str) -> bool:
        return session_id in self.sessions

    async def handle_event(self, session_id: str, event_type: str, payload: dict[str, Any]) -> list[WsServerEvent]:
        state = self.sessions[session_id]
        out: list[WsServerEvent] = []

        if event_type == "interrupt":
            state.interrupted = True
            await self.gemini.interrupt(session_id)
            self.persistence.append_event(session_id, "system", {"type": "interrupt"})
            out.append(WsServerEvent(type="state_update", payload={"status": "interrupted"}))
            return out

        if event_type == "video_frame":
            state.latest_frame = payload.get("image_base64")
            state.frame_count += 1
            if isinstance(state.latest_frame, str):
                await self.gemini.send_video_frame(session_id, state.latest_frame)
                if state.frame_count % 10 == 0:
                    self.persistence.store_frame(session_id, state.latest_frame, state.frame_count)
            if state.frame_count % 5 == 0:
                out.append(
                    WsServerEvent(
                        type="state_update",
                        payload={"status": "vision_streaming", "frames_received": state.frame_count},
                    )
                )
            return out

        if event_type == "audio_chunk":
            state.audio_chunk_count += 1
            audio_b64 = str(payload.get("audio_base64", ""))
            mime_type = str(payload.get("mime_type", "audio/webm"))
            if audio_b64:
                await self.gemini.send_audio_chunk(session_id, audio_b64, mime_type)
            if state.audio_chunk_count == 1 or state.audio_chunk_count % 10 == 0:
                out.append(
                    WsServerEvent(
                        type="state_update",
                        payload={"status": "audio_streaming", "chunks_received": state.audio_chunk_count},
                    )
                )
            return out

        if event_type == "action_execution_result":
            status = str(payload.get("status", "unknown"))
            step_type = str(payload.get("step_type", "unknown"))
            self.persistence.append_event(
                session_id,
                "system",
                {
                    "type": "action_execution_result",
                    "status": status,
                    "step_type": step_type,
                    "details": payload,
                },
            )
            out.append(
                WsServerEvent(
                    type="state_update",
                    payload={"status": "action_executed", "step_type": step_type, "result": status},
                )
            )
            return out

        if event_type == "execute_action_plan":
            if not self.browser_automation:
                out.append(
                    WsServerEvent(
                        type="error",
                        payload={"message": "Browser automation is not configured on backend."},
                    )
                )
                return out
            raw_steps = payload.get("steps")
            steps = raw_steps if isinstance(raw_steps, list) else []
            start_url = str(payload.get("start_url", "")).strip() or None
            result = await self.browser_automation.execute(steps=steps, start_url=start_url)
            self.persistence.append_event(
                session_id,
                "system",
                {
                    "type": "execute_action_plan",
                    "ok": result.ok,
                    "message": result.message,
                    "steps": result.steps,
                },
            )
            out.append(
                WsServerEvent(
                    type="state_update",
                    payload={
                        "status": "remote_action_plan_executed",
                        "ok": result.ok,
                        "message": result.message,
                        "steps": result.steps,
                    },
                )
            )
            return out

        if event_type == "user_text":
            text = str(payload.get("text", "")).strip()
            if not text:
                out.append(WsServerEvent(type="error", payload={"message": "Empty user_text payload."}))
                return out

            if state.interrupted:
                state.interrupted = False

            self.persistence.append_event(session_id, "user", {"text": text})
            reply = await self.gemini.generate(session_id=session_id, user_text=text, latest_frame=state.latest_frame)

            state.timeline.append({"user_text": text, "agent_text": reply.spoken_text})
            self.persistence.append_event(
                session_id, "agent", {"spoken_text": reply.spoken_text, "action_plan": reply.action_plan}
            )
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
