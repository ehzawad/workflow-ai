"""Environment-backed configuration with explicit path and credential handling."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from workflow_ai.exceptions import ConfigurationError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WORKFLOW_AI_",
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    workspace_root: Path = Path(".")
    vault_path: Path = Path("vault")
    runtime_path: Path = Path(".workflow-ai")

    llm_provider: Literal["deterministic", "openai", "anthropic"] = "deterministic"
    openai_model: str = "gpt-5.5"
    anthropic_model: str = "claude-sonnet-5"
    llm_max_output_tokens: int = Field(default=4096, ge=256, le=128_000)

    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "WORKFLOW_AI_OPENAI_API_KEY"),
    )
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "WORKFLOW_AI_ANTHROPIC_API_KEY"),
    )

    live_dispatch_enabled: bool = False
    webhook_url: str | None = None
    max_source_chars: int = Field(default=200_000, ge=1_000, le=5_000_000)
    api_key: SecretStr | None = None

    @model_validator(mode="after")
    def _resolve_paths(self) -> Settings:
        root = self.workspace_root.expanduser().resolve()
        vault = self.vault_path.expanduser()
        runtime = self.runtime_path.expanduser()
        self.workspace_root = root
        self.vault_path = vault.resolve() if vault.is_absolute() else (root / vault).resolve()
        self.runtime_path = runtime.resolve() if runtime.is_absolute() else (root / runtime).resolve()

        for label, path in (("vault", self.vault_path), ("runtime", self.runtime_path)):
            if not path.is_relative_to(root):
                raise ConfigurationError(f"Configured {label} path must be inside workspace root")
        return self

    @property
    def database_path(self) -> Path:
        return self.runtime_path / "workflow.sqlite"

    @property
    def index_path(self) -> Path:
        return self.runtime_path / "vault-index.sqlite"

    @property
    def dispatch_path(self) -> Path:
        return self.runtime_path / "dispatch"

    def ensure_directories(self) -> None:
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.vault_path.mkdir(parents=True, exist_ok=True)
        self.runtime_path.mkdir(parents=True, exist_ok=True)
        self.dispatch_path.mkdir(parents=True, exist_ok=True)
