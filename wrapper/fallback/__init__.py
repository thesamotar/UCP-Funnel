"""Deterministic, no-LLM fallbacks that keep the demo running end to end when
no API key is set (or the LLM returns something unusable).

This whole folder is meant to be deleted once the LLM path is reliable — see
README.md here for the exact removal steps.
"""
from .colors import fallback_colors
from .routing import fallback_route

__all__ = ["fallback_route", "fallback_colors"]
