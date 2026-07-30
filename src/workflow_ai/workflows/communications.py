"""Rule-based communication proposals derived from normalized commitments."""

from __future__ import annotations

import re
from datetime import UTC, datetime, time, timedelta

from workflow_ai.models import (
    CommunicationChannel,
    CommunicationDraft,
    KnowledgeArtifact,
    SourceDocument,
)
from workflow_ai.utils import deduplicate

_EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", flags=re.IGNORECASE)


class CommunicationPlanner:
    """Propose drafts only; authorization remains an explicit human transition."""

    def propose(
        self,
        *,
        artifact: KnowledgeArtifact,
        source: SourceDocument,
    ) -> list[CommunicationDraft]:
        drafts: list[CommunicationDraft] = []
        stakeholder_recipients = _metadata_recipients(source)

        if artifact.decisions or artifact.action_items or artifact.risks:
            drafts.append(
                CommunicationDraft(
                    channel=CommunicationChannel.STAKEHOLDER,
                    recipients=stakeholder_recipients,
                    subject=f"Update: {artifact.title}",
                    body=_stakeholder_body(artifact),
                    start_at=None,
                    end_at=None,
                    timezone=None,
                    location=None,
                    metadata={"source": source.source_name, "requires_recipient_review": "true"},
                )
            )

        for action in artifact.action_items:
            if action.owner and _EMAIL_RE.fullmatch(action.owner):
                due_text = f" by {action.due_date.isoformat()}" if action.due_date else ""
                drafts.append(
                    CommunicationDraft(
                        channel=CommunicationChannel.EMAIL,
                        recipients=[action.owner],
                        subject=f"Action from {artifact.title}",
                        body=(
                            f"Hello,\n\nThis is a draft follow-up for the action below:\n\n"
                            f"{action.description}{due_text}.\n\n"
                            "Please confirm ownership, timing, and any blockers.\n"
                        ),
                        start_at=None,
                        end_at=None,
                        timezone=None,
                        location=None,
                        metadata={"source": source.source_name, "action_priority": action.priority.value},
                    )
                )

            if action.due_date is not None:
                start = datetime.combine(action.due_date, time(hour=9), tzinfo=UTC)
                drafts.append(
                    CommunicationDraft(
                        channel=CommunicationChannel.CALENDAR,
                        recipients=[action.owner]
                        if action.owner and _EMAIL_RE.fullmatch(action.owner)
                        else [],
                        subject=f"Review: {action.description[:90]}",
                        body=(
                            f"Review progress on the action captured in {artifact.title}.\n\n"
                            f"Action: {action.description}"
                        ),
                        start_at=start,
                        end_at=start + timedelta(minutes=30),
                        timezone="UTC",
                        location=None,
                        metadata={"source": source.source_name, "tentative": "true"},
                    )
                )

        return drafts


def _metadata_recipients(source: SourceDocument) -> list[str]:
    raw = source.metadata.get("stakeholders") or source.metadata.get("stakeholder_recipients") or ""
    return deduplicate(re.split(r"[,;]", raw))


def _stakeholder_body(artifact: KnowledgeArtifact) -> str:
    lines = [artifact.summary]
    if artifact.decisions:
        lines.extend(["", "Decisions:", *[f"- {item.statement}" for item in artifact.decisions]])
    if artifact.action_items:
        lines.extend(
            [
                "",
                "Action items:",
                *[
                    f"- {item.description}"
                    + (f" — {item.owner}" if item.owner else "")
                    + (f" — due {item.due_date.isoformat()}" if item.due_date else "")
                    for item in artifact.action_items
                ],
            ]
        )
    if artifact.risks:
        lines.extend(["", "Risks:", *[f"- {item.description}" for item in artifact.risks]])
    return "\n".join(lines).strip() + "\n"
