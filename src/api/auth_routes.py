"""Auth HTTP routes.

Three-shape response on GET /auth/{broker}/login, keyed by the
adapter's declared auth_kind. Frontend branches on this to decide
whether to redirect, render a form, or show a one-click button.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from src.adapters import FieldSpec
from src.adapters.errors import AuthError, BrokerError
from src.api.deps import get_auth_service
from src.config import Settings, get_settings
from src.services import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginInitResponse(BaseModel):
    broker: str
    auth_kind: str
    redirect_url: str | None = None
    fields: list[FieldSpec] | None = None

class SessionResponse(BaseModel):
    session_id: str
    broker: str
    user_id: str | None = None

class SessionStatusResponse(BaseModel):
    alive: bool
    broker: str
    session_id: str
    user_id: str | None = None

class CredentialsLoginBody(BaseModel):
    fields: dict[str, str]

@router.get("/{broker}/login", response_model=LoginInitResponse)
def begin_login(
    broker: str,
    auth_service: AuthService = Depends(get_auth_service),
) -> LoginInitResponse:
    state = uuid.uuid4().hex
    try:
        init = auth_service.begin_login(broker, state=state)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LoginInitResponse(
        broker=broker,
        auth_kind=init.auth_kind,
        redirect_url=init.redirect_url,
        fields=init.fields,
    )

@router.post("/{broker}/login", response_model=SessionResponse)
def complete_login(
    broker: str,
    body: CredentialsLoginBody | None = None,
    auth_service: AuthService = Depends(get_auth_service),
) -> SessionResponse:
    """Completes login for credentials_form or api_key_only brokers.

    - credentials_form: request body must contain `{"fields": {...}}`
      with the values the adapter's credential_fields() asked for.
    - api_key_only: body is ignored; we call authenticate_from_env().
    - oauth_redirect: rejected — those finish via GET /callback.
    """
    init = auth_service.begin_login(broker, state="")
    try:
        if init.auth_kind == "credentials_form":
            if body is None or not body.fields:
                raise HTTPException(
                    status_code=400,
                    detail="credentials_form brokers require `fields` in the body",
                )
            session_id, session = auth_service.complete_credentials_login(
                broker, body.fields
            )
        elif init.auth_kind == "api_key_only":
            session_id, session = auth_service.complete_api_key_login(broker)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Broker {broker!r} uses auth_kind={init.auth_kind!r}; "
                "use GET /auth/{broker}/login to obtain the redirect URL, then "
                "GET /auth/{broker}/callback.",
            )
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except BrokerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SessionResponse(
        session_id=session_id,
        broker=session.broker,
        user_id=session.user_id,
    )

@router.get("/{broker}/status", response_model=SessionStatusResponse)
def session_status(
    broker: str,
    session_id: str,
    auth_service: AuthService = Depends(get_auth_service),
) -> SessionStatusResponse:
    """Is the cached session still valid against the broker?

    Used by the frontend to decide whether to surface a "Reconnect"
    shortcut or fall back to a full re-auth flow.
    """
    alive, session = auth_service.is_alive(broker, session_id)
    return SessionStatusResponse(
        alive=alive,
        broker=broker,
        session_id=session_id,
        user_id=session.user_id if session else None,
    )

@router.delete("/{broker}/session")
def logout(
    broker: str,
    session_id: str,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    auth_service.logout(session_id)
    return {"status": "deleted"}

@router.get("/{broker}/callback")
def oauth_callback(
    broker: str,
    request_token: str | None = None,
    code: str | None = None,
    auth_code: str | None = None,
    state: str | None = None,
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """OAuth callback landing page.

    Different brokers pass the authorization token under different query
    keys (Zerodha: request_token; Upstox: code; Fyers: auth_code). We
    forward whatever is present to the adapter which knows what it wants.
    """
    params = {
        k: v
        for k, v in {
            "request_token": request_token,
            "code": code,
            "auth_code": auth_code,
        }.items()
        if v is not None
    }
    if not params:
        raise HTTPException(
            status_code=400,
            detail="Callback missing auth token (request_token / code / auth_code)",
        )
    try:
        session_id, _ = auth_service.complete_oauth_callback(broker, params)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except BrokerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    target = (
        f"{settings.frontend_base_url.rstrip('/')}/"
        f"?broker={broker}&session_id={session_id}"
    )
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)
