from __future__ import annotations

import asyncio
from datetime import date

from workflow_ai.models import DailyBrief, DecisionBriefDraft, SourceDocument
from workflow_ai.services import Services


def test_daily_and_decision_briefs_are_written(
    services: Services,
    meeting_source: SourceDocument,
) -> None:
    asyncio.run(services.intake.ingest(meeting_source))

    daily_result = asyncio.run(services.briefs.daily(brief_date=date(2026, 7, 31)))
    assert isinstance(daily_result.brief, DailyBrief)
    assert daily_result.brief.action_items
    assert (services.settings.vault_path / daily_result.note_path).exists()

    decision_result = asyncio.run(
        services.briefs.decision(question="Should we keep the August 18 launch date?")
    )
    assert isinstance(decision_result.brief, DecisionBriefDraft)
    assert decision_result.brief.options
    assert (services.settings.vault_path / decision_result.note_path).exists()
