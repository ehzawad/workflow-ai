"""Offline deterministic provider used for demos, tests, and graceful degradation."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path

from workflow_ai.llm.base import LLMProvider
from workflow_ai.models import (
    ActionItem,
    ActionStatus,
    ArtifactKind,
    Confidence,
    Decision,
    DecisionBriefDraft,
    DecisionOption,
    KnowledgeArtifact,
    Priority,
    Risk,
    SearchHit,
    SourceDocument,
)
from workflow_ai.utils import deduplicate

_DIRECTIVE_RE = re.compile(
    r"^(TITLE|DATE|PARTICIPANTS?|PROJECTS?|TOPICS?|ACTION|DECISION|RISK|QUESTION|LINK)\s*:\s*(.*)$",
    flags=re.IGNORECASE,
)
_CHECKBOX_RE = re.compile(r"^\s*[-*]\s*\[\s\]\s*(.+)$")
_DUE_RE = re.compile(r"\b(?:due|by)\s+(\d{4}-\d{2}-\d{2})\b", flags=re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", flags=re.IGNORECASE)


class DeterministicProvider(LLMProvider):
    """Parse a documented line-oriented convention without any network access."""

    name = "deterministic"

    async def normalize(self, source: SourceDocument) -> KnowledgeArtifact:
        title: str | None = None
        occurred_at = source.occurred_at
        participants = list(source.participants)
        projects = list(source.projects)
        topics: list[str] = []
        actions: list[ActionItem] = []
        decisions: list[Decision] = []
        risks: list[Risk] = []
        questions: list[str] = []
        links: list[str] = []
        narrative_lines: list[str] = []

        for raw_line in source.content.splitlines():
            line = raw_line.strip()
            if not line:
                narrative_lines.append("")
                continue

            directive = _DIRECTIVE_RE.match(line)
            if directive:
                key = directive.group(1).upper()
                value = directive.group(2).strip()
                if key == "TITLE":
                    title = value or title
                elif key == "DATE":
                    occurred_at = _parse_datetime(value) or occurred_at
                elif key.startswith("PARTICIPANT"):
                    participants.extend(_split_csv(value))
                elif key.startswith("PROJECT"):
                    projects.extend(_split_csv(value))
                elif key.startswith("TOPIC"):
                    topics.extend(_split_csv(value))
                elif key == "ACTION" and value:
                    actions.append(_parse_action(value))
                elif key == "DECISION" and value:
                    decisions.append(_parse_decision(value, occurred_at))
                elif key == "RISK" and value:
                    risks.append(_parse_risk(value))
                elif key == "QUESTION" and value:
                    questions.append(value)
                elif key == "LINK" and value:
                    links.append(value)
                continue

            checkbox = _CHECKBOX_RE.match(raw_line)
            if checkbox:
                actions.append(_parse_checkbox_action(checkbox.group(1)))
                continue

            if title is None and line.startswith("#"):
                title = line.lstrip("#").strip()
                continue
            narrative_lines.append(raw_line.rstrip())

        title = title or _fallback_title(source)
        summary = _summarize(narrative_lines, fallback=title)
        if not topics:
            topics = _derive_topics(title, projects)

        return KnowledgeArtifact(
            title=title,
            kind=source.kind,
            occurred_at=occurred_at,
            summary=summary,
            participants=deduplicate(participants),
            projects=deduplicate(projects),
            topics=deduplicate(topics),
            decisions=decisions,
            action_items=actions,
            risks=risks,
            open_questions=deduplicate(questions),
            suggested_links=deduplicate(links),
            sensitivity=source.sensitivity,
        )

    async def decision_brief(
        self,
        *,
        question: str,
        evidence: list[SearchHit],
    ) -> DecisionBriefDraft:
        refs = [hit.path for hit in evidence]
        evidence_lines = [f"{hit.title}: {_clean_snippet(hit.snippet)}" for hit in evidence]
        if evidence:
            summary = (
                f"The vault contains {len(evidence)} potentially relevant source note"
                f"{'s' if len(evidence) != 1 else ''}. The strongest retrieved context is "
                f"“{evidence[0].title}”."
            )
            recommendation = (
                "Use the retrieved evidence as a starting point, verify its current status with the "
                "named owners, and decide only after the listed uncertainties are resolved."
            )
            confidence = Confidence.MEDIUM
        else:
            summary = "No supporting vault evidence was retrieved for this question."
            recommendation = "Defer the decision until the minimum evidence packet is assembled."
            confidence = Confidence.LOW

        options = [
            DecisionOption(
                name="Proceed after targeted validation",
                description="Validate the highest-impact assumptions with owners, then make a bounded decision.",
                benefits=["Preserves momentum", "Makes uncertainty explicit"],
                drawbacks=["Requires a short validation cycle"],
                evidence_refs=refs[:5],
            ),
            DecisionOption(
                name="Defer and collect more evidence",
                description="Pause the decision and gather the missing operational or financial inputs.",
                benefits=["Reduces avoidable commitment risk"],
                drawbacks=["May delay execution and stakeholder alignment"],
                evidence_refs=refs[:5],
            ),
        ]
        return DecisionBriefDraft(
            question=question,
            executive_summary=summary,
            recommendation=recommendation,
            confidence=confidence,
            options=options,
            evidence=evidence_lines,
            uncertainties=(
                ["The retrieved notes may be stale or incomplete.", "Owner confirmation is not recorded."]
                if evidence
                else ["No internal evidence was retrieved."]
            ),
            next_steps=[
                "Confirm the decision deadline and decision owner.",
                "Validate the top assumptions against current source-of-truth systems.",
                "Record the final decision and rationale in the vault.",
            ],
        )


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,;]", value) if item.strip()]


def _parse_datetime(value: str) -> datetime | None:
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(cleaned)
        except ValueError:
            return None
        return datetime.combine(parsed_date, datetime.min.time(), tzinfo=UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _priority(value: str, default: Priority = Priority.MEDIUM) -> Priority:
    normalized = value.strip().lower()
    try:
        return Priority(normalized)
    except ValueError:
        return default


def _parse_action(value: str) -> ActionItem:
    parts = [part.strip() for part in value.split("|")]
    if len(parts) >= 4:
        owner = parts[0] or None
        due = _parse_date(parts[1])
        priority = _priority(parts[2])
        description = " | ".join(parts[3:]).strip()
    elif len(parts) == 3:
        owner = parts[0] or None
        due = _parse_date(parts[1])
        priority = Priority.MEDIUM
        description = parts[2]
    elif len(parts) == 2:
        owner = parts[0] or None
        due = None
        priority = Priority.MEDIUM
        description = parts[1]
    else:
        owner = None
        due = None
        priority = Priority.MEDIUM
        description = value
    return ActionItem(
        description=description or value,
        owner=owner,
        due_date=due,
        priority=priority,
        status=ActionStatus.OPEN,
        evidence=value,
    )


def _parse_checkbox_action(value: str) -> ActionItem:
    due_match = _DUE_RE.search(value)
    due = _parse_date(due_match.group(1)) if due_match else None
    email_match = _EMAIL_RE.search(value)
    owner = email_match.group(0) if email_match else None
    description = _DUE_RE.sub("", value).strip(" -–—,;.")
    return ActionItem(
        description=description,
        owner=owner,
        due_date=due,
        priority=Priority.MEDIUM,
        status=ActionStatus.OPEN,
        evidence=value,
    )


def _parse_decision(value: str, occurred_at: datetime | None) -> Decision:
    parts = [part.strip() for part in value.split("|")]
    statement = parts[0]
    rationale = parts[1] if len(parts) > 1 and parts[1] else None
    owner = parts[2] if len(parts) > 2 and parts[2] else None
    return Decision(
        statement=statement,
        rationale=rationale,
        owner=owner,
        decided_on=occurred_at.date() if occurred_at else None,
        evidence=value,
    )


def _parse_risk(value: str) -> Risk:
    parts = [part.strip() for part in value.split("|")]
    if len(parts) >= 3:
        severity = _priority(parts[0])
        description = parts[1]
        mitigation = " | ".join(parts[2:]) or None
    elif len(parts) == 2:
        severity = _priority(parts[0])
        description = parts[1]
        mitigation = None
    else:
        severity = Priority.MEDIUM
        description = value
        mitigation = None
    return Risk(
        description=description,
        severity=severity,
        owner=None,
        mitigation=mitigation,
        evidence=value,
    )


def _fallback_title(source: SourceDocument) -> str:
    stem = Path(source.source_name).stem.replace("_", "-").replace("-", " ").strip()
    return stem.title() or "Untitled Note"


def _summarize(lines: list[str], *, fallback: str) -> str:
    text = "\n".join(lines).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return fallback
    if len(text) <= 600:
        return text
    cutoff = text.rfind(". ", 0, 600)
    return text[: cutoff + 1 if cutoff >= 200 else 600].rstrip() + "…"


def _derive_topics(title: str, projects: list[str]) -> list[str]:
    stop = {"the", "and", "for", "with", "from", "into", "meeting", "notes", "update"}
    title_words = [
        word.lower()
        for word in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", title)
        if word.lower() not in stop
    ]
    return deduplicate([*projects, *title_words[:5]])


def _clean_snippet(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value).strip()
