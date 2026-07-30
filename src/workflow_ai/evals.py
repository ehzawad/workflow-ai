"""Small golden-dataset harness for deterministic extraction regressions."""

from __future__ import annotations

import json
from pathlib import Path

from workflow_ai.llm.base import LLMProvider
from workflow_ai.models import (
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationReport,
)


async def run_evaluations(
    *,
    dataset_path: Path,
    provider: LLMProvider,
    minimum_score: float = 0.95,
) -> EvaluationReport:
    cases = load_cases(dataset_path)
    results: list[EvaluationCaseResult] = []
    for case in cases:
        failures: list[str] = []
        artifact = await provider.normalize(case.source)
        expected = case.expected

        if expected.title_contains and expected.title_contains.casefold() not in artifact.title.casefold():
            failures.append(f"title does not contain {expected.title_contains!r}")
        if expected.kind and artifact.kind is not expected.kind:
            failures.append(f"kind is {artifact.kind.value}, expected {expected.kind.value}")

        actions = "\n".join(item.description for item in artifact.action_items).casefold()
        for value in expected.action_contains:
            if value.casefold() not in actions:
                failures.append(f"missing action substring {value!r}")

        decisions = "\n".join(item.statement for item in artifact.decisions).casefold()
        for value in expected.decision_contains:
            if value.casefold() not in decisions:
                failures.append(f"missing decision substring {value!r}")

        actionable = "\n".join(
            [
                *(item.description for item in artifact.action_items),
                *(item.statement for item in artifact.decisions),
                *artifact.suggested_links,
            ]
        ).casefold()
        for value in expected.forbidden_contains:
            if value.casefold() in actionable:
                failures.append(f"forbidden actionable substring surfaced {value!r}")

        check_count = 2 + len(expected.action_contains) + len(expected.decision_contains)
        check_count += len(expected.forbidden_contains)
        score = max(0.0, 1.0 - len(failures) / max(check_count, 1))
        results.append(
            EvaluationCaseResult(
                case_id=case.case_id,
                passed=not failures,
                score=score,
                failures=failures,
            )
        )

    aggregate = sum(result.score for result in results) / len(results) if results else 0.0
    return EvaluationReport(
        dataset=str(dataset_path),
        provider=provider.name,
        score=aggregate,
        passed=aggregate >= minimum_score and all(result.passed for result in results),
        cases=results,
    )


def load_cases(dataset_path: Path) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    with dataset_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                cases.append(EvaluationCase.model_validate(json.loads(stripped)))
            except (json.JSONDecodeError, ValueError) as error:
                raise ValueError(f"Invalid evaluation case at line {line_number}: {error}") from error
    if not cases:
        raise ValueError(f"Evaluation dataset is empty: {dataset_path}")
    return cases
