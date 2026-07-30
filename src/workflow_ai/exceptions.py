"""Domain exceptions used across API, CLI, and workflow layers."""


class WorkflowAIError(Exception):
    """Base exception for expected application failures."""


class ConfigurationError(WorkflowAIError):
    """The runtime configuration is missing or internally inconsistent."""


class ProviderError(WorkflowAIError):
    """An AI provider failed or returned no schema-valid result."""


class InputRejectedError(WorkflowAIError):
    """Input violated a size, type, or safety constraint."""


class WorkflowConflictError(WorkflowAIError):
    """An equivalent workflow is already in progress."""


class NotFoundError(WorkflowAIError):
    """A requested workflow, note, or outbox item does not exist."""


class InvalidStateTransitionError(WorkflowAIError):
    """A workflow state transition is not allowed."""


class DispatchDisabledError(WorkflowAIError):
    """A live external dispatch was attempted while disabled."""


class PathSafetyError(WorkflowAIError):
    """A computed path escaped the configured workspace or vault."""
