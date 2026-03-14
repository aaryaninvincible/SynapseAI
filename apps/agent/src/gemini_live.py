from __future__ import annotations

import base64
import json
from typing import Any

from .models import AgentReply

PROMPT = """You are ScreenSense Support Copilot.
Return concise troubleshooting guidance and output a JSON action plan.
Always prefer reversible steps and ask for confirmation when uncertain."""


class GeminiLiveAdapter:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._client = None

        if api_key:
            try:
                from google import genai

                self._client = genai.Client(api_key=api_key)
            except Exception:
                self._client = None

    async def generate(self, user_text: str, latest_frame: str | None = None) -> AgentReply:
        if not self._client:
            return self._mock_reply(user_text)

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
                model="gemini-2.5-flash",
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
