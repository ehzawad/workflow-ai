"""OpenAI Responses API structured-output provider."""

from __future__ import annotations

import asyncio

from workflow_ai.exceptions import ConfigurationError, ProviderError
from workflow_ai.llm.base import LLMProvider
from workflow_ai.models import DecisionBriefDraft, KnowledgeArtifact, SearchHit, SourceDocument
from workflow_ai.prompts import DECISION_BRIEF_SYSTEM_PROMPT, KNOWLEDGE_EXTRACTION_SYSTEM_PROMPT
from workflow_ai.utils import canonical_json


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, *, api_key: str | None, model: str) -> None:
        if not api_key:
            raise ConfigurationError("OPENAI_API_KEY is required for the OpenAI provider")
        try:
            from openai import OpenAI
        except ImportError as error:  # pragma: no cover - optional dependency
            raise ConfigurationError(
                "Install the OpenAI provider with `uv sync --extra openai`"
            ) from error
        self._client = OpenAI(api_key=api_key)
        self._model = model

    async def normalize(self, source: SourceDocument) -> KnowledgeArtifact:
        def request() -> KnowledgeArtifact:
            response = self._client.responses.parse(
                model=self._model,
                input=[
                    {"role": "system", "content": KNOWLEDGE_EXTRACTION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": "Normalize this source packet:\n" + source.model_dump_json(),
                    },
                ],
                text_format=KnowledgeArtifact,
            )
            if response.output_parsed is None:
                raise ProviderError("OpenAI returned no parsed knowledge artifact")
            return response.output_parsed

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
            response = self._client.responses.parse(
                model=self._model,
                input=[
                    {"role": "system", "content": DECISION_BRIEF_SYSTEM_PROMPT},
                    {"role": "user", "content": canonical_json(packet)},
                ],
                text_format=DecisionBriefDraft,
            )
            if response.output_parsed is None:
                raise ProviderError("OpenAI returned no parsed decision brief")
            return response.output_parsed

        return await asyncio.to_thread(request)
