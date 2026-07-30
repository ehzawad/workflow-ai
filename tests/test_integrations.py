from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from workflow_ai.integrations.filesystem import FilesystemDispatcher
from workflow_ai.integrations.webhook import WebhookDispatcher
from workflow_ai.models import (
    CommunicationChannel,
    CommunicationDraft,
    OutboxRecord,
    OutboxStatus,
)
from workflow_ai.utils import utc_now


def _record(draft: CommunicationDraft, *, identifier: str) -> OutboxRecord:
    now = utc_now()
    return OutboxRecord(
        id=identifier,
        run_id=None,
        draft=draft,
        status=OutboxStatus.APPROVED,
        approved_by="ehza",
        approved_at=now,
        dispatched_at=None,
        dispatch_receipt=None,
        error=None,
        created_at=now,
        updated_at=now,
    )


def test_filesystem_dispatcher_exports_all_channels(tmp_path: Path) -> None:
    dispatcher = FilesystemDispatcher(tmp_path / "dispatch")

    email = CommunicationDraft(
        channel=CommunicationChannel.EMAIL,
        recipients=["owner@example.com"],
        subject="Action / review",
        body="Please confirm.",
        start_at=None,
        end_at=None,
        timezone=None,
        location=None,
    )
    email_receipt = asyncio.run(dispatcher.dispatch(_record(email, identifier="email-id")))
    email_path = Path(email_receipt.external_id)
    assert email_path.suffix == ".eml"
    assert "To: owner@example.com" in email_path.read_text(encoding="utf-8")
    assert email_receipt.detail["network_side_effect"] is False

    start = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)
    calendar = CommunicationDraft(
        channel=CommunicationChannel.CALENDAR,
        recipients=["owner@example.com"],
        subject="Review; launch, readiness",
        body="Line one\nLine two",
        start_at=start,
        end_at=start + timedelta(minutes=30),
        timezone="UTC",
        location="Room, 2",
    )
    calendar_receipt = asyncio.run(
        dispatcher.dispatch(_record(calendar, identifier="calendar-id"))
    )
    calendar_text = Path(calendar_receipt.external_id).read_text(encoding="utf-8")
    assert "BEGIN:VCALENDAR" in calendar_text
    assert "SUMMARY:Review\\; launch\\, readiness" in calendar_text
    assert "ATTENDEE:mailto:owner@example.com" in calendar_text
    assert "DESCRIPTION:Line one\\nLine two" in calendar_text

    stakeholder = CommunicationDraft(
        channel=CommunicationChannel.STAKEHOLDER,
        recipients=[],
        subject="Leadership update",
        body="Status is green.",
        start_at=None,
        end_at=None,
        timezone=None,
        location=None,
    )
    stakeholder_receipt = asyncio.run(
        dispatcher.dispatch(_record(stakeholder, identifier="stakeholder-id"))
    )
    stakeholder_text = Path(stakeholder_receipt.external_id).read_text(encoding="utf-8")
    assert "**Recipients:** _Unassigned_" in stakeholder_text
    assert "Status is green." in stakeholder_text


def test_webhook_dispatcher_posts_typed_payload(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 202
        headers = {"x-request-id": "request-123"}

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def post(self, url: str, *, json: dict[str, Any]):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    draft = CommunicationDraft(
        channel=CommunicationChannel.STAKEHOLDER,
        recipients=["chief-of-staff@example.com"],
        subject="Update",
        body="Body",
        start_at=None,
        end_at=None,
        timezone=None,
        location=None,
    )
    receipt = asyncio.run(
        WebhookDispatcher("https://example.invalid/hook", timeout_seconds=3.0).dispatch(
            _record(draft, identifier="webhook-id")
        )
    )

    assert captured["url"] == "https://example.invalid/hook"
    assert captured["timeout"] == 3.0
    assert captured["json"]["event"] == "workflow_ai.communication.approved"
    assert captured["json"]["outbox_id"] == "webhook-id"
    assert receipt.external_id == "request-123"
    assert receipt.detail["network_side_effect"] is True
