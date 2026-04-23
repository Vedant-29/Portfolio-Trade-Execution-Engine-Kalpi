"""Portfolio HTTP routes — the core assignment endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.adapters import get_adapter
from src.adapters.errors import AuthError, BrokerError
from src.api.deps import get_auth_service, get_execution_service
from src.schemas import ExecutionSummary, Holding, PortfolioExecuteRequest
from src.services import AuthService, ExecutionService
from src.storage.session_store import SessionStoreError

router = APIRouter(tags=["portfolio"])

@router.post("/portfolio/execute", response_model=ExecutionSummary)
def execute(
    body: PortfolioExecuteRequest,
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ExecutionSummary:
    try:
        return execution_service.execute(body)
    except SessionStoreError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BrokerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@router.get("/holdings", response_model=list[Holding])
def holdings(
    session_id: str,
    auth_service: AuthService = Depends(get_auth_service),
) -> list[Holding]:
    try:
        session = auth_service.resolve(session_id)
    except SessionStoreError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    adapter = get_adapter(session.broker)()
    try:
        return adapter.get_holdings(session)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except BrokerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
