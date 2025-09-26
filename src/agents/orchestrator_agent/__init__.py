"""Orchestrator agent package."""

from __future__ import annotations

from importlib import import_module
from typing import Any


def get_blueprint() -> Any:
    """Import lazily to avoid circular deps when Flask app boots."""
    routes = import_module("src.agents.orchestrator_agent.routes")
    return routes.orchestrator_bp


__all__ = ["get_blueprint"]
