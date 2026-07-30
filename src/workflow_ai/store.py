"""SQLite workflow state, idempotency, outbox, and audit persistence."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from workflow_ai.exceptions import (
    InvalidStateTransitionError,
    NotFoundError,
    WorkflowConflictError,
)
from workflow_ai.models import (
    CommunicationDraft,
    DispatchReceipt,
    OutboxRecord,
    OutboxStatus,
    WorkflowStatus,
)
from workflow_ai.utils import canonical_json, utc_now


class WorkflowStore:
    """Persistence adapter with one short-lived SQLite connection per operation."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    id TEXT PRIMARY KEY,
                    workflow_type TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    input_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output_json TEXT,
                    note_path TEXT,
                    error TEXT,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_workflow_runs_status
                    ON workflow_runs(status, updated_at DESC);

                CREATE TABLE IF NOT EXISTS outbox (
                    id TEXT PRIMARY KEY,
                    run_id TEXT,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    approved_by TEXT,
                    approved_at TEXT,
                    dispatched_at TEXT,
                    dispatch_receipt_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES workflow_runs(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_outbox_status
                    ON outbox(status, created_at DESC);

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES workflow_runs(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_audit_events_run
                    ON audit_events(run_id, id DESC);
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def begin_run(
        self,
        *,
        workflow_type: str,
        idempotency_key: str,
        input_hash: str,
        stale_after: timedelta = timedelta(minutes=15),
    ) -> tuple[dict[str, Any], bool]:
        """Create a run, return a completed duplicate, or safely resume a stale failure."""

        now = utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM workflow_runs WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()

            if row is None:
                run_id = str(uuid.uuid4())
                connection.execute(
                    """
                    INSERT INTO workflow_runs (
                        id, workflow_type, idempotency_key, input_hash, status,
                        started_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        workflow_type,
                        idempotency_key,
                        input_hash,
                        WorkflowStatus.RUNNING.value,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
                created = connection.execute(
                    "SELECT * FROM workflow_runs WHERE id = ?", (run_id,)
                ).fetchone()
                assert created is not None
                return dict(created), False

            existing = dict(row)
            if existing["input_hash"] != input_hash:
                raise WorkflowConflictError(
                    "Idempotency key already belongs to a different input payload"
                )
            if existing["status"] == WorkflowStatus.COMPLETED.value:
                return existing, True
            if existing["status"] == WorkflowStatus.RUNNING.value:
                updated_at = _parse_datetime(existing["updated_at"])
                if updated_at is not None and now - updated_at < stale_after:
                    raise WorkflowConflictError("Equivalent workflow is already running")

            connection.execute(
                """
                UPDATE workflow_runs
                SET status = ?, output_json = NULL, note_path = NULL, error = NULL,
                    started_at = ?, updated_at = ?, completed_at = NULL
                WHERE id = ?
                """,
                (
                    WorkflowStatus.RUNNING.value,
                    now.isoformat(),
                    now.isoformat(),
                    existing["id"],
                ),
            )
            resumed = connection.execute(
                "SELECT * FROM workflow_runs WHERE id = ?", (existing["id"],)
            ).fetchone()
            assert resumed is not None
            return dict(resumed), False

    def complete_run(self, run_id: str, *, output: dict[str, Any], note_path: str) -> None:
        now = utc_now().isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE workflow_runs
                SET status = ?, output_json = ?, note_path = ?, error = NULL,
                    updated_at = ?, completed_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    WorkflowStatus.COMPLETED.value,
                    canonical_json(output),
                    note_path,
                    now,
                    now,
                    run_id,
                    WorkflowStatus.RUNNING.value,
                ),
            )
            if cursor.rowcount != 1:
                raise InvalidStateTransitionError(
                    f"Workflow run {run_id} is not in the running state"
                )

    def fail_run(self, run_id: str, *, error: str) -> None:
        now = utc_now().isoformat()
        safe_error = error[:2_000]
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE workflow_runs
                SET status = ?, error = ?, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    WorkflowStatus.FAILED.value,
                    safe_error,
                    now,
                    run_id,
                    WorkflowStatus.RUNNING.value,
                ),
            )
            if cursor.rowcount != 1:
                existing = connection.execute(
                    "SELECT status FROM workflow_runs WHERE id = ?", (run_id,)
                ).fetchone()
                if existing is None:
                    raise NotFoundError(f"Workflow run not found: {run_id}")
                raise InvalidStateTransitionError(
                    f"Workflow run {run_id} cannot fail from state {existing['status']}"
                )

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM workflow_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Workflow run not found: {run_id}")
        return dict(row)

    def decode_run_output(self, row: dict[str, Any]) -> dict[str, Any]:
        raw = row.get("output_json")
        if not raw:
            raise InvalidStateTransitionError("Completed workflow has no persisted output")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise InvalidStateTransitionError("Persisted workflow output is not an object")
        return value

    def add_audit_event(
        self,
        *,
        run_id: str | None,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (run_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, event_type, canonical_json(payload or {}), utc_now().isoformat()),
            )

    def list_audit_events(self, *, run_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 1_000))
        with self._connect() as connection:
            if run_id is None:
                rows = connection.execute(
                    "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM audit_events WHERE run_id = ? ORDER BY id DESC LIMIT ?",
                    (run_id, limit),
                ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            result.append(item)
        return result

    def create_outbox(self, *, run_id: str | None, draft: CommunicationDraft) -> OutboxRecord:
        outbox_id = str(uuid.uuid4())
        now = utc_now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO outbox (
                    id, run_id, payload_json, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    outbox_id,
                    run_id,
                    draft.model_dump_json(),
                    OutboxStatus.PROPOSED.value,
                    now,
                    now,
                ),
            )
        return self.get_outbox(outbox_id)

    def get_outbox(self, outbox_id: str) -> OutboxRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM outbox WHERE id = ?", (outbox_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Outbox item not found: {outbox_id}")
        return _outbox_from_row(row)

    def list_outbox(
        self,
        *,
        status: OutboxStatus | None = None,
        limit: int = 100,
    ) -> list[OutboxRecord]:
        limit = max(1, min(limit, 1_000))
        with self._connect() as connection:
            if status is None:
                rows = connection.execute(
                    "SELECT * FROM outbox ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM outbox WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status.value, limit),
                ).fetchall()
        return [_outbox_from_row(row) for row in rows]

    def replace_outbox_draft(self, outbox_id: str, draft: CommunicationDraft) -> OutboxRecord:
        """Replace a draft and revoke any earlier approval."""

        now = utc_now().isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE outbox
                SET payload_json = ?, status = ?, approved_by = NULL,
                    approved_at = NULL, dispatched_at = NULL,
                    dispatch_receipt_json = NULL, error = NULL, updated_at = ?
                WHERE id = ? AND status != ?
                """,
                (
                    draft.model_dump_json(),
                    OutboxStatus.PROPOSED.value,
                    now,
                    outbox_id,
                    OutboxStatus.DISPATCHED.value,
                ),
            )
            if cursor.rowcount != 1:
                existing = self._row_or_none(connection, outbox_id)
                if existing is None:
                    raise NotFoundError(f"Outbox item not found: {outbox_id}")
                raise InvalidStateTransitionError("A dispatched item cannot be edited")
        return self.get_outbox(outbox_id)

    def approve_outbox(self, outbox_id: str, *, actor: str) -> OutboxRecord:
        now = utc_now().isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE outbox
                SET status = ?, approved_by = ?, approved_at = ?, error = NULL, updated_at = ?
                WHERE id = ? AND status IN (?, ?)
                """,
                (
                    OutboxStatus.APPROVED.value,
                    actor,
                    now,
                    now,
                    outbox_id,
                    OutboxStatus.PROPOSED.value,
                    OutboxStatus.FAILED.value,
                ),
            )
            if cursor.rowcount != 1:
                existing = self._row_or_none(connection, outbox_id)
                if existing is None:
                    raise NotFoundError(f"Outbox item not found: {outbox_id}")
                raise InvalidStateTransitionError(
                    f"Outbox item cannot be approved from state {existing['status']}"
                )
        return self.get_outbox(outbox_id)

    def mark_outbox_dispatched(
        self,
        outbox_id: str,
        *,
        receipt: DispatchReceipt,
    ) -> OutboxRecord:
        now = utc_now().isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE outbox
                SET status = ?, dispatched_at = ?, dispatch_receipt_json = ?,
                    error = NULL, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    OutboxStatus.DISPATCHED.value,
                    now,
                    receipt.model_dump_json(),
                    now,
                    outbox_id,
                    OutboxStatus.APPROVED.value,
                ),
            )
            if cursor.rowcount != 1:
                existing = self._row_or_none(connection, outbox_id)
                if existing is None:
                    raise NotFoundError(f"Outbox item not found: {outbox_id}")
                if existing["status"] == OutboxStatus.DISPATCHED.value:
                    return self.get_outbox(outbox_id)
                raise InvalidStateTransitionError(
                    f"Outbox item cannot be dispatched from state {existing['status']}"
                )
        return self.get_outbox(outbox_id)

    def mark_outbox_failed(self, outbox_id: str, *, error: str) -> OutboxRecord:
        now = utc_now().isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE outbox
                SET status = ?, error = ?, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    OutboxStatus.FAILED.value,
                    error[:2_000],
                    now,
                    outbox_id,
                    OutboxStatus.APPROVED.value,
                ),
            )
            if cursor.rowcount != 1:
                raise InvalidStateTransitionError("Only approved outbox items can fail dispatch")
        return self.get_outbox(outbox_id)

    @staticmethod
    def _row_or_none(connection: sqlite3.Connection, outbox_id: str) -> sqlite3.Row | None:
        return connection.execute("SELECT * FROM outbox WHERE id = ?", (outbox_id,)).fetchone()


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _outbox_from_row(row: sqlite3.Row) -> OutboxRecord:
    payload = CommunicationDraft.model_validate_json(row["payload_json"])
    receipt = (
        DispatchReceipt.model_validate_json(row["dispatch_receipt_json"]).model_dump(mode="json")
        if row["dispatch_receipt_json"]
        else None
    )
    return OutboxRecord(
        id=row["id"],
        run_id=row["run_id"],
        draft=payload,
        status=OutboxStatus(row["status"]),
        approved_by=row["approved_by"],
        approved_at=_parse_datetime(row["approved_at"]),
        dispatched_at=_parse_datetime(row["dispatched_at"]),
        dispatch_receipt=receipt,
        error=row["error"],
        created_at=_parse_datetime(row["created_at"]),
        updated_at=_parse_datetime(row["updated_at"]),
    )
