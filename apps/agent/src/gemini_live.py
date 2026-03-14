from __future__ import annotations

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

        # v0: simple text completion path. Replace with Live API streaming in next iteration.
        try:
            prompt = (
                f"{PROMPT}\n\n"
                "User message:\n"
                f"{user_text}\n\n"
                "Return JSON with keys: spoken_text, action_plan."
            )
            resp = self._client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            text = (resp.text or "").strip()
            data: dict[str, Any] = json.loads(text)
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

