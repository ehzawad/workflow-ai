"""Executive daily and decision brief workflows."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from workflow_ai.llm.base import LLMProvider
from workflow_ai.models import (
    ActionItem,
    ActionStatus,
    BriefResult,
    DailyBrief,
    KnowledgeArtifact,
    Priority,
    Risk,
)
from workflow_ai.store import WorkflowStore
from workflow_ai.utils import canonical_json, sha256_text
from workflow_ai.vault.index import VaultIndex
from workflow_ai.vault.writer import VaultWriter

_PRIORITY_RANK = {
    Priority.CRITICAL: 0,
    Priority.HIGH: 1,
    Priority.MEDIUM: 2,
    Priority.LOW: 3,
}


class BriefWorkflow:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        store: WorkflowStore,
        writer: VaultWriter,
        index: VaultIndex,
    ) -> None:
        self.provider = provider
        self.store = store
        self.writer = writer
        self.index = index

    async def daily(self, *, brief_date: date | None = None) -> BriefResult:
        target = brief_date or datetime.now(UTC).date()
        records = self.writer.iter_artifacts()
        fingerprint_payload = [
            {"path": self.writer.relative(path), "artifact": artifact.model_dump(mode="json")}
            for path, artifact in records
        ]
        input_hash = sha256_text(canonical_json({"date": target, "records": fingerprint_payload}))
        row, reused = self.store.begin_run(
            workflow_type="daily_brief",
            idempotency_key=f"daily-brief:{target.isoformat()}:{input_hash[:16]}",
            input_hash=input_hash,
        )
        run_id = str(row["id"])
        if reused:
            return BriefResult.model_validate(self.store.decode_run_output(row))

        try:
            brief = _compile_daily_brief(records, target=target, writer=self.writer)
            path = self.writer.write_daily_brief(brief=brief, run_id=run_id)
            self.index.upsert(path)
            result = BriefResult(
                run_id=run_id,
                note_path=self.writer.relative(path),
                brief=brief,
            )
            self.store.complete_run(
                run_id,
                output=result.model_dump(mode="json"),
                note_path=result.note_path,
            )
            self.store.add_audit_event(
                run_id=run_id,
                event_type="brief.daily_completed",
                payload={
                    "brief_date": target.isoformat(),
                    "note_path": result.note_path,
                    "source_count": len(records),
                    "action_count": len(brief.action_items),
                    "risk_count": len(brief.risks),
                },
            )
            return result
        except Exception as error:
            self.store.fail_run(run_id, error=f"{type(error).__name__}: {error}")
            raise

    async def decision(
        self,
        *,
        question: str,
        evidence_limit: int = 8,
    ) -> BriefResult:
        hits = self.index.search(question, limit=evidence_limit)
        input_payload = {
            "question": question,
            "provider": self.provider.name,
            "evidence": [hit.model_dump(mode="json") for hit in hits],
        }
        input_hash = sha256_text(canonical_json(input_payload))
        row, reused = self.store.begin_run(
            workflow_type="decision_brief",
            idempotency_key=f"decision-brief:{input_hash}",
            input_hash=input_hash,
        )
        run_id = str(row["id"])
        if reused:
            return BriefResult.model_validate(self.store.decode_run_output(row))

        try:
            brief = await self.provider.decision_brief(question=question, evidence=hits)
            path = self.writer.write_decision_brief(
                brief=brief,
                run_id=run_id,
                evidence_paths=[hit.path for hit in hits],
            )
            self.index.upsert(path)
            result = BriefResult(
                run_id=run_id,
                note_path=self.writer.relative(path),
                brief=brief,
            )
            self.store.complete_run(
                run_id,
                output=result.model_dump(mode="json"),
                note_path=result.note_path,
            )
            self.store.add_audit_event(
                run_id=run_id,
                event_type="brief.decision_completed",
                payload={
                    "note_path": result.note_path,
                    "evidence_count": len(hits),
                    "provider": self.provider.name,
                },
            )
            return result
        except Exception as error:
            self.store.fail_run(run_id, error=f"{type(error).__name__}: {error}")
            raise


def _compile_daily_brief(
    records: list[tuple[Path, KnowledgeArtifact]],
    *,
    target: date,
    writer: VaultWriter,
) -> DailyBrief:
    selected: list[tuple[Path, KnowledgeArtifact]] = []
    for path, artifact in records:
        artifact_date = artifact.occurred_at.date() if artifact.occurred_at else target
        if artifact_date <= target:
            selected.append((path, artifact))

    selected.sort(key=lambda item: _artifact_sort_key(item[1]), reverse=True)
    action_items = _unique_actions(
        action
        for _, artifact in selected
        for action in artifact.action_items
        if action.status is not ActionStatus.DONE
    )
    action_items.sort(key=lambda action: _action_sort_key(action, target=target))

    risks = _unique_risks(risk for _, artifact in selected for risk in artifact.risks)
    risks.sort(key=lambda risk: _PRIORITY_RANK[risk.severity])

    recent_cutoff = target - timedelta(days=14)
    decisions = [
        decision.statement
        for _, artifact in selected
        if (artifact.occurred_at.date() if artifact.occurred_at else target) >= recent_cutoff
        for decision in artifact.decisions
    ][:12]
    questions = _deduplicate_text(
        question for _, artifact in selected for question in artifact.open_questions
    )[:12]
    source_notes = [writer.relative(path) for path, _ in selected[:20]]

    priorities: list[str] = []
    for action in action_items:
        if action.priority in {Priority.CRITICAL, Priority.HIGH} or (
            action.due_date is not None and action.due_date <= target + timedelta(days=7)
        ):
            owner = f" ({action.owner})" if action.owner else ""
            due = f" — due {action.due_date.isoformat()}" if action.due_date else ""
            priorities.append(f"{action.description}{owner}{due}")
    for risk in risks:
        if risk.severity in {Priority.CRITICAL, Priority.HIGH}:
            priorities.append(f"Mitigate {risk.severity.value} risk: {risk.description}")
    priorities = _deduplicate_text(iter(priorities))[:7]

    summary = (
        f"Across {len(selected)} indexed knowledge notes, the brief surfaces "
        f"{len(action_items)} open action item(s), {len(decisions)} recent decision(s), "
        f"and {len(risks)} active risk(s)."
    )
    if not selected:
        summary = "No normalized knowledge artifacts are available for this date."

    return DailyBrief(
        title=f"Daily executive brief — {target.isoformat()}",
        brief_date=target,
        executive_summary=summary,
        priorities=priorities,
        decisions=_deduplicate_text(iter(decisions))[:12],
        action_items=action_items[:30],
        risks=risks[:20],
        open_questions=questions,
        source_notes=source_notes,
    )


def _artifact_sort_key(artifact: KnowledgeArtifact) -> datetime:
    return artifact.occurred_at or datetime.min.replace(tzinfo=UTC)


def _action_sort_key(action: ActionItem, *, target: date) -> tuple[int, date, str]:
    due = action.due_date or date.max
    overdue_bias = -1 if action.due_date is not None and action.due_date < target else 0
    return overdue_bias + _PRIORITY_RANK[action.priority], due, action.description.casefold()


def _unique_actions(values: Iterable[ActionItem]) -> list[ActionItem]:
    seen: set[tuple[str, str]] = set()
    result: list[ActionItem] = []
    for item in values:
        key = (item.description.casefold(), (item.owner or "").casefold())
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _unique_risks(values: Iterable[Risk]) -> list[Risk]:
    seen: set[str] = set()
    result: list[Risk] = []
    for item in values:
        key = item.description.casefold()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _deduplicate_text(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.casefold().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(value.strip())
    return result
