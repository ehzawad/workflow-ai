from __future__ import annotations

import asyncio
from pathlib import Path

from workflow_ai.models import SourceDocument
from workflow_ai.services import Services


def test_intake_is_idempotent_writes_vault_and_indexes(
    services: Services,
    meeting_source: SourceDocument,
) -> None:
    first = asyncio.run(services.intake.ingest(meeting_source))
    second = asyncio.run(services.intake.ingest(meeting_source))

    assert first.reused is False
    assert second.reused is True
    assert first.run_id == second.run_id
    assert first.note_path == second.note_path
    assert len(first.outbox_ids) == 3

    note = services.settings.vault_path / first.note_path
    assert note.exists()
    text = note.read_text(encoding="utf-8")
    assert "## Decisions" in text
    assert "## Action items" in text
    assert "Original source text" in text

    hits = services.index.search("legal approval onboarding")
    assert hits
    assert hits[0].path == first.note_path

    events = services.store.list_audit_events(run_id=first.run_id)
    serialized = str(events)
    assert "The launch remains on track" not in serialized
    assert "source_hash" in serialized


def test_project_index_is_created(services: Services, meeting_source: SourceDocument) -> None:
    asyncio.run(services.intake.ingest(meeting_source))
    project_index = services.settings.vault_path / "30_Projects" / "atlas-launch" / "README.md"
    assert project_index.exists()
