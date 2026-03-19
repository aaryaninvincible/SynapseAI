from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from .models import AgentReply

try:
    from google import genai
    from google.genai import types

    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

PROMPT = """You are Synapse AI Support Copilot.
Respond in this exact structure:
1) One short paragraph answer first.
2) Then bullet points for actionable details.
Keep the response complete in one turn and preserve conversation context.
Always prefer reversible steps and ask for confirmation when uncertain.
If asked who built you / who made you / your developer / creator identity, answer exactly: Built by Aryan."""


class GeminiLiveAdapter:
    def __init__(
        self,
        api_keys: list[str],
        openrouter_api_key: str,
        anthropic_api_key: str,
        sarvam_api_key: str,
        live_model: str,
        fallback_model: str,
        default_provider: str,
        default_model: str,
    ) -> None:
        self.api_keys = api_keys
        self.openrouter_api_key = openrouter_api_key
        self.anthropic_api_key = anthropic_api_key
        self.sarvam_api_key = sarvam_api_key
        self.live_model = live_model
        self.fallback_model = fallback_model
        self.default_provider = (default_provider or "gemini").strip().lower()
        self.default_model = default_model.strip() if default_model else ""
        self._clients: list[Any] = []
        self._current_client_idx = 0
        self._live_sessions: dict[str, Any] = {}
        self._live_lock = asyncio.Lock()

        for key in api_keys:
            if key and HAS_GENAI:
                try:
                    self._clients.append(genai.Client(api_key=key))
                except Exception:
                    pass

    @property
    def _client(self) -> Any | None:
        if not self._clients:
            return None
        return self._clients[self._current_client_idx]

    def _rotate_client(self) -> None:
        if self._clients:
            self._current_client_idx = (self._current_client_idx + 1) % len(self._clients)
            print("Rotated Gemini client to key index:", self._current_client_idx)

    async def generate(
        self,
        session_id: str,
        user_text: str,
        latest_frame: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        recent_turns: list[dict[str, str]] | None = None,
    ) -> AgentReply:
        selected_provider = (provider or self.default_provider or "gemini").strip().lower()
        selected_model = (model or self.default_model or "").strip()
        prompt_input = self._build_user_prompt(user_text=user_text, recent_turns=recent_turns or [])

        if selected_provider in {"anthropic", "claude"}:
            ret = await self._generate_anthropic(prompt_input, user_text, selected_model)
            if ret:
                return ret
            return self._mock_reply(user_text, "Anthropic client not initialized. Check ANTHROPIC_API_KEY.")

        if selected_provider == "openrouter":
            ret = await self._generate_openrouter(prompt_input, user_text, latest_frame, selected_model)
            if ret:
                return ret
            return self._mock_reply(user_text, "OpenRouter client not initialized. Check OPENROUTER_API_KEY.")

        if selected_provider == "sarvam":
            return self._mock_reply(
                user_text,
                "Sarvam text chat routing is not configured yet. Add SARVAM chat endpoint mapping first.",
            )

        client = self._client
        if not client:
            if self.openrouter_api_key:
                ret = await self._generate_openrouter(prompt_input, user_text, latest_frame, selected_model)
                if ret:
                    return ret
            if self.anthropic_api_key:
                ret = await self._generate_anthropic(prompt_input, user_text, selected_model)
                if ret:
                    return ret
            return self._mock_reply(user_text, "Gemini client not initialized. Check GOOGLE_API_KEY.")

        live_session = await self._ensure_live_session(session_id)
        if live_session:
            live_reply = await self._generate_from_live_session(live_session, prompt_input, user_text, latest_frame)
            if live_reply:
                return live_reply

        try:
            contents: list[Any] = [
                types.Part.from_text(
                    text=(
                        f"{PROMPT}\n\n"
                        f"{prompt_input}\n\n"
                        "You must return valid JSON."
                    )
                )
            ]
            image_part = self._image_part_from_data_url(latest_frame)
            if image_part:
                contents.append(image_part)

            resp = client.models.generate_content(
                model=selected_model or self.fallback_model,
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
            spoken_text = data.get("spoken_text", "I analyzed your request. Let's try the next step.")
            spoken_text = self._apply_identity_override(user_text, spoken_text)
            return AgentReply(
                spoken_text=spoken_text,
                action_plan=data.get("action_plan", self._default_action_plan()),
            )
        except Exception as e:
            print("Generate exception:", e)
            if self.openrouter_api_key:
                ret = await self._generate_openrouter(prompt_input, user_text, latest_frame, selected_model)
                if ret:
                    return ret
            if self.anthropic_api_key:
                ret = await self._generate_anthropic(prompt_input, user_text, selected_model)
                if ret:
                    return ret
            if "RESOURCE_EXHAUSTED" in str(e):
                self._rotate_client()
            return self._mock_reply(user_text, str(e))

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

    async def _ensure_live_session(self, session_id: str) -> Any:
        client = self._client
        if not client:
            return None
        async with self._live_lock:
            if session_id in self._live_sessions:
                return self._live_sessions[session_id]
            try:
                ctx = client.aio.live.connect(
                    model=self.live_model,
                    config=types.LiveConnectConfig(system_instruction=PROMPT),
                )
                live_session = await ctx.__aenter__()
                self._live_sessions[session_id] = live_session
                return live_session
            except Exception:
                return None

    async def _generate_from_live_session(
        self, live_session: Any, prompt_input: str, user_text: str, latest_frame: str | None
    ) -> AgentReply | None:
        try:
            if latest_frame:
                image_blob = self._blob_from_data_url(latest_frame)
                if image_blob:
                    await live_session.send_realtime_input(video=image_blob)

            await live_session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part.from_text(text=prompt_input)]),
                turn_complete=True,
            )

            collected: list[str] = []
            async for message in live_session.receive():
                server_content = getattr(message, "server_content", None)
                if not server_content:
                    continue

                model_turn = getattr(server_content, "model_turn", None)
                if model_turn and getattr(model_turn, "parts", None):
                    for part in model_turn.parts:
                        text = getattr(part, "text", None)
                        if text:
                            collected.append(str(text))
                if getattr(server_content, "turn_complete", False):
                    break

            collected_str = "".join(collected).strip()
            if not collected_str:
                return None
            parsed = self._parse_or_wrap(collected_str)
            spoken_text = parsed.get("spoken_text", "I analyzed your request. Let's try the next step.")
            spoken_text = self._apply_identity_override(user_text, spoken_text)
            return AgentReply(
                spoken_text=spoken_text,
                action_plan=parsed.get("action_plan", self._default_action_plan()),
            )
        except Exception:
            return None

    def _mock_reply(self, user_text: str, error_msg: str = "") -> AgentReply:
        friendly_msg = "I'm sorry, I'm currently undergoing a quick synapse sync (maintenance). Please try again in a few minutes!"
        if "RESOURCE_EXHAUSTED" in error_msg:
            friendly_msg = "My synapses are currently overwhelmed by high traffic. Please try again in a moment!"

        spoken = self._apply_identity_override(user_text, friendly_msg)
        return AgentReply(spoken_text=spoken, action_plan=self._default_action_plan())

    async def _generate_openrouter(
        self,
        prompt_input: str,
        user_text: str,
        latest_frame: str | None,
        model: str | None,
    ) -> AgentReply | None:
        if not self.openrouter_api_key:
            return None

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        contents: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"{PROMPT}\n\n{prompt_input}\n\n"
                    "CRITICAL: You MUST respond ONLY with a single valid JSON object. "
                    "Do NOT include any conversational text before or after the JSON."
                ),
            }
        ]

        if latest_frame and latest_frame.startswith("data:"):
            contents.append({"type": "image_url", "image_url": {"url": latest_frame}})

        data = {
            "model": model or "google/gemini-2.0-flash-001",
            "messages": [{"role": "user", "content": contents}],
        }

        loop = asyncio.get_running_loop()
        resp_text = await loop.run_in_executor(None, self._make_openrouter_request, url, headers, data)
        if not resp_text:
            return None

        try:
            resp_json = json.loads(resp_text)
            content = resp_json["choices"][0]["message"]["content"]
            parsed = self._parse_or_wrap(content)
            spoken_text = parsed.get("spoken_text", "I analyzed your request. Let's try the next step.")
            spoken_text = self._apply_identity_override(user_text, spoken_text)
            return AgentReply(
                spoken_text=spoken_text,
                action_plan=parsed.get("action_plan", self._default_action_plan()),
            )
        except Exception as e:
            print("OpenRouter parsing error:", e)
            return None

    async def _generate_anthropic(self, prompt_input: str, user_text: str, model: str | None) -> AgentReply | None:
        if not self.anthropic_api_key:
            return None

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model or "claude-3-5-sonnet-latest",
            "max_tokens": 1000,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"{PROMPT}\n\n{prompt_input}\n\n"
                        "Return only a valid JSON object with keys: spoken_text and action_plan."
                    ),
                }
            ],
        }

        loop = asyncio.get_running_loop()
        resp_text = await loop.run_in_executor(None, self._make_openrouter_request, url, headers, payload)
        if not resp_text:
            return None

        try:
            data = json.loads(resp_text)
            content_blocks = data.get("content", [])
            text = ""
            if isinstance(content_blocks, list):
                for block in content_blocks:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text += str(block.get("text", ""))
            if not text.strip():
                return None
            parsed = self._parse_or_wrap(text)
            spoken_text = self._apply_identity_override(
                user_text,
                parsed.get("spoken_text", "I analyzed your request. Let's try the next step."),
            )
            return AgentReply(
                spoken_text=spoken_text,
                action_plan=parsed.get("action_plan", self._default_action_plan()),
            )
        except Exception as exc:
            print("Anthropic parsing error:", exc)
            return None

    @staticmethod
    def _make_openrouter_request(url: str, headers: dict[str, str], data: dict[str, Any]) -> str | None:
        try:
            import urllib.request

            req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            print("HTTP provider error:", e)
            return None

    def _build_user_prompt(self, user_text: str, recent_turns: list[dict[str, str]]) -> str:
        context_lines: list[str] = []
        for item in recent_turns[-10:]:
            role = str(item.get("role", "")).strip().lower()
            text = str(item.get("text", "")).strip()
            if role in {"user", "agent"} and text:
                context_lines.append(f"{role}: {text}")

        context_block = "\n".join(context_lines)
        if context_block:
            return (
                "Conversation context from earlier turns:\n"
                f"{context_block}\n\n"
                "Current user message:\n"
                f"{user_text}"
            )

        return f"Current user message:\n{user_text}"

    def _apply_identity_override(self, user_text: str, spoken_text: str) -> str:
        normalized = user_text.lower()
        if any(
            key in normalized
            for key in ("who built", "who made", "your developer", "who created", "creator", "built you")
        ):
            return "Built by Aryan."
        return spoken_text

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
        if latest_frame is None or not latest_frame.startswith("data:"):
            return None
        try:
            parts = str(latest_frame).split(",", 1)
            if len(parts) < 2:
                return None
            head, payload = parts
            parsed_mime = head.split(";")[0]
            mime_type = parsed_mime.replace("data:", "").strip() if parsed_mime else "image/jpeg"
            image_bytes = base64.b64decode(payload, validate=True)
            return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        except Exception:
            return None

    def _blob_from_data_url(self, data_url: str | None) -> Any | None:
        if data_url is None or not data_url.startswith("data:"):
            return None
        try:
            parts = str(data_url).split(",", 1)
            if len(parts) < 2:
                return None
            head, payload = parts
            parsed_mime = head.split(";")[0]
            mime_type = parsed_mime.replace("data:", "").strip() if parsed_mime else "application/octet-stream"
            raw_bytes = base64.b64decode(payload, validate=True)
            return types.Blob(data=raw_bytes, mime_type=mime_type)
        except Exception:
            return None

    def _parse_or_wrap(self, model_text: str) -> dict[str, Any]:
        cleaned = model_text.strip()
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return self._normalize_model_payload(data)
        except Exception:
            pass

        import re

        try:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                if isinstance(data, dict):
                    return self._normalize_model_payload(data)
            match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                if isinstance(data, dict):
                    return self._normalize_model_payload(data)
        except Exception:
            pass

        if self._looks_like_json(cleaned):
            return {
                "spoken_text": "I analyzed your request. I can walk you through the next step now.",
                "action_plan": self._default_action_plan(),
            }

        return {
            "spoken_text": cleaned,
            "action_plan": self._default_action_plan(),
        }

    def _normalize_model_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        spoken_text = data.get("spoken_text")
        if not isinstance(spoken_text, str) or not spoken_text.strip():
            fallback = data.get("spoken_summary") or data.get("summary") or data.get("message")
            if not isinstance(fallback, str):
                action_plan = data.get("action_plan")
                if isinstance(action_plan, dict):
                    fallback = action_plan.get("spoken_summary")
            spoken_text = (
                fallback
                if isinstance(fallback, str) and fallback.strip()
                else "I analyzed your request. Let's try the next step."
            )

        action_plan = data.get("action_plan")
        if not isinstance(action_plan, dict):
            action_plan = self._default_action_plan()

        return {
            "spoken_text": (spoken_text or "").strip(),
            "action_plan": action_plan,
        }

    def _looks_like_json(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        return (
            (stripped.startswith("{") and stripped.endswith("}"))
            or (stripped.startswith("[") and stripped.endswith("]"))
            or '"spoken_text"' in stripped
            or '"action_plan"' in stripped
        )

    def status(self) -> dict[str, Any]:
        has_gemini = bool(self.api_keys) and (self._client is not None)
        has_openrouter = bool(self.openrouter_api_key)
        has_claude = bool(self.anthropic_api_key)
        return {
            "gemini_api_key_configured": bool(self.api_keys) or has_openrouter or has_claude,
            "gemini_client_ready": has_gemini or has_openrouter or has_claude,
            "live_model": self.live_model,
            "fallback_model": self.fallback_model,
            "default_provider": self.default_provider,
            "default_model": self.default_model,
            "available_providers": {
                "gemini": has_gemini,
                "openrouter": has_openrouter,
                "anthropic": has_claude,
                "sarvam": bool(self.sarvam_api_key),
            },
            "mode": "gemini" if has_gemini else ("openrouter" if has_openrouter else ("anthropic" if has_claude else "mock")),
        }
