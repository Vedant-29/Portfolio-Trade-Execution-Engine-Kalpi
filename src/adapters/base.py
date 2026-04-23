from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import ClassVar, Literal

from pydantic import BaseModel

from src.schemas import BrokerSession, Holding, OrderRequest, OrderResult

AuthKind = Literal["oauth_redirect", "credentials_form", "api_key_only"]

class FieldSpec(BaseModel):
    """Declarative description of one input a credentials_form broker needs.

    The frontend renders a generic form from the list of FieldSpecs the
    adapter provides — so AngelOne's (client_id, pin, totp) and Firstock's
    (userid, password, totp) reuse the exact same UI.
    """

    name: str
    label: str
    type: Literal["text", "password", "number"] = "text"
    pattern: str | None = None
    hint: str | None = None
    max_length: int | None = None

class BrokerAdapter(ABC):
    """Canonical broker interface.

    Every adapter declares its `auth_kind`. The registry validator enforces
    that the matching auth method group is implemented. Downstream methods
    (place_order, cancel_order, get_holdings, get_order_status,
    authorization_header) are abstract and must be implemented by every
    adapter regardless of auth_kind.
    """

    name: ClassVar[str]
    display_name: ClassVar[str]
    auth_kind: ClassVar[AuthKind]

    def build_login_url(self, redirect_uri: str, state: str) -> str:
        raise NotImplementedError(
            f"{type(self).__name__}.build_login_url is only required for "
            "auth_kind='oauth_redirect'"
        )

    def exchange_code_for_session(self, params: Mapping[str, str]) -> BrokerSession:
        raise NotImplementedError(
            f"{type(self).__name__}.exchange_code_for_session is only required "
            "for auth_kind='oauth_redirect'"
        )

    def credential_fields(self) -> list[FieldSpec]:
        raise NotImplementedError(
            f"{type(self).__name__}.credential_fields is only required for "
            "auth_kind='credentials_form'"
        )

    def authenticate_with_credentials(self, **fields: str) -> BrokerSession:
        raise NotImplementedError(
            f"{type(self).__name__}.authenticate_with_credentials is only required "
            "for auth_kind='credentials_form'"
        )

    def authenticate_from_env(self) -> BrokerSession:
        raise NotImplementedError(
            f"{type(self).__name__}.authenticate_from_env is only required for "
            "auth_kind='api_key_only'"
        )

    @abstractmethod
    def authorization_header(self, session: BrokerSession) -> dict[str, str]:
        """Return the HTTP headers a downstream request should include to
        authenticate as this session. Hides per-broker header quirks
        (Zerodha's `Authorization: token api_key:access_token` etc.)."""

    @abstractmethod
    def place_order(self, session: BrokerSession, req: OrderRequest) -> OrderResult:
        ...

    @abstractmethod
    def cancel_order(self, session: BrokerSession, broker_order_id: str) -> None: ...

    @abstractmethod
    def get_order_status(
        self, session: BrokerSession, broker_order_id: str
    ) -> OrderResult: ...

    @abstractmethod
    def get_holdings(self, session: BrokerSession) -> list[Holding]: ...
