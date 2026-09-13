"""AI adapter selection (spec/local-dev.md L3, spec/backend.md B6).

Exactly one adapter is active per process, chosen by ``AI_MODE``:

* ``fixture`` -- :class:`~app.ai.fixture.FixtureAiAdapter`, deterministic rules
  over the real stored page text. No provider call is made anywhere, including
  health checks and the intake gate (L3).
* ``live`` -- :class:`~app.ai.live.LiveAiAdapter` against the configured provider.
  Missing credentials, model or spending ceiling already fail configuration
  validation at startup (``app.config.Settings``), so this factory cannot be
  reached in an under-configured live process.

There is no third path and no fallback: a failed live call raises and the job
records the failure. Silently returning fixture output after a live failure is
forbidden (L3), because it would present deterministic stand-in data as a real
assessment.
"""

from __future__ import annotations

from app.ai.base import AiAdapter, AiResponseInvalidError, AiUnavailableError
from app.ai.fixture import FixtureAiAdapter
from app.config import AiMode, Settings

__all__ = [
    "AiAdapter",
    "AiResponseInvalidError",
    "AiUnavailableError",
    "FixtureAiAdapter",
    "get_adapter",
]


def get_adapter(settings: Settings) -> AiAdapter:
    """Return the adapter for the configured mode (spec/local-dev.md L3).

    Raises:
        RuntimeError: when live mode somehow lacks a model or credential. This is
            defence in depth; ``Settings`` rejects that configuration at startup.
    """
    if settings.ai_mode is AiMode.fixture:
        return FixtureAiAdapter()

    # Imported lazily so a fixture-mode process never imports the HTTP client
    # path, and so no provider module is loaded when no credential exists.
    from app.ai.live import LiveAiAdapter

    if not settings.ai_model or not settings.ai_api_key:  # pragma: no cover - guarded upstream
        raise RuntimeError("AI_MODE=live requires AI_MODEL and AI_API_KEY")
    return LiveAiAdapter(
        model=settings.ai_model,
        api_key=settings.ai_api_key,
        endpoint=settings.ai_endpoint,
        provider=settings.ai_provider,
    )
