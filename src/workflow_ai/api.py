"""FastAPI surface for intake, retrieval, briefs, and approved coordination."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import Field

from workflow_ai import __version__
from workflow_ai.config import Settings
from workflow_ai.exceptions import (
    ConfigurationError,
    DispatchDisabledError,
    InputRejectedError,
    InvalidStateTransitionError,
    NotFoundError,
    ProviderError,
    WorkflowAIError,
    WorkflowConflictError,
)
from workflow_ai.models import (
    BriefResult,
    CommunicationDraft,
    HealthResponse,
    IngestResult,
    OutboxRecord,
    OutboxStatus,
    SearchHit,
    SourceDocument,
    StrictModel,
)
from workflow_ai.services import Services


class IntakeRequest(StrictModel):
    source: SourceDocument
    propose_communications: bool = True
    idempotency_key: str | None = Field(default=None, max_length=240)


class DecisionBriefRequest(StrictModel):
    question: str = Field(min_length=3, max_length=2_000)
    evidence_limit: int = Field(default=8, ge=1, le=30)


class DailyBriefRequest(StrictModel):
    brief_date: date | None = None


class ActorRequest(StrictModel):
    actor: str = Field(min_length=1, max_length=200)


class DispatchRequest(ActorRequest):
    mode: str = Field(default="filesystem", pattern="^(filesystem|webhook)$")


class EditOutboxRequest(ActorRequest):
    draft: CommunicationDraft


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = Services.build(resolved_settings)
        yield

    app = FastAPI(
        title="Workflow AI",
        version=__version__,
        summary="Executive knowledge-vault and approval-gated coordination API",
        lifespan=lifespan,
    )

    @app.exception_handler(WorkflowAIError)
    async def workflow_error_handler(_request: Request, error: WorkflowAIError) -> JSONResponse:
        status_code = _status_for_error(error)
        return JSONResponse(
            status_code=status_code,
            content={"error": type(error).__name__, "detail": str(error)},
        )

    @app.get("/healthz", response_model=HealthResponse, tags=["operations"])
    async def health(request: Request) -> HealthResponse:
        services = _services(request)
        return HealthResponse(
            version=__version__,
            provider=services.provider.name,
            vault_path=str(services.settings.vault_path),
        )

    @app.post(
        "/v1/intake",
        response_model=IngestResult,
        status_code=status.HTTP_201_CREATED,
        tags=["knowledge"],
        dependencies=[Depends(_authorize)],
    )
    async def intake(payload: IntakeRequest, request: Request) -> IngestResult:
        return await _services(request).intake.ingest(
            payload.source,
            propose_communications=payload.propose_communications,
            idempotency_key=payload.idempotency_key,
        )

    @app.get(
        "/v1/search",
        response_model=list[SearchHit],
        tags=["knowledge"],
        dependencies=[Depends(_authorize)],
    )
    async def search_vault(
        request: Request,
        q: Annotated[str, Query(min_length=1, max_length=500)],
        limit: Annotated[int, Query(ge=1, le=100)] = 10,
    ) -> list[SearchHit]:
        return _services(request).index.search(q, limit=limit)

    @app.post(
        "/v1/index/rebuild",
        tags=["knowledge"],
        dependencies=[Depends(_authorize)],
    )
    async def rebuild_index(request: Request) -> dict[str, int]:
        return {"indexed_notes": _services(request).index.rebuild()}

    @app.post(
        "/v1/briefs/daily",
        response_model=BriefResult,
        tags=["briefs"],
        dependencies=[Depends(_authorize)],
    )
    async def daily_brief(payload: DailyBriefRequest, request: Request) -> BriefResult:
        return await _services(request).briefs.daily(brief_date=payload.brief_date)

    @app.post(
        "/v1/briefs/decision",
        response_model=BriefResult,
        tags=["briefs"],
        dependencies=[Depends(_authorize)],
    )
    async def decision_brief(payload: DecisionBriefRequest, request: Request) -> BriefResult:
        return await _services(request).briefs.decision(
            question=payload.question,
            evidence_limit=payload.evidence_limit,
        )

    @app.get(
        "/v1/outbox",
        response_model=list[OutboxRecord],
        tags=["coordination"],
        dependencies=[Depends(_authorize)],
    )
    async def list_outbox(
        request: Request,
        outbox_status: Annotated[OutboxStatus | None, Query(alias="status")] = None,
        limit: Annotated[int, Query(ge=1, le=1_000)] = 100,
    ) -> list[OutboxRecord]:
        return _services(request).outbox.list(status=outbox_status, limit=limit)

    @app.put(
        "/v1/outbox/{outbox_id}",
        response_model=OutboxRecord,
        tags=["coordination"],
        dependencies=[Depends(_authorize)],
    )
    async def edit_outbox(
        outbox_id: str,
        payload: EditOutboxRequest,
        request: Request,
    ) -> OutboxRecord:
        return _services(request).outbox.edit(
            outbox_id,
            draft=payload.draft,
            actor=payload.actor,
        )

    @app.post(
        "/v1/outbox/{outbox_id}/approve",
        response_model=OutboxRecord,
        tags=["coordination"],
        dependencies=[Depends(_authorize)],
    )
    async def approve_outbox(
        outbox_id: str,
        payload: ActorRequest,
        request: Request,
    ) -> OutboxRecord:
        return _services(request).outbox.approve(outbox_id, actor=payload.actor)

    @app.post(
        "/v1/outbox/{outbox_id}/dispatch",
        response_model=OutboxRecord,
        tags=["coordination"],
        dependencies=[Depends(_authorize)],
    )
    async def dispatch_outbox(
        outbox_id: str,
        payload: DispatchRequest,
        request: Request,
    ) -> OutboxRecord:
        return await _services(request).outbox.dispatch(
            outbox_id,
            actor=payload.actor,
            mode=payload.mode,
        )

    @app.get(
        "/v1/audit",
        tags=["operations"],
        dependencies=[Depends(_authorize)],
    )
    async def audit_events(
        request: Request,
        run_id: str | None = None,
        limit: Annotated[int, Query(ge=1, le=1_000)] = 100,
    ) -> list[dict[str, Any]]:
        return _services(request).store.list_audit_events(run_id=run_id, limit=limit)

    return app


def _services(request: Request) -> Services:
    services = getattr(request.app.state, "services", None)
    if not isinstance(services, Services):
        raise HTTPException(status_code=503, detail="Application services are not initialized")
    return services


async def _authorize(
    request: Request,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    services = _services(request)
    expected = services.settings.api_key
    if expected is None:
        return
    supplied = x_api_key or ""
    if not secrets.compare_digest(supplied, expected.get_secret_value()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def _status_for_error(error: WorkflowAIError) -> int:
    if isinstance(error, NotFoundError):
        return status.HTTP_404_NOT_FOUND
    if isinstance(error, (WorkflowConflictError, InvalidStateTransitionError)):
        return status.HTTP_409_CONFLICT
    if isinstance(error, (InputRejectedError, DispatchDisabledError)):
        return status.HTTP_400_BAD_REQUEST
    if isinstance(error, (ConfigurationError, ProviderError)):
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return status.HTTP_500_INTERNAL_SERVER_ERROR


app = create_app()
