from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BrokerSession(BaseModel):
    """Post-auth session. The single vocabulary every downstream call speaks.

    Different brokers return different shapes at login (Zerodha wants
    `token api_key:access_token` in the Authorization header; AngelOne
    uses a separate feed_token for its WebSocket). `token_header_format`
    and `extras` absorb that diversity here so the rest of the system
    stays uniform.
    """

    broker: str

    access_token: str
    token_header_format: str = "Bearer {access_token}"
    """Formatted via str.format(**session.model_dump()) at call time.
    Overridden by Zerodha to: 'token {access_token}' (api_key is prepended
    into access_token at auth time)."""

    feed_token: str | None = None
    """AngelOne WebSocket bearer — different from the REST JWT."""

    user_id: str | None = None
    refresh_token: str | None = None
    expires_at: datetime | None = None

    extras: dict[str, Any] = Field(default_factory=dict)
    """Per-broker overflow: anything that doesn't fit above."""
