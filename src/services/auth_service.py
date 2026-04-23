"""Auth orchestration.

Sits between the API routes and the adapter layer. The API knows
about HTTP (query params, form bodies); the adapter knows about the
broker's wire format. AuthService converts one to the other and
persists the resulting session.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.adapters import BrokerAdapter, FieldSpec, get_adapter
from src.adapters.errors import AuthError
from src.schemas import BrokerSession
from src.storage import SessionStore
from src.utils.logging import get_logger

_logger = get_logger(__name__)

@dataclass(frozen=True)
class LoginInit:
    """What the API returns to the frontend when auth starts.

    The frontend branches on `auth_kind` to decide:
      - oauth_redirect   → redirect the browser to `redirect_url`
      - credentials_form → render a form using `fields`
      - api_key_only     → show a single "Connect" button; POST back
                           to /auth/{broker}/login to complete
    """

    auth_kind: str
    redirect_url: str | None = None
    fields: list[FieldSpec] | None = None

class AuthService:
    def __init__(
        self,
        *,
        session_store: SessionStore,
        public_base_url: str,
    ) -> None:
        self._sessions = session_store
        self._base_url = public_base_url.rstrip("/")

    def _adapter(self, broker: str) -> BrokerAdapter:
        cls = get_adapter(broker)
        return cls()

    def begin_login(self, broker: str, *, state: str) -> LoginInit:
        adapter = self._adapter(broker)
        kind = adapter.auth_kind

        if kind == "oauth_redirect":
            redirect_uri = f"{self._base_url}/auth/{broker}/callback"
            return LoginInit(
                auth_kind=kind,
                redirect_url=adapter.build_login_url(redirect_uri, state),
            )

        if kind == "credentials_form":
            return LoginInit(auth_kind=kind, fields=adapter.credential_fields())

        if kind == "api_key_only":
            return LoginInit(auth_kind=kind)

        raise AuthError(f"Unknown auth_kind for broker={broker!r}", broker=broker)

    def complete_oauth_callback(
        self, broker: str, params: Mapping[str, str]
    ) -> tuple[str, BrokerSession]:
        adapter = self._adapter(broker)
        if adapter.auth_kind != "oauth_redirect":
            raise AuthError(
                f"Broker {broker!r} uses auth_kind={adapter.auth_kind!r}, not "
                f"oauth_redirect — callback not supported.",
                broker=broker,
            )
        session = adapter.exchange_code_for_session(params)
        session_id = self._sessions.save(session)
        _logger.info("session_created", broker=broker, session_id=session_id)
        return session_id, session

    def complete_credentials_login(
        self, broker: str, fields: Mapping[str, str]
    ) -> tuple[str, BrokerSession]:
        adapter = self._adapter(broker)
        if adapter.auth_kind != "credentials_form":
            raise AuthError(
                f"Broker {broker!r} uses auth_kind={adapter.auth_kind!r}, not "
                f"credentials_form.",
                broker=broker,
            )
        session = adapter.authenticate_with_credentials(**fields)
        session_id = self._sessions.save(session)
        _logger.info("session_created", broker=broker, session_id=session_id)
        return session_id, session

    def complete_api_key_login(self, broker: str) -> tuple[str, BrokerSession]:
        adapter = self._adapter(broker)
        if adapter.auth_kind != "api_key_only":
            raise AuthError(
                f"Broker {broker!r} uses auth_kind={adapter.auth_kind!r}, not "
                f"api_key_only.",
                broker=broker,
            )
        session = adapter.authenticate_from_env()
        session_id = self._sessions.save(session)
        _logger.info("session_created", broker=broker, session_id=session_id)
        return session_id, session

    def resolve(self, session_id: str) -> BrokerSession:
        return self._sessions.load(session_id)

    def logout(self, session_id: str) -> None:
        self._sessions.delete(session_id)

    def is_alive(self, broker: str, session_id: str) -> tuple[bool, BrokerSession | None]:
        """Check if a stored session still authenticates against the broker.

        Strategy: load the session from SQLite, then ask the adapter to
        fetch holdings. If the broker responds normally, the session is
        live. If it raises AuthError, the token is expired or revoked.

        Returns `(alive, session_or_None)`. A dead session is auto-deleted
        from storage so the next call returns a clean state.
        """
        try:
            session = self._sessions.load(session_id)
        except Exception:
            return False, None

        if session.broker != broker:
            return False, None

        adapter = self._adapter(broker)
        try:
            adapter.get_holdings(session)
        except AuthError:

            self._sessions.delete(session_id)
            return False, None
        except Exception:

            return True, session
        return True, session
