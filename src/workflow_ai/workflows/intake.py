"""Idempotent source-to-vault intake workflow."""

from __future__ import annotations

from workflow_ai.exceptions import InputRejectedError
from workflow_ai.llm.base import LLMProvider
from workflow_ai.models import IngestResult, KnowledgeArtifact, SourceDocument
from workflow_ai.store import WorkflowStore
from workflow_ai.utils import canonical_json, deduplicate, sha256_text
from workflow_ai.vault.index import VaultIndex
from workflow_ai.vault.writer import VaultWriter
from workflow_ai.workflows.communications import CommunicationPlanner


class IntakeWorkflow:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        store: WorkflowStore,
        writer: VaultWriter,
        index: VaultIndex,
        planner: CommunicationPlanner,
        max_source_chars: int,
    ) -> None:
        self.provider = provider
        self.store = store
        self.writer = writer
        self.index = index
        self.planner = planner
        self.max_source_chars = max_source_chars

    async def ingest(
        self,
        source: SourceDocument,
        *,
        propose_communications: bool = True,
        idempotency_key: str | None = None,
    ) -> IngestResult:
        if len(source.content) > self.max_source_chars:
            raise InputRejectedError(
                f"Source exceeds configured limit of {self.max_source_chars} characters"
            )

        source_payload = source.model_dump(mode="json")
        input_hash = sha256_text(canonical_json(source_payload))
        key = f"intake:{idempotency_key or input_hash}"
        row, reused = self.store.begin_run(
            workflow_type="intake",
            idempotency_key=key,
            input_hash=input_hash,
        )
        run_id = str(row["id"])
        if reused:
            result = IngestResult.model_validate(self.store.decode_run_output(row))
            return result.model_copy(update={"reused": True})

        self.store.add_audit_event(
            run_id=run_id,
            event_type="intake.started",
            payload={
                "source_name": source.source_name,
                "kind": source.kind.value,
                "source_hash": sha256_text(source.content),
                "character_count": len(source.content),
                "provider": self.provider.name,
            },
        )

        try:
            artifact = await self.provider.normalize(source)
            artifact = _merge_operator_context(artifact, source)
            note_path = self.writer.write_artifact(
                artifact=artifact,
                source=source,
                run_id=run_id,
            )
            self.index.upsert(note_path)

            outbox_ids: list[str] = []
            if propose_communications:
                for draft in self.planner.propose(artifact=artifact, source=source):
                    record = self.store.create_outbox(run_id=run_id, draft=draft)
                    outbox_ids.append(record.id)

            result = IngestResult(
                run_id=run_id,
                artifact=artifact,
                note_path=self.writer.relative(note_path),
                outbox_ids=outbox_ids,
            )
            self.store.complete_run(
                run_id,
                output=result.model_dump(mode="json"),
                note_path=result.note_path,
            )
            self.store.add_audit_event(
                run_id=run_id,
                event_type="intake.completed",
                payload={
                    "note_path": result.note_path,
                    "outbox_count": len(outbox_ids),
                    "decision_count": len(artifact.decisions),
                    "action_count": len(artifact.action_items),
                    "risk_count": len(artifact.risks),
                },
            )
            return result
        except Exception as error:
            self.store.fail_run(run_id, error=f"{type(error).__name__}: {error}")
            self.store.add_audit_event(
                run_id=run_id,
                event_type="intake.failed",
                payload={"error_type": type(error).__name__},
            )
            raise


def _merge_operator_context(
    artifact: KnowledgeArtifact,
    source: SourceDocument,
) -> KnowledgeArtifact:
    return artifact.model_copy(
        update={
            "kind": source.kind,
            "sensitivity": source.sensitivity,
            "participants": deduplicate([*source.participants, *artifact.participants]),
            "projects": deduplicate([*source.projects, *artifact.projects]),
            "occurred_at": source.occurred_at or artifact.occurred_at,
        },
        deep=True,
    )
