from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from workflow_ai.exceptions import (
    InvalidStateTransitionError,
    NotFoundError,
    WorkflowConflictError,
)
from workflow_ai.models import (
    CommunicationChannel,
    CommunicationDraft,
    DispatchReceipt,
    OutboxStatus,
    WorkflowStatus,
)
from workflow_ai.store import WorkflowStore


def _draft(subject: str = "Status update") -> CommunicationDraft:
    return CommunicationDraft(
        channel=CommunicationChannel.EMAIL,
        recipients=["owner@example.com"],
        subject=subject,
        body="Please review.",
        start_at=None,
        end_at=None,
        timezone=None,
        location=None,
    )


def test_workflow_run_lifecycle_and_audit(tmp_path) -> None:
    store = WorkflowStore(tmp_path / "state.sqlite")
    store.initialize()

    row, reused = store.begin_run(
        workflow_type="test",
        idempotency_key="run-key",
        input_hash="hash-one",
    )
    run_id = row["id"]
    assert reused is False
    assert row["status"] == WorkflowStatus.RUNNING.value

    with pytest.raises(WorkflowConflictError, match="already running"):
        store.begin_run(
            workflow_type="test",
            idempotency_key="run-key",
            input_hash="hash-one",
        )

    store.complete_run(run_id, output={"ok": True}, note_path="note.md")
    completed = store.get_run(run_id)
    assert completed["status"] == WorkflowStatus.COMPLETED.value
    assert store.decode_run_output(completed) == {"ok": True}

    same, reused = store.begin_run(
        workflow_type="test",
        idempotency_key="run-key",
        input_hash="hash-one",
    )
    assert reused is True
    assert same["id"] == run_id

    with pytest.raises(InvalidStateTransitionError):
        store.complete_run(run_id, output={}, note_path="again.md")
    with pytest.raises(InvalidStateTransitionError, match="cannot fail"):
        store.fail_run(run_id, error="too late")

    store.add_audit_event(run_id=run_id, event_type="test.one", payload={"value": 1})
    store.add_audit_event(run_id=None, event_type="test.global")
    filtered = store.list_audit_events(run_id=run_id, limit=50)
    assert filtered[0]["payload"] == {"value": 1}
    assert all(event["run_id"] == run_id for event in filtered)
    assert len(store.list_audit_events(limit=1)) == 1


def test_failed_and_stale_runs_can_resume(tmp_path) -> None:
    store = WorkflowStore(tmp_path / "state.sqlite")
    store.initialize()

    failed, _ = store.begin_run(
        workflow_type="test",
        idempotency_key="failed-key",
        input_hash="hash",
    )
    store.fail_run(failed["id"], error="x" * 3_000)
    failed_row = store.get_run(failed["id"])
    assert failed_row["status"] == WorkflowStatus.FAILED.value
    assert len(failed_row["error"]) == 2_000

    resumed, reused = store.begin_run(
        workflow_type="test",
        idempotency_key="failed-key",
        input_hash="hash",
    )
    assert reused is False
    assert resumed["id"] == failed["id"]
    assert resumed["status"] == WorkflowStatus.RUNNING.value
    assert resumed["error"] is None

    stale, _ = store.begin_run(
        workflow_type="test",
        idempotency_key="stale-key",
        input_hash="hash",
    )
    old = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    connection = sqlite3.connect(store.database_path)
    try:
        connection.execute(
            "UPDATE workflow_runs SET updated_at = ? WHERE id = ?",
            (old, stale["id"]),
        )
        connection.commit()
    finally:
        connection.close()
    resumed_stale, reused = store.begin_run(
        workflow_type="test",
        idempotency_key="stale-key",
        input_hash="hash",
        stale_after=timedelta(seconds=1),
    )
    assert reused is False
    assert resumed_stale["id"] == stale["id"]


def test_run_lookup_and_decode_errors(tmp_path) -> None:
    store = WorkflowStore(tmp_path / "state.sqlite")
    store.initialize()

    with pytest.raises(NotFoundError):
        store.get_run("missing")
    with pytest.raises(NotFoundError):
        store.fail_run("missing", error="failure")
    with pytest.raises(InvalidStateTransitionError, match="no persisted output"):
        store.decode_run_output({"output_json": None})
    with pytest.raises(InvalidStateTransitionError, match="not an object"):
        store.decode_run_output({"output_json": json.dumps([1, 2, 3])})


def test_outbox_state_machine_and_error_paths(tmp_path) -> None:
    store = WorkflowStore(tmp_path / "state.sqlite")
    store.initialize()
    item = store.create_outbox(run_id=None, draft=_draft())
    assert item.status is OutboxStatus.PROPOSED
    assert store.list_outbox(status=OutboxStatus.PROPOSED)[0].id == item.id
    assert store.list_outbox(limit=1)[0].id == item.id

    with pytest.raises(NotFoundError):
        store.get_outbox("missing")
    with pytest.raises(NotFoundError):
        store.replace_outbox_draft("missing", _draft("New"))
    with pytest.raises(NotFoundError):
        store.approve_outbox("missing", actor="ehza")

    with pytest.raises(InvalidStateTransitionError):
        store.mark_outbox_dispatched(
            item.id,
            receipt=DispatchReceipt(dispatcher="test", external_id="x"),
        )
    with pytest.raises(InvalidStateTransitionError):
        store.mark_outbox_failed(item.id, error="not approved")

    approved = store.approve_outbox(item.id, actor="ehza")
    assert approved.approved_by == "ehza"
    failed = store.mark_outbox_failed(item.id, error="network failed")
    assert failed.status is OutboxStatus.FAILED
    assert failed.error == "network failed"

    reapproved = store.approve_outbox(item.id, actor="ehza")
    assert reapproved.status is OutboxStatus.APPROVED
    receipt = DispatchReceipt(
        dispatcher="test",
        external_id="delivery-1",
        detail={"status_code": 202},
    )
    dispatched = store.mark_outbox_dispatched(item.id, receipt=receipt)
    assert dispatched.status is OutboxStatus.DISPATCHED
    assert dispatched.dispatch_receipt["external_id"] == "delivery-1"

    # Marking the same record dispatched again is idempotent.
    assert store.mark_outbox_dispatched(item.id, receipt=receipt).status is OutboxStatus.DISPATCHED

    with pytest.raises(InvalidStateTransitionError):
        store.replace_outbox_draft(item.id, _draft("Cannot edit"))
    with pytest.raises(InvalidStateTransitionError):
        store.approve_outbox(item.id, actor="ehza")
    with pytest.raises(InvalidStateTransitionError):
        store.mark_outbox_failed(item.id, error="too late")
    with pytest.raises(NotFoundError):
        store.mark_outbox_dispatched("missing", receipt=receipt)
