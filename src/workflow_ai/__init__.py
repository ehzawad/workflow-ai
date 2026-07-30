"""Workflow AI: an executive knowledge and coordination operating system."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("workflow-ai")
except PackageNotFoundError:  # pragma: no cover - source checkout without installation
    __version__ = "0.1.0"

__all__ = ["__version__"]
