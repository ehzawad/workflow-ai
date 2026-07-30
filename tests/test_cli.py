from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import uvicorn
from typer.testing import CliRunner

from workflow_ai import __version__
from workflow_ai.cli import _parse_datetime, app


runner = CliRunner()


def _configure_workspace(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WORKFLOW_AI_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_AI_VAULT_PATH", "vault")
    monkeypatch.setenv("WORKFLOW_AI_RUNTIME_PATH", ".workflow-ai")
    monkeypatch.setenv("WORKFLOW_AI_LLM_PROVIDER", "deterministic")


def _invoke(*args: str) -> dict[str, Any] | list[Any]:
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_cli_end_to_end(monkeypatch, tmp_path: Path) -> None:
    _configure_workspace(monkeypatch, tmp_path)
    source = tmp_path / "leadership-sync.txt"
    source.write_text(
        """TITLE: Product Launch Leadership Sync
DATE: 2026-07-30T15:00:00+00:00
PROJECT: Atlas Launch
The launch remains on track.
DECISION: Keep the August 18 launch date | Readiness checks passed | Maya Chen
ACTION: omar@example.com | 2026-08-04 | high | Obtain final legal approval
RISK: high | Legal review may delay onboarding | Escalate unresolved clauses
QUESTION: Are support staffing levels sufficient?
""",
        encoding="utf-8",
    )

    version = runner.invoke(app, ["--version"])
    assert version.exit_code == 0
    assert version.stdout.strip() == __version__

    initialized = _invoke("init")
    assert initialized["provider"] == "deterministic"
    assert (tmp_path / "vault" / "Home.md").exists()

    ingested = _invoke(
        "ingest",
        str(source),
        "--kind",
        "meeting",
        "--project",
        "Atlas Launch",
        "--stakeholder",
        "chief-of-staff@example.com",
    )
    assert ingested["artifact"]["title"] == "Product Launch Leadership Sync"
    assert len(ingested["outbox_ids"]) == 3

    search = _invoke("search", "legal approval onboarding", "--limit", "3")
    assert search

    reindexed = _invoke("reindex")
    assert reindexed["indexed_notes"] >= 1

    daily = _invoke("brief", "daily", "--date", "2026-07-31")
    assert daily["brief"]["brief_date"] == "2026-07-31"

    decision = _invoke(
        "brief",
        "decision",
        "Should Atlas keep the August 18 launch date?",
        "--evidence-limit",
        "4",
    )
    assert decision["brief"]["options"]
    assert decision["brief"]["evidence"]

    proposed = _invoke("outbox", "list", "--status", "proposed")
    outbox_id = proposed[0]["id"]
    draft = proposed[0]["draft"]
    draft["subject"] = "Reviewed: " + draft["subject"]
    draft_file = tmp_path / "draft.json"
    draft_file.write_text(json.dumps(draft), encoding="utf-8")

    edited = _invoke("outbox", "edit", outbox_id, str(draft_file), "--actor", "ehza")
    assert edited["draft"]["subject"].startswith("Reviewed:")

    approved = _invoke("outbox", "approve", outbox_id, "--actor", "ehza")
    assert approved["status"] == "approved"

    dispatched = _invoke(
        "outbox", "dispatch", outbox_id, "--actor", "ehza", "--mode", "filesystem"
    )
    assert dispatched["status"] == "dispatched"
    assert Path(dispatched["dispatch_receipt"]["external_id"]).exists()

    events = _invoke("audit", "--run-id", ingested["run_id"], "--limit", "20")
    assert any(event["event_type"] == "intake.completed" for event in events)

    dataset = Path(__file__).parents[1] / "evals" / "golden.jsonl"
    evaluation = _invoke(
        "eval",
        "run",
        "--dataset",
        str(dataset),
        "--provider",
        "deterministic",
        "--minimum-score",
        "0.95",
    )
    assert evaluation["passed"] is True


def test_cli_reports_domain_errors(monkeypatch, tmp_path: Path) -> None:
    _configure_workspace(monkeypatch, tmp_path)
    source = tmp_path / "note.txt"
    source.write_text(
        "TITLE: Follow-up\nACTION: owner@example.com | 2026-08-04 | high | Confirm terms",
        encoding="utf-8",
    )
    _invoke("init")
    ingested = _invoke("ingest", str(source), "--kind", "meeting")

    result = runner.invoke(
        app,
        ["outbox", "dispatch", ingested["outbox_ids"][0], "--mode", "filesystem"],
    )

    assert result.exit_code == 1
    assert "must be approved" in result.output


def test_cli_serve_modes(monkeypatch, tmp_path: Path) -> None:
    _configure_workspace(monkeypatch, tmp_path)
    calls: list[tuple[object, dict[str, object]]] = []

    def fake_run(target: object, **kwargs: object) -> None:
        calls.append((target, kwargs))

    monkeypatch.setattr(uvicorn, "run", fake_run)

    normal = runner.invoke(app, ["serve", "--host", "0.0.0.0", "--port", "9000"])
    assert normal.exit_code == 0, normal.output
    assert calls[-1][1]["port"] == 9000

    reload_result = runner.invoke(app, ["serve", "--reload"])
    assert reload_result.exit_code == 0, reload_result.output
    assert calls[-1][0] == "workflow_ai.api:app"
    assert calls[-1][1]["reload"] is True


def test_cli_datetime_parser_normalizes_to_utc() -> None:
    assert _parse_datetime("2026-07-31").tzinfo is not None
    assert _parse_datetime("2026-07-31T12:30:00").tzinfo is not None
    assert _parse_datetime("2026-07-31T12:30:00Z").utcoffset().total_seconds() == 0
