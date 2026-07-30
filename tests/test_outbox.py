from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from workflow_ai.exceptions import DispatchDisabledError, InvalidStateTransitionError
from workflow_ai.models import CommunicationDraft, OutboxStatus, SourceDocument
from workflow_ai.services import Services


def test_outbox_requires_approval_before_any_side_effect(
    services: Services,
    meeting_source: SourceDocument,
) -> None:
    result = asyncio.run(services.intake.ingest(meeting_source))
    outbox_id = result.outbox_ids[0]

    with pytest.raises(InvalidStateTransitionError):
        asyncio.run(services.outbox.dispatch(outbox_id, actor="ehza"))

    assert list(services.settings.dispatch_path.rglob("*.*")) == []


def test_approved_outbox_exports_reviewable_file(
    services: Services,
    meeting_source: SourceDocument,
) -> None:
    result = asyncio.run(services.intake.ingest(meeting_source))
    outbox_id = result.outbox_ids[0]

    approved = services.outbox.approve(outbox_id, actor="ehza")
    assert approved.status is OutboxStatus.APPROVED

    dispatched = asyncio.run(services.outbox.dispatch(outbox_id, actor="ehza"))
    assert dispatched.status is OutboxStatus.DISPATCHED
    assert dispatched.dispatch_receipt is not None
    exported = Path(dispatched.dispatch_receipt["external_id"])
    assert exported.exists()


def test_edit_revokes_approval(services: Services, meeting_source: SourceDocument) -> None:
    result = asyncio.run(services.intake.ingest(meeting_source))
    item = services.outbox.approve(result.outbox_ids[0], actor="ehza")
    updated_draft = CommunicationDraft.model_validate(
        {**item.draft.model_dump(mode="python"), "subject": "Reviewed subject"}
    )

    edited = services.outbox.edit(item.id, draft=updated_draft, actor="ehza")

    assert edited.status is OutboxStatus.PROPOSED
    assert edited.approved_by is None
    assert edited.draft.subject == "Reviewed subject"


def test_live_webhook_is_disabled_by_default(
    services: Services,
    meeting_source: SourceDocument,
) -> None:
    result = asyncio.run(services.intake.ingest(meeting_source))
    services.outbox.approve(result.outbox_ids[0], actor="ehza")

    with pytest.raises(DispatchDisabledError):
        asyncio.run(
            services.outbox.dispatch(result.outbox_ids[0], actor="ehza", mode="webhook")
        )
