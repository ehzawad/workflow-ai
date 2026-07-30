"""Typed domain contracts for extraction, persistence, APIs, and evaluations."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from workflow_ai.utils import deduplicate, utc_now


class StrictModel(BaseModel):
    """Base model that rejects unknown keys and normalizes surrounding whitespace."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)


class ArtifactKind(StrEnum):
    MEETING = "meeting"
    TRANSCRIPT = "transcript"
    PROJECT_UPDATE = "project_update"
    NOTE = "note"
    EMAIL = "email"
    DECISION = "decision"
    BRIEF = "brief"


class Sensitivity(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionStatus(StrEnum):
    OPEN = "open"
    BLOCKED = "blocked"
    DONE = "done"


class WorkflowStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class OutboxStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    DISPATCHED = "dispatched"
    FAILED = "failed"


class CommunicationChannel(StrEnum):
    EMAIL = "email"
    CALENDAR = "calendar"
    STAKEHOLDER = "stakeholder"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionItem(StrictModel):
    description: str = Field(min_length=1)
    owner: str | None
    due_date: date | None
    priority: Priority
    status: ActionStatus
    evidence: str | None


class Decision(StrictModel):
    statement: str = Field(min_length=1)
    rationale: str | None
    owner: str | None
    decided_on: date | None
    evidence: str | None


class Risk(StrictModel):
    description: str = Field(min_length=1)
    severity: Priority
    owner: str | None
    mitigation: str | None
    evidence: str | None


class SourceDocument(StrictModel):
    """Raw imported content and operator-supplied context."""

    source_name: str = Field(min_length=1, max_length=240)
    kind: ArtifactKind = ArtifactKind.NOTE
    content: str = Field(min_length=1)
    occurred_at: datetime | None = None
    participants: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("participants", "projects")
    @classmethod
    def _deduplicate_lists(cls, value: list[str]) -> list[str]:
        return deduplicate(value)

    @field_validator("occurred_at")
    @classmethod
    def _normalize_occurred_at(cls, value: datetime | None) -> datetime | None:
        return _assume_utc(value)


class KnowledgeArtifact(StrictModel):
    """Schema-constrained representation extracted from an unstructured source."""

    title: str = Field(min_length=1, max_length=240)
    kind: ArtifactKind
    occurred_at: datetime | None
    summary: str = Field(min_length=1)
    participants: list[str]
    projects: list[str]
    topics: list[str]
    decisions: list[Decision]
    action_items: list[ActionItem]
    risks: list[Risk]
    open_questions: list[str]
    suggested_links: list[str]
    sensitivity: Sensitivity

    @field_validator("participants", "projects", "topics", "open_questions", "suggested_links")
    @classmethod
    def _deduplicate_lists(cls, value: list[str]) -> list[str]:
        return deduplicate(value)

    @field_validator("occurred_at")
    @classmethod
    def _normalize_occurred_at(cls, value: datetime | None) -> datetime | None:
        return _assume_utc(value)


class SearchHit(StrictModel):
    path: str
    title: str
    snippet: str
    score: float
    tags: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)


class DecisionOption(StrictModel):
    name: str
    description: str
    benefits: list[str]
    drawbacks: list[str]
    evidence_refs: list[str]


class DecisionBriefDraft(StrictModel):
    question: str
    executive_summary: str
    recommendation: str
    confidence: Confidence
    options: list[DecisionOption]
    evidence: list[str]
    uncertainties: list[str]
    next_steps: list[str]


class DailyBrief(StrictModel):
    title: str
    brief_date: date
    executive_summary: str
    priorities: list[str]
    decisions: list[str]
    action_items: list[ActionItem]
    risks: list[Risk]
    open_questions: list[str]
    source_notes: list[str]
    generated_at: datetime = Field(default_factory=utc_now)


class CommunicationDraft(StrictModel):
    channel: CommunicationChannel
    recipients: list[str]
    subject: str
    body: str
    start_at: datetime | None
    end_at: datetime | None
    timezone: str | None
    location: str | None
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("recipients")
    @classmethod
    def _deduplicate_recipients(cls, value: list[str]) -> list[str]:
        return deduplicate(value)

    @field_validator("start_at", "end_at")
    @classmethod
    def _normalize_calendar_datetimes(cls, value: datetime | None) -> datetime | None:
        return _assume_utc(value)

    @model_validator(mode="after")
    def _validate_calendar_window(self) -> CommunicationDraft:
        if self.channel is CommunicationChannel.CALENDAR:
            if self.start_at is None or self.end_at is None:
                raise ValueError("Calendar drafts require start_at and end_at")
            if self.end_at <= self.start_at:
                raise ValueError("Calendar draft end_at must be after start_at")
        return self


class OutboxRecord(StrictModel):
    id: str
    run_id: str | None
    draft: CommunicationDraft
    status: OutboxStatus
    approved_by: str | None
    approved_at: datetime | None
    dispatched_at: datetime | None
    dispatch_receipt: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class DispatchReceipt(StrictModel):
    dispatcher: str
    external_id: str
    detail: dict[str, Any] = Field(default_factory=dict)


class IngestResult(StrictModel):
    run_id: str
    artifact: KnowledgeArtifact
    note_path: str
    outbox_ids: list[str]
    reused: bool = False


class BriefResult(StrictModel):
    run_id: str
    note_path: str
    brief: DailyBrief | DecisionBriefDraft


class HealthResponse(StrictModel):
    status: Literal["ok"] = "ok"
    version: str
    provider: str
    vault_path: str


class EvaluationExpectation(StrictModel):
    title_contains: str | None = None
    kind: ArtifactKind | None = None
    action_contains: list[str] = Field(default_factory=list)
    decision_contains: list[str] = Field(default_factory=list)
    forbidden_contains: list[str] = Field(default_factory=list)


class EvaluationCase(StrictModel):
    case_id: str
    source: SourceDocument
    expected: EvaluationExpectation


class EvaluationCaseResult(StrictModel):
    case_id: str
    passed: bool
    score: float
    failures: list[str]


class EvaluationReport(StrictModel):
    dataset: str
    provider: str
    score: float
    passed: bool
    cases: list[EvaluationCaseResult]
    generated_at: datetime = Field(default_factory=utc_now)


def _assume_utc(value: datetime | None) -> datetime | None:
    """Interpret a naive boundary timestamp as UTC and preserve aware values."""

    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
