"""LLM providers for cited answer generation.

Exposes the :class:`LLMProvider` interface and a lazily-constructed process-wide
default provider (Anthropic). The default is created on first use so importing
this package never requires an API key.
"""

from app.services.llm.base import INSUFFICIENT_CONTEXT_MESSAGE, LLMProvider

_default_provider: LLMProvider | None = None


def get_default_llm_provider() -> LLMProvider:
    """Return the shared default provider, constructing it on first use.

    Raises ``RuntimeError`` if no provider can be configured (e.g. a missing
    ``ANTHROPIC_API_KEY``).
    """
    global _default_provider
    if _default_provider is None:
        # Imported lazily so importing this package never imports the SDK.
        from app.services.llm.anthropic_provider import AnthropicLLMProvider

        _default_provider = AnthropicLLMProvider()
    return _default_provider


__all__ = [
    "INSUFFICIENT_CONTEXT_MESSAGE",
    "LLMProvider",
    "get_default_llm_provider",
]
