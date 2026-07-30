from __future__ import annotations

import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest
from pydantic import SecretStr

from workflow_ai.config import Settings
from workflow_ai.exceptions import ConfigurationError, ProviderError
from workflow_ai.llm.anthropic_provider import AnthropicProvider
from workflow_ai.llm.deterministic import DeterministicProvider
from workflow_ai.llm.factory import create_provider
from workflow_ai.llm.openai_provider import OpenAIProvider
from workflow_ai.models import (
    ArtifactKind,
    Confidence,
    DecisionBriefDraft,
    KnowledgeArtifact,
    SearchHit,
    Sensitivity,
    SourceDocument,
)


def _artifact() -> KnowledgeArtifact:
    return KnowledgeArtifact(
        title="Provider result",
        kind=ArtifactKind.NOTE,
        occurred_at=None,
        summary="A structured provider result.",
        participants=[],
        projects=[],
        topics=["provider"],
        decisions=[],
        action_items=[],
        risks=[],
        open_questions=[],
        suggested_links=[],
        sensitivity=Sensitivity.PUBLIC,
    )


def _brief(question: str = "Proceed?") -> DecisionBriefDraft:
    return DecisionBriefDraft(
        question=question,
        executive_summary="Evidence was reviewed.",
        recommendation="Proceed after validation.",
        confidence=Confidence.MEDIUM,
        options=[],
        evidence=["source.md"],
        uncertainties=["Owner confirmation is pending."],
        next_steps=["Confirm with the owner."],
    )


def _source() -> SourceDocument:
    return SourceDocument(
        source_name="meeting.txt",
        kind=ArtifactKind.MEETING,
        content="TITLE: Meeting",
        sensitivity=Sensitivity.CONFIDENTIAL,
    )


def _hit() -> SearchHit:
    return SearchHit(
        path="20_Meetings/meeting.md",
        title="Meeting",
        snippet="Relevant evidence",
        score=1.0,
    )


def _install_fake_openai(monkeypatch, *, parsed: bool = True) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    class Responses:
        def parse(self, **kwargs):
            calls.append(kwargs)
            value = _artifact() if kwargs["text_format"] is KnowledgeArtifact else _brief()
            return SimpleNamespace(output_parsed=value if parsed else None)

    class Client:
        def __init__(self, *, api_key: str) -> None:
            assert api_key == "openai-key"
            self.responses = Responses()

    module = ModuleType("openai")
    module.OpenAI = Client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", module)
    return calls


def _install_fake_anthropic(monkeypatch, *, parsed: bool = True) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    class Messages:
        def parse(self, **kwargs):
            calls.append(kwargs)
            value = _artifact() if kwargs["output_format"] is KnowledgeArtifact else _brief()
            return SimpleNamespace(parsed_output=value if parsed else None)

    class Client:
        def __init__(self, *, api_key: str) -> None:
            assert api_key == "anthropic-key"
            self.messages = Messages()

    module = ModuleType("anthropic")
    module.Anthropic = Client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", module)
    return calls


def test_openai_structured_provider(monkeypatch) -> None:
    calls = _install_fake_openai(monkeypatch)
    provider = OpenAIProvider(api_key="openai-key", model="gpt-test")

    artifact = asyncio.run(provider.normalize(_source()))
    brief = asyncio.run(provider.decision_brief(question="Proceed?", evidence=[_hit()]))

    assert artifact.kind is ArtifactKind.MEETING
    assert artifact.sensitivity is Sensitivity.CONFIDENTIAL
    assert brief.recommendation == "Proceed after validation."
    assert calls[0]["model"] == "gpt-test"
    assert calls[0]["text_format"] is KnowledgeArtifact
    assert calls[1]["text_format"] is DecisionBriefDraft


def test_openai_provider_configuration_and_empty_output(monkeypatch) -> None:
    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
        OpenAIProvider(api_key=None, model="gpt-test")

    _install_fake_openai(monkeypatch, parsed=False)
    provider = OpenAIProvider(api_key="openai-key", model="gpt-test")
    with pytest.raises(ProviderError, match="knowledge artifact"):
        asyncio.run(provider.normalize(_source()))
    with pytest.raises(ProviderError, match="decision brief"):
        asyncio.run(provider.decision_brief(question="Proceed?", evidence=[]))


def test_anthropic_structured_provider(monkeypatch) -> None:
    calls = _install_fake_anthropic(monkeypatch)
    provider = AnthropicProvider(
        api_key="anthropic-key",
        model="claude-test",
        max_tokens=2_048,
    )

    artifact = asyncio.run(provider.normalize(_source()))
    brief = asyncio.run(provider.decision_brief(question="Proceed?", evidence=[_hit()]))

    assert artifact.kind is ArtifactKind.MEETING
    assert artifact.sensitivity is Sensitivity.CONFIDENTIAL
    assert brief.evidence == ["source.md"]
    assert calls[0]["model"] == "claude-test"
    assert calls[0]["max_tokens"] == 2_048
    assert calls[0]["output_format"] is KnowledgeArtifact
    assert calls[1]["output_format"] is DecisionBriefDraft


def test_anthropic_provider_configuration_and_empty_output(monkeypatch) -> None:
    with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider(api_key=None, model="claude-test", max_tokens=1_024)

    _install_fake_anthropic(monkeypatch, parsed=False)
    provider = AnthropicProvider(
        api_key="anthropic-key",
        model="claude-test",
        max_tokens=1_024,
    )
    with pytest.raises(ProviderError, match="knowledge artifact"):
        asyncio.run(provider.normalize(_source()))
    with pytest.raises(ProviderError, match="decision brief"):
        asyncio.run(provider.decision_brief(question="Proceed?", evidence=[]))


def test_provider_factory_all_branches(monkeypatch, tmp_path) -> None:
    deterministic = create_provider(
        Settings(workspace_root=tmp_path, llm_provider="deterministic")
    )
    assert isinstance(deterministic, DeterministicProvider)

    _install_fake_openai(monkeypatch)
    openai_settings = Settings(
        workspace_root=tmp_path,
        llm_provider="openai",
        openai_model="gpt-test",
    ).model_copy(update={"openai_api_key": SecretStr("openai-key")})
    openai = create_provider(openai_settings)
    assert isinstance(openai, OpenAIProvider)

    _install_fake_anthropic(monkeypatch)
    anthropic_settings = Settings(
        workspace_root=tmp_path,
        llm_provider="anthropic",
        anthropic_model="claude-test",
    ).model_copy(update={"anthropic_api_key": SecretStr("anthropic-key")})
    anthropic = create_provider(anthropic_settings)
    assert isinstance(anthropic, AnthropicProvider)
