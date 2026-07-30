"""Optional generic webhook dispatcher for stakeholder messaging automations."""

from __future__ import annotations

import httpx

from workflow_ai.integrations.base import Dispatcher
from workflow_ai.models import DispatchReceipt, OutboxRecord


class WebhookDispatcher(Dispatcher):
    name = "webhook"
    live = True

    def __init__(self, url: str, *, timeout_seconds: float = 10.0) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds

    async def dispatch(self, item: OutboxRecord) -> DispatchReceipt:
        payload = {
            "event": "workflow_ai.communication.approved",
            "outbox_id": item.id,
            "run_id": item.run_id,
            "communication": item.draft.model_dump(mode="json"),
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(self.url, json=payload)
            response.raise_for_status()
        return DispatchReceipt(
            dispatcher=self.name,
            external_id=response.headers.get("x-request-id", item.id),
            detail={"status_code": response.status_code, "network_side_effect": True},
        )
