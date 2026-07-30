"""Typer CLI for local-first executive workflow operations."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any, TypeVar

import typer

from workflow_ai import __version__
from workflow_ai.api import create_app
from workflow_ai.config import Settings
from workflow_ai.evals import run_evaluations
from workflow_ai.exceptions import WorkflowAIError
from workflow_ai.llm.factory import create_provider
from workflow_ai.models import (
    ArtifactKind,
    BriefResult,
    CommunicationDraft,
    IngestResult,
    OutboxRecord,
    OutboxStatus,
    Sensitivity,
    SourceDocument,
)
from workflow_ai.services import Services
from workflow_ai.vault.taxonomy import initialize_vault

T = TypeVar("T")


app = typer.Typer(
    name="workflow-ai",
    help="Executive knowledge-vault and approval-gated coordination system.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
brief_app = typer.Typer(help="Generate executive briefs.", no_args_is_help=True)
outbox_app = typer.Typer(
    help="Review, edit, approve, and dispatch communications.",
    no_args_is_help=True,
)
eval_app = typer.Typer(help="Run golden-dataset extraction evaluations.", no_args_is_help=True)

app.add_typer(brief_app, name="brief")
app.add_typer(outbox_app, name="outbox")
app.add_typer(eval_app, name="eval")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """Workflow AI command line."""


@app.command("init")
def initialize() -> None:
    """Create missing vault scaffolding, runtime tables, and search index."""

    def operation() -> dict[str, Any]:
        settings = Settings()
        settings.ensure_directories()
        created = initialize_vault(settings.vault_path)
        services = Services.build(settings)
        indexed = services.index.rebuild()
        return {
            "workspace": str(settings.workspace_root),
            "vault": str(settings.vault_path),
            "created": [str(path.relative_to(settings.vault_path)) for path in created],
            "indexed_notes": indexed,
            "provider": services.provider.name,
        }

    _sync_command(operation)


@app.command()
def ingest(
    path: Annotated[Path, typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True)],
    kind: Annotated[ArtifactKind, typer.Option()] = ArtifactKind.NOTE,
    project: Annotated[list[str] | None, typer.Option("--project", "-p")] = None,
    participant: Annotated[list[str] | None, typer.Option("--participant")] = None,
    occurred_at: Annotated[str | None, typer.Option(help="ISO-8601 date or timestamp.")] = None,
    sensitivity: Annotated[Sensitivity, typer.Option()] = Sensitivity.INTERNAL,
    stakeholder: Annotated[list[str] | None, typer.Option("--stakeholder")] = None,
    no_communications: Annotated[
        bool, typer.Option(help="Do not create communication proposals.")
    ] = False,
    idempotency_key: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Normalize a note, transcript, email, or project update into the vault."""

    async def operation() -> IngestResult:
        services = Services.build()
        source = SourceDocument(
            source_name=path.name,
            kind=kind,
            content=path.read_text(encoding="utf-8"),
            occurred_at=_parse_datetime(occurred_at) if occurred_at else None,
            participants=participant or [],
            projects=project or [],
            sensitivity=sensitivity,
            metadata={"stakeholders": ",".join(stakeholder or [])},
        )
        return await services.intake.ingest(
            source,
            propose_communications=not no_communications,
            idempotency_key=idempotency_key,
        )

    _async_command(operation())


@app.command()
def search(
    query: Annotated[str, typer.Argument(min=1)],
    limit: Annotated[int, typer.Option(min=1, max=100)] = 10,
) -> None:
    """Search the local vault using SQLite full-text retrieval."""

    _sync_command(lambda: Services.build().index.search(query, limit=limit))


@app.command()
def reindex() -> None:
    """Rebuild the full-text search index from Markdown."""

    _sync_command(lambda: {"indexed_notes": Services.build().index.rebuild()})


@brief_app.command("daily")
def daily_brief(
    brief_date: Annotated[str | None, typer.Option("--date", help="YYYY-MM-DD")] = None,
) -> None:
    """Generate an action-, decision-, and risk-oriented daily brief."""

    target = date.fromisoformat(brief_date) if brief_date else None

    async def operation() -> BriefResult:
        return await Services.build().briefs.daily(brief_date=target)

    _async_command(operation())


@brief_app.command("decision")
def decision_brief(
    question: Annotated[str, typer.Argument(min=3)],
    evidence_limit: Annotated[int, typer.Option(min=1, max=30)] = 8,
) -> None:
    """Retrieve vault evidence and produce a typed decision brief."""

    async def operation() -> BriefResult:
        return await Services.build().briefs.decision(
            question=question,
            evidence_limit=evidence_limit,
        )

    _async_command(operation())


@outbox_app.command("list")
def list_outbox(
    status_filter: Annotated[OutboxStatus | None, typer.Option("--status")] = None,
    limit: Annotated[int, typer.Option(min=1, max=1_000)] = 100,
) -> None:
    """List communication proposals and their approval state."""

    _sync_command(lambda: Services.build().outbox.list(status=status_filter, limit=limit))


@outbox_app.command("edit")
def edit_outbox(
    outbox_id: Annotated[str, typer.Argument()],
    draft_file: Annotated[Path, typer.Argument(exists=True, file_okay=True, dir_okay=False)],
    actor: Annotated[str, typer.Option()] = "operator",
) -> None:
    """Replace a draft from JSON; any previous approval is revoked."""

    def operation() -> OutboxRecord:
        draft = CommunicationDraft.model_validate_json(draft_file.read_text(encoding="utf-8"))
        return Services.build().outbox.edit(outbox_id, draft=draft, actor=actor)

    _sync_command(operation)


@outbox_app.command("approve")
def approve_outbox(
    outbox_id: Annotated[str, typer.Argument()],
    actor: Annotated[str, typer.Option()] = "operator",
) -> None:
    """Record explicit human approval for a proposed communication."""

    _sync_command(lambda: Services.build().outbox.approve(outbox_id, actor=actor))


@outbox_app.command("dispatch")
def dispatch_outbox(
    outbox_id: Annotated[str, typer.Argument()],
    actor: Annotated[str, typer.Option()] = "operator",
    mode: Annotated[str, typer.Option(help="filesystem or webhook")] = "filesystem",
) -> None:
    """Dispatch an approved item; filesystem export is the safe default."""

    async def operation() -> OutboxRecord:
        return await Services.build().outbox.dispatch(outbox_id, actor=actor, mode=mode)

    _async_command(operation())


@app.command()
def audit(
    run_id: Annotated[str | None, typer.Option()] = None,
    limit: Annotated[int, typer.Option(min=1, max=1_000)] = 100,
) -> None:
    """Inspect metadata-only workflow audit events."""

    _sync_command(lambda: Services.build().store.list_audit_events(run_id=run_id, limit=limit))


@eval_app.command("run")
def evaluate(
    dataset: Annotated[Path, typer.Option(exists=True, file_okay=True, dir_okay=False)] = Path(
        "evals/golden.jsonl"
    ),
    provider: Annotated[str, typer.Option(help="deterministic, openai, or anthropic")] = "deterministic",
    minimum_score: Annotated[float, typer.Option(min=0.0, max=1.0)] = 0.95,
) -> None:
    """Run schema and semantic regression cases."""

    async def operation() -> None:
        settings = Settings().model_copy(update={"llm_provider": provider})
        selected_provider = create_provider(settings)
        report = await run_evaluations(
            dataset_path=dataset,
            provider=selected_provider,
            minimum_score=minimum_score,
        )
        _print_json(report)
        if not report.passed:
            raise typer.Exit(code=1)
        return None

    _async_command(operation(), print_result=False)


@app.command()
def serve(
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8080,
    reload: Annotated[bool, typer.Option()] = False,
) -> None:
    """Run the FastAPI service."""

    import uvicorn

    if reload:
        uvicorn.run("workflow_ai.api:app", host=host, port=port, reload=True)
    else:
        uvicorn.run(create_app(), host=host, port=port)


def _sync_command(operation: Callable[[], T], *, print_result: bool = True) -> T:
    try:
        result = operation()
        if print_result and result is not None:
            _print_json(result)
        return result
    except WorkflowAIError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error


def _async_command(awaitable: Awaitable[T], *, print_result: bool = True) -> T:
    try:
        result = asyncio.run(awaitable)
        if print_result and result is not None:
            _print_json(result)
        return result
    except WorkflowAIError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error


def _print_json(value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    elif isinstance(value, list):
        value = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value]
    typer.echo(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _parse_datetime(value: str) -> datetime:
    cleaned = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        parsed = datetime.combine(date.fromisoformat(cleaned), datetime.min.time(), tzinfo=UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


if __name__ == "__main__":  # pragma: no cover
    app()
