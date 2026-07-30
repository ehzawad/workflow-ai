from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from workflow_ai.exceptions import PathSafetyError
from workflow_ai.models import ArtifactKind, CommunicationChannel, CommunicationDraft, SourceDocument
from workflow_ai.utils import safe_child, slugify
from workflow_ai.vault.frontmatter import dump_markdown, load_markdown


def test_frontmatter_round_trip() -> None:
    metadata = {"title": "A note", "tags": ["one", "two"], "nested": {"value": 3}}
    rendered = dump_markdown(metadata, "# A note\n\nBody")
    loaded, body = load_markdown(rendered)

    assert loaded == metadata
    assert body.startswith("# A note")


def test_safe_child_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(PathSafetyError):
        safe_child(tmp_path, "../outside.txt")


def test_slugify_is_stable_and_safe() -> None:
    assert slugify("  Executive's Q3 Plan / 2026  ") == "executive-s-q3-plan-2026"


def test_boundary_datetimes_are_normalized_to_utc() -> None:
    source = SourceDocument(
        source_name="note.txt",
        kind=ArtifactKind.NOTE,
        content="Body",
        occurred_at=datetime(2026, 7, 31, 12, 0),
    )
    assert source.occurred_at is not None
    assert source.occurred_at.tzinfo is not None

    draft = CommunicationDraft(
        channel=CommunicationChannel.CALENDAR,
        recipients=[],
        subject="Review",
        body="Review status",
        start_at=datetime(2026, 8, 1, 9, 0),
        end_at=datetime(2026, 8, 1, 9, 30),
        timezone="UTC",
        location=None,
    )
    assert draft.start_at is not None and draft.start_at.tzinfo is not None
    assert draft.end_at is not None and draft.end_at.tzinfo is not None
