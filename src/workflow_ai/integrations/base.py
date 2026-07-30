"""Dispatch integration interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from workflow_ai.models import DispatchReceipt, OutboxRecord


class Dispatcher(ABC):
    name: str
    live: bool

    @abstractmethod
    async def dispatch(self, item: OutboxRecord) -> DispatchReceipt:
        """Dispatch one already-approved outbox item."""
