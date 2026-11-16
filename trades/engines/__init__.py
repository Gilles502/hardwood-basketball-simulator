"""CPU trade engines: one module per trade type, each with `run(finder, team, wish) -> bool`.

`ENGINES` maps an initiator's wish kind to the engines tried for it, in order. Entries are `LazyEngine`s: the
module `trades.engines.<name>` is imported on first use, and an engine whose module does not exist yet is
skipped (it answers False). A new engine needs no edit here when its name is already listed: add
`trades/engines/<name>.py` with a `run` function.
"""
import importlib
import logging
from typing import Callable, Dict, List, Optional

main_log = logging.getLogger('main_sim')

ENGINE_PACKAGE = "trades.engines"

# Initiator wish kind -> engine module names, tried in this order until one closes a deal.
ENGINE_ORDER: Dict[str, List[str]] = {
    "NEED_STARTER": ["positional_swap", "win_now_youth", "star_upgrade"],
    "WANT_STAR": ["star_upgrade"],
    "STAR_WANTS_OUT": ["trade_demand"],
    "SELL_VETERANS": ["veteran_sale"],
    "SHED_TAX": ["tax_dump"],
    "CLEAR_LONG_CONTRACT": ["expiring_for_long", "tax_dump"],
    "RENT_VETERAN": ["deadline_rental"],
    "UNHAPPY_PLAYER": ["change_of_scenery"],
    "MOVE_UP_DRAFT": ["pick_trade_up"],
}


class LazyEngine:
    """An engine by module name: imports `trades.engines.<name>` when first needed and calls its `run`."""
    _MISSING = object()

    def __init__(self, name: str):
        self.name = name
        self._run = None
        self.broken = False   # its module failed to load (logged once by engines_for)

    def load(self) -> Optional[Callable]:
        if self._run is None:
            module_name = f"{ENGINE_PACKAGE}.{self.name}"
            try:
                module = importlib.import_module(module_name)
            except ModuleNotFoundError as ex:
                if ex.name != module_name:   # the engine exists but one of its own imports is broken
                    raise
                self._run = self._MISSING
            else:
                self._run = module.run
        return None if self._run is self._MISSING else self._run

    def available(self) -> bool:
        return self.load() is not None

    def __call__(self, finder, team, wish) -> bool:
        run = self.load()
        return bool(run(finder, team, wish)) if run is not None else False

    def __repr__(self) -> str:
        return f"LazyEngine({self.name!r})"


_ENGINE_CACHE: Dict[str, LazyEngine] = {}


def _engine(name: str) -> LazyEngine:
    return _ENGINE_CACHE.setdefault(name, LazyEngine(name))


ENGINES: Dict[str, List[Callable]] = {kind: [_engine(n) for n in names] for kind, names in ENGINE_ORDER.items()}


def _usable(engine: Callable) -> bool:
    """A plain callable always is; a LazyEngine when its module exists and loads. A module that fails to load
    (syntax error, a broken import of its own) is logged once as an error and skipped from then on."""
    if not isinstance(engine, LazyEngine):
        return True
    if engine.broken:
        return False
    try:
        return engine.available()
    except Exception as ex:
        engine.broken = True
        main_log.error(f"Trade engine module {ENGINE_PACKAGE}.{engine.name} failed to load: {ex}", exc_info=True)
        return False


def engines_for(kind: str) -> List[Callable]:
    """The engines tried for a wish of this kind, in order; [] when none serves it (or none is written yet).
    Never raises: an engine whose module is broken is logged and left out."""
    return [e for e in ENGINES.get(kind, []) if _usable(e)]
