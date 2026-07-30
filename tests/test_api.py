from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import SecretStr

from workflow_ai.api import create_app
from workflow_ai.config import Settings
from workflow_ai.models import SourceDocument


def test_api_intake_search_and_health(settings: Settings, meeting_source: SourceDocument) -> None:
    with TestClient(create_app(settings)) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["provider"] == "deterministic"

        response = client.post(
            "/v1/intake",
            json={"source": meeting_source.model_dump(mode="json")},
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["artifact"]["title"] == "Product Launch Leadership Sync"

        search = client.get("/v1/search", params={"q": "legal approval"})
        assert search.status_code == 200
        assert search.json()


def test_optional_api_key_authentication(settings: Settings) -> None:
    protected = settings.model_copy(update={"api_key": SecretStr("test-secret")})
    with TestClient(create_app(protected)) as client:
        unauthorized = client.get("/v1/search", params={"q": "anything"})
        assert unauthorized.status_code == 401

        authorized = client.get(
            "/v1/search",
            params={"q": "anything"},
            headers={"X-API-Key": "test-secret"},
        )
        assert authorized.status_code == 200
