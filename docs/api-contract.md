# API Contract (v0)

## POST `/session/start`

Request:

```json
{
  "user_id": "optional-user-id"
}
```

Response:

```json
{
  "session_id": "uuid",
  "ws_url": "ws://localhost:8000/ws/uuid"
}
```

## POST `/session/{session_id}/end`

Response:

```json
{
  "ok": true
}
```

## WS `/ws/{session_id}`

Inbound message:

```json
{
  "type": "user_text | video_frame | audio_chunk | interrupt | action_execution_result | execute_action_plan",
  "payload": {}
}
```

Outbound message:

```json
{
  "type": "agent_text_delta | agent_action_plan | state_update | error",
  "payload": {}
}
```

## Example `agent_action_plan`

```json
{
  "intent": "resolve_form_submission_error",
  "confidence": 0.85,
  "steps": [
    {
      "type": "click",
      "target": "Required email field",
      "bbox": [0.33, 0.44, 0.28, 0.06]
    },
    {
      "type": "type",
      "target": "Email field",
      "text": "name@example.com"
    }
  ],
  "spoken_summary": "Fill the missing required email field and submit again."
}
```
