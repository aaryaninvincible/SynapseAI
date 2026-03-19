from typing import Any, Literal

from pydantic import BaseModel, Field


EventType = Literal[
    "user_text",
    "video_frame",
    "audio_chunk",
    "interrupt",
    "action_execution_result",
    "execute_action_plan",
]
ServerEventType = Literal["agent_text_delta", "agent_action_plan", "state_update", "error"]


class StartSessionRequest(BaseModel):
    user_id: str | None = None
    provider: str | None = None
    model: str | None = None


class StartSessionResponse(BaseModel):
    session_id: str
    ws_url: str


class EndSessionResponse(BaseModel):
    ok: bool = True


class WsClientEvent(BaseModel):
    type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)


class WsServerEvent(BaseModel):
    type: ServerEventType
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentReply(BaseModel):
    spoken_text: str
    action_plan: dict[str, Any]
