"""Application settings (spec/local-dev.md L3, spec/backend.md B2, B8).

Every variable documented in the L3 environment contract is read here with its
documented default. Live AI mode must fail configuration validation when the
provider, model, credential or spending ceiling is missing; there is never a
silent fallback to fixture results (L3).
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from functools import lru_cache
from typing import Literal

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AiMode(str, Enum):
    """AI execution mode (spec/local-dev.md L3, spec/backend.md B6)."""

    fixture = "fixture"
    live = "live"


class ConfigurationError(RuntimeError):
    """Raised at startup when the environment contract is not satisfiable.

    Used instead of a silent fixture fallback (spec/local-dev.md L3).
    """


#: MIME types accepted by the ingestion slice (spec/backend.md B4).
SUPPORTED_MIME_TYPES: tuple[str, ...] = ("application/pdf", "image/jpeg", "image/png")


class Settings(BaseSettings):
    """Typed view over the L3 environment contract (spec/local-dev.md L3)."""

    model_config = SettingsConfigDict(
        env_file=None,
        case_sensitive=False,
        extra="ignore",
    )

    # --- Runtime ---
    app_env: str = Field(default="development", alias="APP_ENV")

    # --- Persistence ---
    database_url: str = Field(
        default="postgresql+psycopg://dispute_demo:dispute_demo@db:5432/dispute_demo",
        alias="DATABASE_URL",
    )

    # --- Sessions and browser origin (spec/backend.md B8) ---
    session_secret: str = Field(default="dev-only-insecure-secret", alias="SESSION_SECRET")
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    session_ttl_seconds: int = Field(default=12 * 60 * 60, alias="SESSION_TTL_SECONDS")
    app_origin: str = Field(default="http://localhost:5173", alias="APP_ORIGIN")

    # --- Private file storage (spec/backend.md B4) ---
    file_storage_root: str = Field(default="/data/private", alias="FILE_STORAGE_ROOT")

    # --- AI provider adapter (spec/backend.md B6, spec/local-dev.md L3) ---
    ai_mode: AiMode = Field(default=AiMode.fixture, alias="AI_MODE")
    ai_provider: str | None = Field(default=None, alias="AI_PROVIDER")
    ai_model: str | None = Field(default=None, alias="AI_MODEL")
    ai_api_key: str | None = Field(default=None, alias="AI_API_KEY")
    ai_endpoint: str | None = Field(default=None, alias="AI_ENDPOINT")
    ai_demo_budget_usd: Decimal = Field(default=Decimal("0"), alias="AI_DEMO_BUDGET_USD")
    ai_max_concurrency: int = Field(default=1, ge=1, alias="AI_MAX_CONCURRENCY")

    # --- Legal pack (spec/backend.md B5) ---
    legal_pack_version: str = Field(default="tn-goods-v1", alias="LEGAL_PACK_VERSION")

    # --- Ingestion limits (spec/backend.md B4) ---
    max_case_files: int = Field(default=10, ge=1, alias="MAX_CASE_FILES")
    max_case_pages: int = Field(default=30, ge=1, alias="MAX_CASE_PAGES")
    max_file_bytes: int = Field(default=10_485_760, ge=1, alias="MAX_FILE_BYTES")
    max_case_bytes: int = Field(default=52_428_800, ge=1, alias="MAX_CASE_BYTES")

    # --- OCR (spec/backend.md B4) ---
    ocr_languages: str = Field(default="fra+ara+eng", alias="OCR_LANGUAGES")

    @field_validator("ai_provider", "ai_model", "ai_api_key", "ai_endpoint", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        """Treat an empty environment variable as absent."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def supported_mime_types(self) -> tuple[str, ...]:
        """MIME allow-list surfaced by ``GET /api/config`` (spec/backend.md B9)."""
        return SUPPORTED_MIME_TYPES

    @property
    def is_live_ai(self) -> bool:
        """True when provider calls are permitted (spec/local-dev.md L3)."""
        return self.ai_mode is AiMode.live

    @model_validator(mode="after")
    def _validate_live_mode(self) -> "Settings":
        """Fail fast when live mode lacks credentials, model or a spend ceiling.

        spec/local-dev.md L3: "Live mode must fail configuration validation if
        credentials, model or spending ceiling are absent."
        """
        if self.ai_mode is not AiMode.live:
            return self

        missing: list[str] = []
        if not self.ai_provider:
            missing.append("AI_PROVIDER")
        if not self.ai_model:
            missing.append("AI_MODEL")
        if not self.ai_api_key:
            missing.append("AI_API_KEY")
        if missing:
            raise ValueError(
                "AI_MODE=live requires " + ", ".join(missing) + "; fixture fallback is not allowed"
            )
        if self.ai_demo_budget_usd <= Decimal("0"):
            raise ValueError("AI_MODE=live requires AI_DEMO_BUDGET_USD greater than 0")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Raises:
        ConfigurationError: when the environment does not satisfy the L3
            contract. The message never contains secret values.
    """
    try:
        return Settings()  # type: ignore[call-arg]  # values come from the environment
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'settings'}: {error['msg']}"
            for error in exc.errors()
        )
        raise ConfigurationError(f"Invalid backend configuration: {details}") from None


def reset_settings_cache() -> None:
    """Clear the settings cache. Used by tests that patch the environment."""
    get_settings.cache_clear()


CookieSameSite = Literal["lax", "strict", "none"]

#: Session cookie name and policy (spec/backend.md B8, spec/local-dev.md L1).
SESSION_COOKIE_NAME = "sid"
SESSION_COOKIE_SAMESITE: CookieSameSite = "lax"
SESSION_COOKIE_PATH = "/"
CSRF_HEADER_NAME = "X-CSRF-Token"
