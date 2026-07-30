from __future__ import annotations

import pytest

from workflow_ai.exceptions import WorkflowConflictError
from workflow_ai.store import WorkflowStore


def test_idempotency_key_cannot_be_reused_for_different_input(tmp_path) -> None:
    store = WorkflowStore(tmp_path / "state.sqlite")
    store.initialize()
    store.begin_run(workflow_type="test", idempotency_key="same", input_hash="one")

    with pytest.raises(WorkflowConflictError):
        store.begin_run(workflow_type="test", idempotency_key="same", input_hash="two")
