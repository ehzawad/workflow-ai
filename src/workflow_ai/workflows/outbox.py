"""Approval-gated coordination workflow."""

from __future__ import annotations

from workflow_ai.config import Settings
from workflow_ai.exceptions import DispatchDisabledError, InvalidStateTransitionError
from workflow_ai.integrations.filesystem import FilesystemDispatcher
from workflow_ai.integrations.webhook import WebhookDispatcher
from workflow_ai.models import CommunicationDraft, OutboxRecord, OutboxStatus
from workflow_ai.store import WorkflowStore


class OutboxWorkflow:
    def __init__(self, *, settings: Settings, store: WorkflowStore) -> None:
        self.settings = settings
        self.store = store

    def list(self, *, status: OutboxStatus | None = None, limit: int = 100) -> list[OutboxRecord]:
        return self.store.list_outbox(status=status, limit=limit)

    def edit(self, outbox_id: str, *, draft: CommunicationDraft, actor: str) -> OutboxRecord:
        item = self.store.replace_outbox_draft(outbox_id, draft)
        self.store.add_audit_event(
            run_id=item.run_id,
            event_type="outbox.edited",
            payload={"outbox_id": outbox_id, "actor": actor, "approval_revoked": True},
        )
        return item

    def approve(self, outbox_id: str, *, actor: str) -> OutboxRecord:
        item = self.store.approve_outbox(outbox_id, actor=actor)
        self.store.add_audit_event(
            run_id=item.run_id,
            event_type="outbox.approved",
            payload={"outbox_id": outbox_id, "actor": actor},
        )
        return item

    async def dispatch(
        self,
        outbox_id: str,
        *,
        actor: str,
        mode: str = "filesystem",
    ) -> OutboxRecord:
        item = self.store.get_outbox(outbox_id)
        if item.status is OutboxStatus.DISPATCHED:
            return item
        if item.status is not OutboxStatus.APPROVED:
            raise InvalidStateTransitionError(
                f"Outbox item must be approved before dispatch; current state is {item.status.value}"
            )

        if mode == "filesystem":
            dispatcher = FilesystemDispatcher(self.settings.dispatch_path)
        elif mode == "webhook":
            if not self.settings.live_dispatch_enabled:
                raise DispatchDisabledError(
                    "Live dispatch is disabled; set WORKFLOW_AI_LIVE_DISPATCH_ENABLED=true"
                )
            if not self.settings.webhook_url:
                raise DispatchDisabledError("WORKFLOW_AI_WEBHOOK_URL is not configured")
            dispatcher = WebhookDispatcher(self.settings.webhook_url)
        else:
            raise DispatchDisabledError(f"Unknown dispatch mode: {mode}")

        self.store.add_audit_event(
            run_id=item.run_id,
            event_type="outbox.dispatch_started",
            payload={"outbox_id": outbox_id, "actor": actor, "dispatcher": dispatcher.name},
        )
        try:
            receipt = await dispatcher.dispatch(item)
            result = self.store.mark_outbox_dispatched(outbox_id, receipt=receipt)
            self.store.add_audit_event(
                run_id=item.run_id,
                event_type="outbox.dispatched",
                payload={
                    "outbox_id": outbox_id,
                    "actor": actor,
                    "dispatcher": dispatcher.name,
                    "external_id": receipt.external_id,
                },
            )
            return result
        except Exception as error:
            self.store.mark_outbox_failed(outbox_id, error=f"{type(error).__name__}: {error}")
            self.store.add_audit_event(
                run_id=item.run_id,
                event_type="outbox.dispatch_failed",
                payload={
                    "outbox_id": outbox_id,
                    "actor": actor,
                    "dispatcher": dispatcher.name,
                    "error_type": type(error).__name__,
                },
            )
            raise
