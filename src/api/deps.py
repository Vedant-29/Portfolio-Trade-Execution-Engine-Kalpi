"""FastAPI Depends wiring.

Construct each long-lived service once per process. FastAPI will call
these providers on every request, but `@lru_cache` makes that cheap.
"""

from __future__ import annotations

from functools import lru_cache

from src.config import get_settings
from src.services import AuthService, ExecutionService, NotificationService
from src.storage import EventStore, SessionStore


@lru_cache(maxsize=1)
def get_session_store() -> SessionStore:
    settings = get_settings()
    return SessionStore(
        db_path=settings.session_db_path,
        fernet_key=settings.fernet_key,
    )

@lru_cache(maxsize=1)
def get_event_store() -> EventStore:
    """EventStore lives in the same SQLite file as SessionStore — one
    volume mount for Docker, two independent tables inside."""
    settings = get_settings()
    return EventStore(db_path=settings.session_db_path, max_entries=500)

@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    settings = get_settings()
    return AuthService(
        session_store=get_session_store(),
        public_base_url=settings.public_base_url,
    )

@lru_cache(maxsize=1)
def get_notification_service() -> NotificationService:
    return NotificationService(event_store=get_event_store())

@lru_cache(maxsize=1)
def get_execution_service() -> ExecutionService:
    return ExecutionService(
        auth_service=get_auth_service(),
        notification_service=get_notification_service(),
    )

def _reset_for_tests() -> None:
    get_session_store.cache_clear()
    get_event_store.cache_clear()
    get_auth_service.cache_clear()
    get_notification_service.cache_clear()
    get_execution_service.cache_clear()
