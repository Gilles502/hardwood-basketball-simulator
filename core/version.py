# core/version.py
"""The game version: the single source for the backend, the logs, the saves and the frontend build.

frontend/vite.config.ts reads VERSION and CHANNEL from this file at build time, so bump them here only.
"""
VERSION = "0.1.0"
CHANNEL = "Early Access"


def label() -> str:
    """Display form, e.g. 'v0.1.0 Early Access'."""
    return f"v{VERSION} {CHANNEL}".strip()
