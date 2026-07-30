"""Communication dispatch adapters."""

from workflow_ai.integrations.base import Dispatcher
from workflow_ai.integrations.filesystem import FilesystemDispatcher
from workflow_ai.integrations.webhook import WebhookDispatcher

__all__ = ["Dispatcher", "FilesystemDispatcher", "WebhookDispatcher"]
