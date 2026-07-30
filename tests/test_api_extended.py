from __future__ import annotations

from fastapi.testclient import TestClient

from workflow_ai.api import _status_for_error, create_app
from workflow_ai.config import Settings
from workflow_ai.exceptions import (
    ConfigurationError,
    DispatchDisabledError,
    InputRejectedError,
    InvalidStateTransitionError,
    NotFoundError,
    ProviderError,
    WorkflowAIError,
    WorkflowConflictError,
)
from workflow_ai.models import SourceDocument


def test_api_briefs_outbox_index_and_audit(
    settings: Settings,
    meeting_source: SourceDocument,
) -> None:
    with TestClient(create_app(settings)) as client:
        intake = client.post(
            "/v1/intake",
            json={"source": meeting_source.model_dump(mode="json")},
        )
        assert intake.status_code == 201
        result = intake.json()
        outbox_id = result["outbox_ids"][0]

        rebuild = client.post("/v1/index/rebuild")
        assert rebuild.status_code == 200
        assert rebuild.json()["indexed_notes"] >= 1

        daily = client.post("/v1/briefs/daily", json={"brief_date": "2026-07-31"})
        assert daily.status_code == 200
        assert daily.json()["brief"]["brief_date"] == "2026-07-31"

        decision = client.post(
            "/v1/briefs/decision",
            json={
                "question": "Should Atlas keep the August 18 launch date?",
                "evidence_limit": 5,
            },
        )
        assert decision.status_code == 200
        assert decision.json()["brief"]["evidence"]

        outbox = client.get("/v1/outbox", params={"status": "proposed"})
        assert outbox.status_code == 200
        item = next(record for record in outbox.json() if record["id"] == outbox_id)

        premature = client.post(
            f"/v1/outbox/{outbox_id}/dispatch",
            json={"actor": "ehza", "mode": "filesystem"},
        )
        assert premature.status_code == 409
        assert premature.json()["error"] == "InvalidStateTransitionError"

        item["draft"]["subject"] = "Reviewed subject"
        edited = client.put(
            f"/v1/outbox/{outbox_id}",
            json={"actor": "ehza", "draft": item["draft"]},
        )
        assert edited.status_code == 200
        assert edited.json()["draft"]["subject"] == "Reviewed subject"

        approved = client.post(
            f"/v1/outbox/{outbox_id}/approve",
            json={"actor": "ehza"},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"

        dispatched = client.post(
            f"/v1/outbox/{outbox_id}/dispatch",
            json={"actor": "ehza", "mode": "filesystem"},
        )
        assert dispatched.status_code == 200
        assert dispatched.json()["status"] == "dispatched"

        events = client.get("/v1/audit", params={"run_id": result["run_id"], "limit": 50})
        assert events.status_code == 200
        event_types = {event["event_type"] for event in events.json()}
        assert "intake.completed" in event_types
        assert "outbox.dispatched" in event_types

        missing = client.post(
            "/v1/outbox/not-found/approve",
            json={"actor": "ehza"},
        )
        assert missing.status_code == 404


def test_api_rejects_oversized_source(settings: Settings, meeting_source: SourceDocument) -> None:
    constrained = settings.model_copy(update={"max_source_chars": 1_000})
    source = meeting_source.model_copy(update={"content": "x" * 1_001})

    with TestClient(create_app(constrained)) as client:
        response = client.post(
            "/v1/intake",
            json={"source": source.model_dump(mode="json")},
        )

    assert response.status_code == 400
    assert response.json()["error"] == "InputRejectedError"


def test_error_to_http_status_mapping() -> None:
    assert _status_for_error(NotFoundError("missing")) == 404
    assert _status_for_error(WorkflowConflictError("conflict")) == 409
    assert _status_for_error(InvalidStateTransitionError("state")) == 409
    assert _status_for_error(InputRejectedError("input")) == 400
    assert _status_for_error(DispatchDisabledError("disabled")) == 400
    assert _status_for_error(ConfigurationError("config")) == 503
    assert _status_for_error(ProviderError("provider")) == 503
    assert _status_for_error(WorkflowAIError("other")) == 500
