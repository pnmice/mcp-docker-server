from typing import Any, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    """Server settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="")

    docker_host: Optional[str] = None
    docker_tls_verify: bool = False
    docker_cert_path: Optional[str] = None
    docker_api_version: Optional[str] = None

    @field_validator("docker_tls_verify", mode="before")
    @classmethod
    def parse_docker_tls_verify(cls, v: Any) -> bool:
        """Parse DOCKER_TLS_VERIFY from various string formats."""
        if isinstance(v, bool):
            return v
        elif isinstance(v, str):
            return v.lower() in ("1", "true", "yes", "on")
        else:
            # This handles None, empty string, or other types
            return False
