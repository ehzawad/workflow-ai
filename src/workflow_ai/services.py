"""Composition root shared by the CLI and FastAPI application."""

from __future__ import annotations

from dataclasses import dataclass

from workflow_ai.config import Settings
from workflow_ai.llm.base import LLMProvider
from workflow_ai.llm.factory import create_provider
from workflow_ai.store import WorkflowStore
from workflow_ai.vault.index import VaultIndex
from workflow_ai.vault.taxonomy import initialize_vault
from workflow_ai.vault.writer import VaultWriter
from workflow_ai.workflows.briefs import BriefWorkflow
from workflow_ai.workflows.communications import CommunicationPlanner
from workflow_ai.workflows.intake import IntakeWorkflow
from workflow_ai.workflows.outbox import OutboxWorkflow


@dataclass(slots=True)
class Services:
    settings: Settings
    provider: LLMProvider
    store: WorkflowStore
    writer: VaultWriter
    index: VaultIndex
    intake: IntakeWorkflow
    briefs: BriefWorkflow
    outbox: OutboxWorkflow

    @classmethod
    def build(cls, settings: Settings | None = None) -> Services:
        resolved = settings or Settings()
        resolved.ensure_directories()
        initialize_vault(resolved.vault_path)

        store = WorkflowStore(resolved.database_path)
        store.initialize()
        writer = VaultWriter(resolved.vault_path)
        index = VaultIndex(database_path=resolved.index_path, vault_root=resolved.vault_path)
        index.initialize()
        provider = create_provider(resolved)

        return cls(
            settings=resolved,
            provider=provider,
            store=store,
            writer=writer,
            index=index,
            intake=IntakeWorkflow(
                provider=provider,
                store=store,
                writer=writer,
                index=index,
                planner=CommunicationPlanner(),
                max_source_chars=resolved.max_source_chars,
            ),
            briefs=BriefWorkflow(
                provider=provider,
                store=store,
                writer=writer,
                index=index,
            ),
            outbox=OutboxWorkflow(settings=resolved, store=store),
        )
