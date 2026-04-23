from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.adapters import all_adapter_classes, registered_brokers
from src.api.deps import get_event_store
from src.config import Settings, get_settings
from src.schemas import ExecutionSummary
from src.storage import EventStore

router = APIRouter(tags=["meta"])

class HealthResponse(BaseModel):
    status: str
    app_env: str
    brokers_configured: list[str]
    brokers_registered: list[str]

class BrokerInfo(BaseModel):
    name: str
    display_name: str
    auth_kind: str
    configured: bool

@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        app_env=settings.app_env,
        brokers_configured=settings.configured_brokers(),
        brokers_registered=registered_brokers(),
    )

@router.get("/brokers", response_model=list[BrokerInfo])
def list_brokers(
    settings: Settings = Depends(get_settings),
) -> list[BrokerInfo]:
    configured = set(settings.configured_brokers())
    return [
        BrokerInfo(
            name=cls.name,
            display_name=cls.display_name,
            auth_kind=cls.auth_kind,
            configured=cls.name in configured,
        )
        for cls in all_adapter_classes().values()
    ]

@router.get("/events", response_model=list[ExecutionSummary])
def list_events(
    limit: int = Query(default=50, ge=1, le=100),
    events: EventStore = Depends(get_event_store),
) -> list[ExecutionSummary]:
    """Recent execution summaries, newest first. In-memory, capped at 100."""
    return events.recent(limit=limit)
