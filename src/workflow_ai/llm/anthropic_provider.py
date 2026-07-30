"""Anthropic Messages API structured-output provider."""

from __future__ import annotations

import asyncio

from workflow_ai.exceptions import ConfigurationError, ProviderError
from workflow_ai.llm.base import LLMProvider
from workflow_ai.models import DecisionBriefDraft, KnowledgeArtifact, SearchHit, SourceDocument
from workflow_ai.prompts import DECISION_BRIEF_SYSTEM_PROMPT, KNOWLEDGE_EXTRACTION_SYSTEM_PROMPT
from workflow_ai.utils import canonical_json


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, *, api_key: str | None, model: str, max_tokens: int) -> None:
        if not api_key:
            raise ConfigurationError("ANTHROPIC_API_KEY is required for the Anthropic provider")
        try:
            from anthropic import Anthropic
        except ImportError as error:  # pragma: no cover - optional dependency
            raise ConfigurationError(
                "Install the Anthropic provider with `uv sync --extra anthropic`"
            ) from error
        self._client = Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    async def normalize(self, source: SourceDocument) -> KnowledgeArtifact:
        def request() -> KnowledgeArtifact:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=self._max_tokens,
                system=KNOWLEDGE_EXTRACTION_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": "Normalize this source packet:\n" + source.model_dump_json(),
                    }
                ],
                output_format=KnowledgeArtifact,
            )
            if response.parsed_output is None:
                raise ProviderError("Anthropic returned no parsed knowledge artifact")
            return response.parsed_output

        artifact = await asyncio.to_thread(request)
        return artifact.model_copy(
            update={"kind": source.kind, "sensitivity": source.sensitivity}, deep=True
        )

    async def decision_brief(
        self,
        *,
        question: str,
        evidence: list[SearchHit],
    ) -> DecisionBriefDraft:
        packet = {
            "question": question,
            "evidence": [hit.model_dump(mode="json") for hit in evidence],
        }

        def request() -> DecisionBriefDraft:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=self._max_tokens,
                system=DECISION_BRIEF_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": canonical_json(packet)}],
                output_format=DecisionBriefDraft,
            )
            if response.parsed_output is None:
                raise ProviderError("Anthropic returned no parsed decision brief")
            return response.parsed_output

        return await asyncio.to_thread(request)
