from __future__ import annotations

import asyncio
from pathlib import Path

from workflow_ai.evals import run_evaluations
from workflow_ai.llm.deterministic import DeterministicProvider


def test_golden_dataset_passes() -> None:
    dataset = Path(__file__).parents[1] / "evals" / "golden.jsonl"
    report = asyncio.run(
        run_evaluations(
            dataset_path=dataset,
            provider=DeterministicProvider(),
            minimum_score=0.95,
        )
    )

    assert report.passed
    assert report.score == 1.0
