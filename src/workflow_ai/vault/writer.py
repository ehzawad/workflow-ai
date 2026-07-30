"""Render structured workflow objects into durable Obsidian Markdown."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from workflow_ai.models import (
    ActionItem,
    ArtifactKind,
    DailyBrief,
    DecisionBriefDraft,
    KnowledgeArtifact,
    SourceDocument,
)
from workflow_ai.utils import atomic_write_text, safe_child, sha256_text, slugify, utc_now
from workflow_ai.vault.frontmatter import dump_markdown, load_markdown


class VaultWriter:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def write_artifact(
        self,
        *,
        artifact: KnowledgeArtifact,
        source: SourceDocument,
        run_id: str,
    ) -> Path:
        source_hash = sha256_text(source.content)
        relative = self._artifact_relative_path(artifact, source_hash=source_hash)
        path = safe_child(self.root, relative)
        path = self._resolve_collision(path, source_hash=source_hash)

        metadata = {
            "title": artifact.title,
            "type": artifact.kind.value,
            "date": _iso_date(artifact.occurred_at),
            "status": "active",
            "sensitivity": artifact.sensitivity.value,
            "projects": artifact.projects,
            "topics": artifact.topics,
            "participants": artifact.participants,
            "tags": _tags(artifact),
            "workflow_ai": {
                "schema_version": 1,
                "run_id": run_id,
                "source_name": source.source_name,
                "source_hash": source_hash,
                "ingested_at": utc_now().isoformat(),
                "artifact": artifact.model_dump(mode="json"),
            },
        }
        body = _render_artifact_body(artifact, source)
        atomic_write_text(path, dump_markdown(metadata, body))
        for project in artifact.projects:
            self._ensure_project_index(project)
        return path

    def write_daily_brief(self, *, brief: DailyBrief, run_id: str) -> Path:
        relative = Path("60_Briefs") / str(brief.brief_date.year) / (
            f"{brief.brief_date.isoformat()}-daily-brief.md"
        )
        path = safe_child(self.root, relative)
        metadata = {
            "title": brief.title,
            "type": "daily_brief",
            "date": brief.brief_date.isoformat(),
            "status": "active",
            "tags": ["workflow-ai", "brief", "daily"],
            "workflow_ai": {
                "schema_version": 1,
                "run_id": run_id,
                "brief": brief.model_dump(mode="json"),
            },
        }
        atomic_write_text(path, dump_markdown(metadata, _render_daily_brief(brief)))
        return path

    def write_decision_brief(
        self,
        *,
        brief: DecisionBriefDraft,
        run_id: str,
        evidence_paths: list[str],
    ) -> Path:
        today = utc_now().date()
        digest = sha256_text(brief.question)[:8]
        relative = (
            Path("60_Briefs")
            / str(today.year)
            / f"{today.isoformat()}-decision-{slugify(brief.question, max_length=55)}-{digest}.md"
        )
        path = safe_child(self.root, relative)
        metadata = {
            "title": f"Decision brief: {brief.question}",
            "type": "decision_brief",
            "date": today.isoformat(),
            "status": "active",
            "tags": ["workflow-ai", "brief", "decision"],
            "evidence_paths": evidence_paths,
            "workflow_ai": {
                "schema_version": 1,
                "run_id": run_id,
                "decision_brief": brief.model_dump(mode="json"),
            },
        }
        atomic_write_text(path, dump_markdown(metadata, _render_decision_brief(brief)))
        return path

    def iter_artifacts(self) -> list[tuple[Path, KnowledgeArtifact]]:
        artifacts: list[tuple[Path, KnowledgeArtifact]] = []
        for path in sorted(self.root.rglob("*.md")):
            try:
                metadata, _ = load_markdown(path.read_text(encoding="utf-8"))
                workflow_data = metadata.get("workflow_ai", {})
                if not isinstance(workflow_data, dict):
                    continue
                raw_artifact = workflow_data.get("artifact")
                if isinstance(raw_artifact, dict):
                    artifacts.append((path, KnowledgeArtifact.model_validate(raw_artifact)))
            except (OSError, UnicodeError, ValueError):
                continue
        return artifacts

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def _artifact_relative_path(
        self, artifact: KnowledgeArtifact, *, source_hash: str
    ) -> Path:
        when = artifact.occurred_at or datetime.now(UTC)
        day = when.date().isoformat()
        name = f"{day}-{slugify(artifact.title)}.md"

        if artifact.kind in {ArtifactKind.MEETING, ArtifactKind.TRANSCRIPT}:
            return Path("20_Meetings") / str(when.year) / name
        if artifact.kind is ArtifactKind.PROJECT_UPDATE and artifact.projects:
            return Path("30_Projects") / slugify(artifact.projects[0]) / name
        if artifact.kind is ArtifactKind.DECISION:
            return Path("40_Decisions") / str(when.year) / name
        if artifact.kind is ArtifactKind.BRIEF:
            return Path("60_Briefs") / str(when.year) / name
        return Path("00_Inbox") / f"{day}-{slugify(artifact.title)}-{source_hash[:8]}.md"

    def _resolve_collision(self, path: Path, *, source_hash: str) -> Path:
        if not path.exists():
            return path
        try:
            metadata, _ = load_markdown(path.read_text(encoding="utf-8"))
            workflow_data = metadata.get("workflow_ai", {})
            if isinstance(workflow_data, dict) and workflow_data.get("source_hash") == source_hash:
                return path
        except (OSError, UnicodeError, ValueError):
            pass
        return path.with_name(f"{path.stem}-{source_hash[:8]}{path.suffix}")

    def _ensure_project_index(self, project: str) -> None:
        directory = safe_child(self.root, Path("30_Projects") / slugify(project))
        directory.mkdir(parents=True, exist_ok=True)
        index = directory / "README.md"
        if index.exists():
            return
        metadata = {
            "title": project,
            "type": "project_index",
            "status": "active",
            "tags": ["project", "moc"],
        }
        body = (
            f"# {project}\n\n"
            "## Outcome\n\nDefine the measurable outcome.\n\n"
            "## Notes\n\n"
            "```query\npath:\"30_Projects/"
            f"{slugify(project)}\"\n"
            "```\n"
        )
        atomic_write_text(index, dump_markdown(metadata, body))


def _iso_date(value: datetime | None) -> str | None:
    return value.date().isoformat() if value else None


def _tags(artifact: KnowledgeArtifact) -> list[str]:
    values = ["workflow-ai", artifact.kind.value, *artifact.topics]
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = slugify(value, max_length=50)
        if tag and tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def _render_artifact_body(artifact: KnowledgeArtifact, source: SourceDocument) -> str:
    lines = [f"# {artifact.title}", "", "## Executive summary", "", artifact.summary]
    if artifact.projects:
        project_links = ", ".join(
            f"[[30_Projects/{slugify(project)}/README|{project}]]" for project in artifact.projects
        )
        lines.extend(["", f"**Projects:** {project_links}"])
    if artifact.participants:
        lines.extend(["", f"**Participants:** {', '.join(artifact.participants)}"])

    lines.extend(["", "## Decisions", ""])
    if artifact.decisions:
        for decision in artifact.decisions:
            owner = f" — owner: {decision.owner}" if decision.owner else ""
            lines.append(f"- **{decision.statement}**{owner}")
            if decision.rationale:
                lines.append(f"  - Rationale: {decision.rationale}")
            if decision.evidence:
                lines.append(f"  - Evidence: {decision.evidence}")
    else:
        lines.append("_No explicit decisions extracted._")

    lines.extend(["", "## Action items", ""])
    if artifact.action_items:
        lines.extend(_render_action(action) for action in artifact.action_items)
    else:
        lines.append("_No explicit action items extracted._")

    lines.extend(["", "## Risks", ""])
    if artifact.risks:
        for risk in artifact.risks:
            lines.append(f"- **{risk.severity.value.upper()}** — {risk.description}")
            if risk.mitigation:
                lines.append(f"  - Mitigation: {risk.mitigation}")
            if risk.owner:
                lines.append(f"  - Owner: {risk.owner}")
    else:
        lines.append("_No explicit risks extracted._")

    lines.extend(["", "## Open questions", ""])
    lines.extend(f"- {question}" for question in artifact.open_questions)
    if not artifact.open_questions:
        lines.append("_No open questions extracted._")

    if artifact.suggested_links:
        lines.extend(["", "## Suggested links", ""])
        lines.extend(f"- [[{link}]]" for link in artifact.suggested_links)

    lines.extend(
        [
            "",
            "## Source provenance",
            "",
            f"- Source: `{source.source_name}`",
            f"- Imported kind: `{source.kind.value}`",
            f"- Sensitivity: `{source.sensitivity.value}`",
            "",
            "<details>",
            "<summary>Original source text</summary>",
            "",
            *_indent_source(source.content),
            "",
            "</details>",
        ]
    )
    return "\n".join(lines)


def _render_action(action: ActionItem) -> str:
    checked = "x" if action.status.value == "done" else " "
    attributes: list[str] = []
    if action.owner:
        attributes.append(f"owner: {action.owner}")
    if action.due_date:
        attributes.append(f"due: {action.due_date.isoformat()}")
    attributes.append(f"priority: {action.priority.value}")
    suffix = f" ({'; '.join(attributes)})" if attributes else ""
    return f"- [{checked}] {action.description}{suffix}"


def _render_daily_brief(brief: DailyBrief) -> str:
    lines = [f"# {brief.title}", "", brief.executive_summary, "", "## Priorities", ""]
    lines.extend(f"{index}. {item}" for index, item in enumerate(brief.priorities, start=1))
    if not brief.priorities:
        lines.append("_No priorities surfaced._")
    lines.extend(["", "## Open action items", ""])
    lines.extend(_render_action(item) for item in brief.action_items)
    if not brief.action_items:
        lines.append("_No open action items._")
    lines.extend(["", "## Recent decisions", ""])
    lines.extend(f"- {item}" for item in brief.decisions)
    if not brief.decisions:
        lines.append("_No decisions surfaced._")
    lines.extend(["", "## Risks", ""])
    lines.extend(f"- **{risk.severity.value.upper()}** — {risk.description}" for risk in brief.risks)
    if not brief.risks:
        lines.append("_No risks surfaced._")
    lines.extend(["", "## Open questions", ""])
    lines.extend(f"- {item}" for item in brief.open_questions)
    if not brief.open_questions:
        lines.append("_No open questions surfaced._")
    lines.extend(["", "## Source notes", ""])
    lines.extend(f"- [[{_strip_md(path)}]]" for path in brief.source_notes)
    return "\n".join(lines)


def _render_decision_brief(brief: DecisionBriefDraft) -> str:
    lines = [
        f"# Decision brief: {brief.question}",
        "",
        "## Executive summary",
        "",
        brief.executive_summary,
        "",
        "## Recommendation",
        "",
        f"**Confidence: {brief.confidence.value}.** {brief.recommendation}",
        "",
        "## Options",
        "",
    ]
    for option in brief.options:
        lines.extend(
            [
                f"### {option.name}",
                "",
                option.description,
                "",
                "**Benefits**",
                *[f"- {item}" for item in option.benefits],
                "",
                "**Drawbacks**",
                *[f"- {item}" for item in option.drawbacks],
                "",
                "**Evidence references**",
                *[f"- [[{_strip_md(item)}]]" for item in option.evidence_refs],
                "",
            ]
        )
    lines.extend(["## Evidence", "", *[f"- {item}" for item in brief.evidence]])
    lines.extend(["", "## Uncertainties", "", *[f"- {item}" for item in brief.uncertainties]])
    lines.extend(["", "## Next steps", "", *[f"- [ ] {item}" for item in brief.next_steps]])
    return "\n".join(lines)


def _indent_source(value: str) -> list[str]:
    sanitized = re.sub(r"\x00", "", value)
    return [f"    {line}" for line in sanitized.splitlines()]


def _strip_md(path: str) -> str:
    return path[:-3] if path.endswith(".md") else path
