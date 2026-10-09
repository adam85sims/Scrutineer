"""Scrutineer WebUI — Browser-based dashboard for agent behavioral testing.

Provides a FastAPI-powered web interface for running scenarios, viewing
traces, managing baselines, and configuring chaos injection — all wrapping
the existing Scrutineer core without modifying it.

Usage:
    scrutineer-serve                        # Start on localhost:8080
    scrutineer-serve --port 3000            # Custom port
    scrutineer-serve --host 0.0.0.0         # All interfaces
    scrutineer-serve --reload               # Auto-reload on code changes
"""
from __future__ import annotations

from scrutineer.web.app import create_app

__all__: list[str] = ["create_app"]
