from __future__ import annotations

import asyncio

import pytest

from workflow_ai.exceptions import DispatchDisabledError
from workflow_ai.integrations.webhook import WebhookDispatcher
from workflow_ai.models import DispatchReceipt, OutboxStatus, SourceDocument
from workflow_ai.services import Services


def test_outbox_unknown_mode_and_missing_webhook_url(
    services: Services,
    meeting_source: SourceDocument,
) -> None:
    result = asyncio.run(services.intake.ingest(meeting_source))
    outbox_id = result.outbox_ids[0]
    services.outbox.approve(outbox_id, actor="ehza")

    with pytest.raises(DispatchDisabledError, match="Unknown dispatch mode"):
        asyncio.run(services.outbox.dispatch(outbox_id, actor="ehza", mode="carrier-pigeon"))

    services.settings.live_dispatch_enabled = True
    services.settings.webhook_url = None
    with pytest.raises(DispatchDisabledError, match="not configured"):
        asyncio.run(services.outbox.dispatch(outbox_id, actor="ehza", mode="webhook"))


def test_webhook_failure_is_persisted_and_can_be_reapproved(
    monkeypatch,
    services: Services,
    meeting_source: SourceDocument,
) -> None:
    result = asyncio.run(services.intake.ingest(meeting_source))
    outbox_id = result.outbox_ids[0]
    services.settings.live_dispatch_enabled = True
    services.settings.webhook_url = "https://example.invalid/hook"
    services.outbox.approve(outbox_id, actor="ehza")

    async def fail(_self, _item):
        raise RuntimeError("downstream unavailable")

    monkeypatch.setattr(WebhookDispatcher, "dispatch", fail)
    with pytest.raises(RuntimeError, match="downstream unavailable"):
        asyncio.run(services.outbox.dispatch(outbox_id, actor="ehza", mode="webhook"))

    failed = services.store.get_outbox(outbox_id)
    assert failed.status is OutboxStatus.FAILED
    assert "RuntimeError" in (failed.error or "")
    events = services.store.list_audit_events(run_id=result.run_id)
    assert any(event["event_type"] == "outbox.dispatch_failed" for event in events)

    retried = services.outbox.approve(outbox_id, actor="ehza")
    assert retried.status is OutboxStatus.APPROVED


def test_webhook_success_and_dispatched_short_circuit(
    monkeypatch,
    services: Services,
    meeting_source: SourceDocument,
) -> None:
    result = asyncio.run(services.intake.ingest(meeting_source))
    outbox_id = result.outbox_ids[0]
    services.settings.live_dispatch_enabled = True
    services.settings.webhook_url = "https://example.invalid/hook"
    services.outbox.approve(outbox_id, actor="ehza")
    calls = 0

    async def succeed(_self, _item):
        nonlocal calls
        calls += 1
        return DispatchReceipt(dispatcher="webhook", external_id="remote-1")

    monkeypatch.setattr(WebhookDispatcher, "dispatch", succeed)
    first = asyncio.run(services.outbox.dispatch(outbox_id, actor="ehza", mode="webhook"))
    second = asyncio.run(services.outbox.dispatch(outbox_id, actor="ehza", mode="webhook"))

    assert first.status is OutboxStatus.DISPATCHED
    assert second.status is OutboxStatus.DISPATCHED
    assert calls == 1
