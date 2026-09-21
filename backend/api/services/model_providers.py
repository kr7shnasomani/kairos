"""
Synthesis provider registry (Layer 11).

One place that knows which OpenAI-compatible chat endpoints exist and in what order the cascade
tries them. `services/llm.py` (synthesis) and `routers/health.py` (liveness probe) both read this
list, so adding a provider is one entry plus its settings, not a new call path copied into each
caller. Ollama stays out of it: `/api/generate` is a different wire format, not a different URL.

The `name` is load-bearing beyond logging. It is returned as `model` on every answer, counted as the
provider mix in `benchmark/run_benchmark.py`, and rendered as the "answered by" badge in the UI, so
renaming a tier renames it in published figures too.
"""

from dataclasses import dataclass, field
from typing import Any

from api.config import Settings


@dataclass(frozen=True)
class Provider:
    """One OpenAI-compatible `/chat/completions` endpoint, with the settings the call needs."""

    name: str
    base_url: str
    api_key: str
    model: str
    timeout: float
    # Provider-specific body keys. Nemotron reasons before answering unless told not to; sending
    # that key to a provider that does not understand it is how tiers start 400ing, so it stays
    # per-provider rather than global.
    extra_body: dict[str, Any] = field(default_factory=dict)

    @property
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


def all_tiers(settings: Settings) -> list[Provider]:
    """
    Every tier this build knows, configured or not, in fallback order: Token Factory, NIM,
    OpenRouter, Gemini. The one list of provider names: the health probe looks tiers up here, so
    an unkeyed tier reads "not configured" rather than "unknown".

    Order note, unchanged from the comments it replaces: every tier below the first serves a
    different model, so a fallthrough blends models within one run and the benchmark marks that
    run SUSPECT.
    """
    no_thinking = {"chat_template_kwargs": {"enable_thinking": False}}
    return [
        Provider(
            name="tokenfactory",
            base_url=settings.NEBIUS_TOKEN_FACTORY_BASE_URL,
            api_key=settings.NEBIUS_TOKEN_FACTORY_API_KEY,
            model=settings.NEBIUS_TOKEN_FACTORY_MODEL,
            timeout=settings.NEBIUS_TOKEN_FACTORY_TIMEOUT,
            # Same Nemotron build as NIM, so it needs the same flag, behind its own switch.
            extra_body=no_thinking if settings.NEBIUS_TOKEN_FACTORY_DISABLE_THINKING else {},
        ),
        Provider(
            name="nim",
            base_url=settings.NVIDIA_NIM_BASE_URL,
            api_key=settings.NVIDIA_NIM_API_KEY,
            model=settings.NVIDIA_NIM_MODEL,
            timeout=settings.NVIDIA_NIM_TIMEOUT,
            extra_body=no_thinking if settings.NVIDIA_NIM_DISABLE_THINKING else {},
        ),
        Provider(
            name="openrouter",
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
            model=settings.OPENROUTER_MODEL,
            timeout=settings.OPENROUTER_TIMEOUT,
        ),
        Provider(
            name="gemini",
            base_url=settings.GEMINI_BASE_URL,
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
            # Kept at the 90 s this tier has always used: it is the last cloud tier, so its cap is
            # allowed to exceed the per-tier caps above it.
            timeout=90.0,
        ),
    ]


def synthesis_cascade(settings: Settings) -> list[Provider]:
    """Configured tiers in fallback order. A tier with no API key is dropped, which is what makes
    the order safe to extend: with only NVIDIA_NIM_API_KEY set this is NIM alone, exactly as before
    the registry existed."""
    return [p for p in all_tiers(settings) if p.api_key]
