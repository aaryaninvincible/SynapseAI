from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class PersistenceService:
    def __init__(self, project_id: str, bucket_name: str) -> None:
        self.project_id = project_id
        self.bucket_name = bucket_name
        self._firestore = None
        self._bucket = None

        try:
            if project_id:
                from google.cloud import firestore

                self._firestore = firestore.Client(project=project_id)
        except Exception:
            self._firestore = None

        try:
            if project_id and bucket_name:
                from google.cloud import storage

                storage_client = storage.Client(project=project_id)
                self._bucket = storage_client.bucket(bucket_name)
        except Exception:
            self._bucket = None

    def enabled(self) -> bool:
        return self._firestore is not None

    def session_started(self, session_id: str, user_id: str | None) -> None:
        if not self._firestore:
            return
        self._firestore.collection("sessions").document(session_id).set(
            {
                "session_id": session_id,
                "user_id": user_id,
                "status": "active",
                "started_at": self._utc_now(),
            }
        )

    def session_ended(self, session_id: str, summary: dict[str, Any]) -> None:
        if not self._firestore:
            return
        self._firestore.collection("sessions").document(session_id).set(
            {
                "status": "ended",
                "ended_at": self._utc_now(),
                "summary": summary,
            },
            merge=True,
        )

    def append_event(self, session_id: str, role: str, payload: dict[str, Any]) -> None:
        if not self._firestore:
            return
        self._firestore.collection("sessions").document(session_id).collection("events").add(
            {"role": role, "payload": payload, "ts": self._utc_now()}
        )

    def store_frame(self, session_id: str, frame_data_url: str, frame_index: int) -> None:
        if not self._bucket:
            return
        try:
            blob = self._bucket.blob(f"sessions/{session_id}/frames/frame-{frame_index:06d}.txt")
            blob.upload_from_string(frame_data_url, content_type="text/plain")
        except Exception:
            return

    def _utc_now(self) -> str:
        return datetime.now(tz=timezone.utc).isoformat()

