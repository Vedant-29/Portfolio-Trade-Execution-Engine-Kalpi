from __future__ import annotations

from src.adapters.base import AuthKind, BrokerAdapter

_ADAPTERS: dict[str, type[BrokerAdapter]] = {}

_REQUIRED_AUTH_METHODS: dict[AuthKind, tuple[str, ...]] = {
    "oauth_redirect": ("build_login_url", "exchange_code_for_session"),
    "credentials_form": ("credential_fields", "authenticate_with_credentials"),
    "api_key_only": ("authenticate_from_env",),
}

def register(adapter_cls: type[BrokerAdapter]) -> type[BrokerAdapter]:
    """Register an adapter and validate it implements the methods required
    by its declared auth_kind. Raises TypeError on mismatch.

    Usable as a decorator:
        @register
        class ZerodhaAdapter(BrokerAdapter): ...
    """

    for attr in ("name", "display_name", "auth_kind"):
        if not getattr(adapter_cls, attr, None):
            raise TypeError(f"{adapter_cls.__name__} must set ClassVar `{attr}`")

    auth_kind: AuthKind = adapter_cls.auth_kind
    if auth_kind not in _REQUIRED_AUTH_METHODS:
        raise TypeError(
            f"{adapter_cls.__name__} declares unknown auth_kind={auth_kind!r}"
        )

    base_methods = {
        method: getattr(BrokerAdapter, method)
        for method in _REQUIRED_AUTH_METHODS[auth_kind]
    }
    for method, base_impl in base_methods.items():
        if getattr(adapter_cls, method) is base_impl:
            raise TypeError(
                f"{adapter_cls.__name__} declares auth_kind={auth_kind!r} "
                f"but did not override {method}()"
            )

    if adapter_cls.name in _ADAPTERS:
        existing = _ADAPTERS[adapter_cls.name].__name__
        raise TypeError(
            f"Adapter name {adapter_cls.name!r} is already registered by {existing}"
        )

    _ADAPTERS[adapter_cls.name] = adapter_cls
    return adapter_cls

def get_adapter(name: str) -> type[BrokerAdapter]:
    try:
        return _ADAPTERS[name]
    except KeyError as exc:
        raise KeyError(f"No adapter registered for broker={name!r}") from exc

def registered_brokers() -> list[str]:
    return sorted(_ADAPTERS.keys())

def all_adapter_classes() -> dict[str, type[BrokerAdapter]]:
    return dict(_ADAPTERS)

def _reset_for_tests() -> None:
    _ADAPTERS.clear()

def load_all_adapters() -> list[str]:
    """Import and register every built-in adapter.

    Called once at app startup. Each adapter module registers itself
    via the `register` decorator at import time. Import errors are
    propagated — a broken adapter module is a bug, not a soft failure.

    Returns the list of registered broker names.
    """

    from src.adapters.angelone import AngelOneAdapter
    from src.adapters.fyers import FyersAdapter
    from src.adapters.groww import GrowwAdapter
    from src.adapters.paytm import PaytmAdapter
    from src.adapters.upstox import UpstoxAdapter
    from src.adapters.zerodha import ZerodhaAdapter

    _register_once(ZerodhaAdapter)
    _register_once(UpstoxAdapter)
    _register_once(AngelOneAdapter)
    _register_once(FyersAdapter)
    _register_once(GrowwAdapter)
    _register_once(PaytmAdapter)
    return registered_brokers()

def _register_once(cls: type[BrokerAdapter]) -> None:

    if cls.name in _ADAPTERS:
        return
    register(cls)
