"""Obsidian-compatible vault storage and retrieval."""

from workflow_ai.vault.index import VaultIndex
from workflow_ai.vault.taxonomy import initialize_vault
from workflow_ai.vault.writer import VaultWriter

__all__ = ["VaultIndex", "VaultWriter", "initialize_vault"]
