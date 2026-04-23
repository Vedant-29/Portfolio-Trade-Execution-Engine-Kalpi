from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    fernet_key: str = ""
    public_base_url: str = "http://localhost:8000"

    frontend_base_url: str = "http://localhost:5173"
    session_db_path: Path = Path("./data/sessions.sqlite")

    zerodha_api_key: str = ""
    zerodha_api_secret: str = ""
    upstox_api_key: str = ""
    upstox_api_secret: str = ""
    angelone_api_key: str = ""
    angelone_client_code: str = ""
    angelone_mpin: str = ""
    angelone_totp_secret: str = ""
    fyers_api_key: str = ""
    fyers_api_secret: str = ""
    groww_api_key: str = ""
    groww_api_secret: str = ""
    paytm_api_key: str = ""
    paytm_api_secret: str = ""

    def configured_brokers(self) -> list[str]:
        pairs = {
            "zerodha": (self.zerodha_api_key, self.zerodha_api_secret),
            "upstox": (self.upstox_api_key, self.upstox_api_secret),
            "angelone": (self.angelone_api_key, self.angelone_client_code),
            "fyers": (self.fyers_api_key, self.fyers_api_secret),
            "groww": (self.groww_api_key, self.groww_api_secret),
            "paytm": (self.paytm_api_key, self.paytm_api_secret),
        }
        return sorted(name for name, creds in pairs.items() if all(creds))

@lru_cache
def get_settings() -> Settings:
    return Settings()
