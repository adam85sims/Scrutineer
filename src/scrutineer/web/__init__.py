"""Scrutineer WebUI — Browser-based dashboard for agent behavioral testing.

Provides a FastAPI-powered web interface for running scenarios, viewing
traces, managing baselines, and configuring chaos injection — all wrapping
the existing Scrutineer core without modifying it.

Requires the ``web`` extra: ``pip install "scrutineer-agents[web]"``.

Usage:
    scrutineer-serve                        # Start on localhost:8080
    scrutineer-serve --port 3000            # Custom port
    scrutineer-serve --host 0.0.0.0         # All interfaces
    scrutineer-serve --reload               # Auto-reload on code changes
"""
from __future__ import annotations

from typing import Any

__all__: list[str] = ["create_app"]


def __getattr__(name: str) -> Any:
    """Resolve ``create_app`` on first use rather than on package import.

    Importing this package happens *before* the ``scrutineer-serve`` entry point function runs,
    so a module-level ``from scrutineer.web.app import create_app`` killed the command with a
    bare ``ModuleNotFoundError: No module named 'fastapi'`` on any install without the ``web``
    extra — before ``main()`` could report which extra was missing. FastAPI is optional; the
    package import must not require it. (``scrutineer.web.server`` deliberately imports the app
    inside ``main()`` for the same reason.)
    """
    if name == "create_app":
        from scrutineer.web.app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
