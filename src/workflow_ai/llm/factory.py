"""Construct the configured provider without importing optional SDKs eagerly."""

from workflow_ai.config import Settings
from workflow_ai.llm.base import LLMProvider
from workflow_ai.llm.deterministic import DeterministicProvider


def create_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "deterministic":
        return DeterministicProvider()
    if settings.llm_provider == "openai":
        from workflow_ai.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(
            api_key=(
                settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
            ),
            model=settings.openai_model,
        )
    if settings.llm_provider == "anthropic":
        from workflow_ai.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=(
                settings.anthropic_api_key.get_secret_value()
                if settings.anthropic_api_key
                else None
            ),
            model=settings.anthropic_model,
            max_tokens=settings.llm_max_output_tokens,
        )
    raise AssertionError(f"Unhandled provider: {settings.llm_provider}")
