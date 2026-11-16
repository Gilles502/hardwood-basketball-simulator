"""Runtime context shared with the code that runs outside the game objects.

The Flask server owns two pieces of live state that the trade code needs to know about:
the league phase and the draft currently being run. Rather than letting the trade code
reach into the ``server`` module, the server registers small provider callables here.
Without a server (headless runs, tests) both providers return None.
"""
from typing import Any, Callable, Optional

_league_state: Callable[[], Optional[str]] = lambda: None
_active_draft: Callable[[], Any] = lambda: None


def register(league_state: Optional[Callable[[], Optional[str]]] = None,
             active_draft: Optional[Callable[[], Any]] = None) -> None:
    """Install the providers; calling it with no arguments resets both to "no server"."""
    global _league_state, _active_draft
    _league_state = league_state or (lambda: None)
    _active_draft = active_draft or (lambda: None)


def get_league_state() -> Optional[str]:
    return _league_state()


def get_active_draft() -> Any:
    """The running Draft instance, or None when no draft is in progress."""
    return _active_draft()
