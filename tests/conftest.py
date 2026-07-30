from __future__ import annotations

from pathlib import Path

import pytest

from workflow_ai.config import Settings
from workflow_ai.models import ArtifactKind, Sensitivity, SourceDocument
from workflow_ai.services import Services


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        workspace_root=tmp_path,
        vault_path=Path("vault"),
        runtime_path=Path(".workflow-ai"),
        llm_provider="deterministic",
    )


@pytest.fixture
def services(settings: Settings) -> Services:
    return Services.build(settings)


@pytest.fixture
def meeting_source() -> SourceDocument:
    return SourceDocument(
        source_name="leadership-sync.txt",
        kind=ArtifactKind.MEETING,
        content="""TITLE: Product Launch Leadership Sync
DATE: 2026-07-30T15:00:00+00:00
PARTICIPANTS: Maya Chen, Omar Rahman
PROJECT: Atlas Launch
TOPICS: launch readiness, legal review
The launch remains on track for August 18.
DECISION: Keep the August 18 launch date | Readiness checks passed | Maya Chen
ACTION: omar@example.com | 2026-08-04 | high | Obtain final legal approval
RISK: high | Legal review may delay onboarding | Escalate unresolved clauses
QUESTION: Are support staffing levels sufficient?
""",
        projects=["Atlas Launch"],
        sensitivity=Sensitivity.INTERNAL,
        metadata={"stakeholders": "chief-of-staff@example.com"},
    )
