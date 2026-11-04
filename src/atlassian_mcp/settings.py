"""Non-secret runtime configuration.

Credentials never live here -- they travel only in per-request headers
(see middleware.py) and are never read from the environment. Unknown
environment variables are ignored rather than rejected, since this service
runs in a shared container environment that may export variables unrelated
to it (PRD-21297 tech design, SOP §1.2).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCP_HTTP_", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8080


settings = Settings()
