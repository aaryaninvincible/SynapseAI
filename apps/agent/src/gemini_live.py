from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from .models import AgentReply

PROMPT = """You are Synapse AI Support Copilot.
Return concise troubleshooting guidance and output a JSON action plan.
Always prefer reversible steps and ask for confirmation when uncertain."""


class GeminiLiveAdapter:
    def __init__(self, api_key: str, live_model: str, fallback_model: str) -> None:
        self.api_key = api_key
        self.live_model = live_model
        self.fallback_model = fallback_model
        self._client = None
        self._live_sessions: dict[str, Any] = {}
        self._live_lock = asyncio.Lock()

        if api_key:
            try:
                from google import genai

                self._client = genai.Client(api_key=api_key)
            except Exception:
                self._client = None

    async def generate(self, session_id: str, user_text: str, latest_frame: str | None = None) -> AgentReply:
        if not self._client:
            return self._mock_reply(user_text)

        live_session = await self._ensure_live_session(session_id)
        if live_session:
            live_reply = await self._generate_from_live_session(live_session, user_text, latest_frame)
            if live_reply:
                return live_reply

        try:
            from google.genai import types

            contents: list[Any] = [
                types.Part.from_text(
                    text=(
                        f"{PROMPT}\n\n"
                        "User message:\n"
                        f"{user_text}\n\n"
                        "You must return valid JSON."
                    )
                )
            ]
            image_part = self._image_part_from_data_url(latest_frame)
            if image_part:
                contents.append(image_part)

            resp = self._client.models.generate_content(
                model=self.fallback_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema={
                        "type": "object",
                        "properties": {
                            "spoken_text": {"type": "string"},
                            "action_plan": {
                                "type": "object",
                                "properties": {
                                    "intent": {"type": "string"},
                                    "confidence": {"type": "number"},
                                    "steps": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "type": {"type": "string"},
                                                "target": {"type": "string"},
                                                "text": {"type": "string"},
                                                "bbox": {
                                                    "type": "array",
                                                    "items": {"type": "number"},
                                                },
                                            },
                                        },
                                    },
                                    "spoken_summary": {"type": "string"},
                                },
                            },
                        },
                        "required": ["spoken_text", "action_plan"],
                    },
                ),
            )

            text = (resp.text or "{}").strip()
            data = json.loads(text)
            return AgentReply(
                spoken_text=data.get("spoken_text", "I analyzed your request. Let's try the next step."),
                action_plan=data.get("action_plan", self._default_action_plan()),
            )
        except Exception:
            return self._mock_reply(user_text)

    async def send_video_frame(self, session_id: str, frame_data_url: str) -> bool:
        live_session = await self._ensure_live_session(session_id)
        if not live_session:
            return False
        image_blob = self._blob_from_data_url(frame_data_url)
        if not image_blob:
            return False
        try:
            await live_session.send_realtime_input(video=image_blob)
            return True
        except Exception:
            await self.close_session(session_id)
            return False

    async def send_audio_chunk(self, session_id: str, audio_base64: str, mime_type: str) -> bool:
        live_session = await self._ensure_live_session(session_id)
        if not live_session:
            return False
        try:
            audio_bytes = base64.b64decode(audio_base64, validate=True)
            from google.genai import types

            audio_blob = types.Blob(data=audio_bytes, mime_type=mime_type or "audio/webm")
            await live_session.send_realtime_input(audio=audio_blob)
            return True
        except Exception:
            await self.close_session(session_id)
            return False

    async def interrupt(self, session_id: str) -> None:
        await self.close_session(session_id)

    async def close_session(self, session_id: str) -> None:
        async with self._live_lock:
            live_session = self._live_sessions.pop(session_id, None)
        if live_session:
            try:
                await live_session.close()
            except Exception:
                return

    async def _ensure_live_session(self, session_id: str) -> Any | None:
        if not self._client:
            return None
        async with self._live_lock:
            if session_id in self._live_sessions:
                return self._live_sessions[session_id]
            try:
                from google.genai import types

                ctx = self._client.aio.live.connect(
                    model=self.live_model,
                    config=types.LiveConnectConfig(system_instruction=PROMPT),
                )
                live_session = await ctx.__aenter__()
                self._live_sessions[session_id] = live_session
                return live_session
            except Exception:
                return None

    async def _generate_from_live_session(
        self, live_session: Any, user_text: str, latest_frame: str | None
    ) -> AgentReply | None:
        try:
            from google.genai import types

            if latest_frame:
                image_blob = self._blob_from_data_url(latest_frame)
                if image_blob:
                    await live_session.send_realtime_input(video=image_blob)

            await live_session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part.from_text(text=user_text)]),
                turn_complete=True,
            )

            collected = ""
            async for message in live_session.receive():
                server_content = getattr(message, "server_content", None)
                if not server_content:
                    continue

                model_turn = getattr(server_content, "model_turn", None)
                if model_turn and getattr(model_turn, "parts", None):
                    for part in model_turn.parts:
                        text = getattr(part, "text", None)
                        if text:
                            collected += text
                if getattr(server_content, "turn_complete", False):
                    break

            if not collected.strip():
                return None
            parsed = self._parse_or_wrap(collected)
            return AgentReply(
                spoken_text=parsed.get("spoken_text", "I analyzed your request. Let's try the next step."),
                action_plan=parsed.get("action_plan", self._default_action_plan()),
            )
        except Exception:
            return None

    def _mock_reply(self, user_text: str) -> AgentReply:
        spoken = f"I got your request: '{user_text[:120]}'. First, let's verify required fields and retry."
        return AgentReply(spoken_text=spoken, action_plan=self._default_action_plan())

    def _default_action_plan(self) -> dict[str, Any]:
        return {
            "intent": "resolve_submission_error",
            "confidence": 0.72,
            "steps": [
                {
                    "type": "click",
                    "target": "First field with red validation",
                    "bbox": [0.3, 0.4, 0.25, 0.06],
                },
                {"type": "type", "target": "Required field", "text": "sample@example.com"},
                {"type": "click", "target": "Submit button"},
            ],
            "spoken_summary": "Fill the missing required field and submit again.",
        }

    def _image_part_from_data_url(self, latest_frame: str | None) -> Any | None:
        if not latest_frame or not latest_frame.startswith("data:"):
            return None
        try:
            from google.genai import types

            head, payload = latest_frame.split(",", 1)
            mime_type = head.split(";")[0].replace("data:", "").strip() or "image/jpeg"
            image_bytes = base64.b64decode(payload, validate=True)
            return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        except Exception:
            return None

    def _blob_from_data_url(self, data_url: str | None) -> Any | None:
        if not data_url or not data_url.startswith("data:"):
            return None
        try:
            from google.genai import types

            head, payload = data_url.split(",", 1)
            mime_type = head.split(";")[0].replace("data:", "").strip() or "application/octet-stream"
            raw_bytes = base64.b64decode(payload, validate=True)
            return types.Blob(data=raw_bytes, mime_type=mime_type)
        except Exception:
            return None

    def _parse_or_wrap(self, model_text: str) -> dict[str, Any]:
        cleaned = model_text.strip()
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {
            "spoken_text": cleaned,
            "action_plan": self._default_action_plan(),
        }

    def status(self) -> dict[str, Any]:
        return {
            "gemini_api_key_configured": bool(self.api_key),
            "gemini_client_ready": self._client is not None,
            "live_model": self.live_model,
            "fallback_model": self.fallback_model,
            "mode": "gemini" if self._client is not None else "mock",
        }
