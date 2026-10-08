"""Application configuration, loaded from environment variables (prefix ``VP_``)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VP_", env_file=".env", extra="ignore")

    environment: str = "local"

    # Risk score at or above which a vehicle is reported as suspicious.
    risk_threshold: float = 0.5
    # A sustained average above this many km/day between two readings is
    # physically implausible for a private vehicle and is flagged outright.
    max_km_per_day: float = 1500.0

    chain_enabled: bool = True
    chain_rpc_url: str = "http://anvil:8545"
    contract_address: str = ""
    chain_private_key: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
