"""AI-provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from workflow_ai.models import DecisionBriefDraft, KnowledgeArtifact, SearchHit, SourceDocument


class LLMProvider(ABC):
    """Provider-neutral structured extraction and synthesis contract."""

    name: str

    @abstractmethod
    async def normalize(self, source: SourceDocument) -> KnowledgeArtifact:
        """Normalize unstructured source material into a knowledge artifact."""

    @abstractmethod
    async def decision_brief(
        self,
        *,
        question: str,
        evidence: list[SearchHit],
    ) -> DecisionBriefDraft:
        """Synthesize a decision brief from retrieved vault evidence."""
