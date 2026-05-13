"""Web research context provider — Parallel.ai MCP wrapped in a sub-agent.

Agents see a single ``query_web(question)`` tool. Calling it routes the
question through a synthesizing sub-agent that talks to Parallel.ai's
MCP endpoint, so the main agent never sees raw search snippets in its
context window — only the synthesized cited answer.

Auth: keyless by default; if ``PARALLEL_API_KEY`` is set it is picked
up automatically by ``ParallelMCPBackend`` for the higher-rate
authenticated endpoint.

Public surface:
    * :func:`web_backend` — the lazy singleton backend (for lifespan setup/teardown)
    * :func:`web_tools` — drop into an agent's ``tools=`` list
    * :func:`web_instructions` — drop into ``build_instructions(WEB=...)``
"""

from __future__ import annotations

from typing import Any

from agno.context.web import ParallelMCPBackend, WebContextProvider

from app.settings import default_model

_BACKEND: ParallelMCPBackend | None = None
_PROVIDER: WebContextProvider | None = None


def web_backend() -> ParallelMCPBackend:
    """Return the process-wide ``ParallelMCPBackend``.

    Lazy-built on first call. The FastAPI lifespan in ``app/main.py``
    calls ``asetup`` / ``aclose`` on this singleton.
    """
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = ParallelMCPBackend()
    return _BACKEND


def web_provider() -> WebContextProvider:
    """Return the process-wide ``WebContextProvider``."""
    global _PROVIDER
    if _PROVIDER is None:
        _PROVIDER = WebContextProvider(
            backend=web_backend(),
            id="web",
            name="Web",
            model=default_model(),
        )
    return _PROVIDER


def web_tools() -> list[Any]:
    """Return the provider's agent-facing tool list.

    Drop ``*web_tools()`` into ``collect_tools(...)``. In default mode this
    is a single ``query_web(question)`` tool routed through the
    synthesizing sub-agent.
    """
    return web_provider().get_tools()


def web_instructions() -> str:
    """Return the provider's instruction snippet for ``build_instructions``."""
    return web_provider().instructions()


def _reset_for_tests() -> None:
    """Test-only helper — drop the singletons so each test starts clean."""
    global _BACKEND, _PROVIDER
    _BACKEND = None
    _PROVIDER = None
