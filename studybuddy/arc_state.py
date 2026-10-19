"""ARC-14: Lock-protected lazy singletons for process-global mutable state.

Replaces the ``_FOO = None`` + ``global`` + check-then-set pattern scattered
across the codebase (skills taxonomy caches, model caches, embedding caches)
with an explicit, thread-safe, test-friendly registry.

Per-process cache documentation (read this before adding a new singleton):
    * Every gunicorn/Render worker is its OWN OS process. A singleton created
      here lives and dies inside one process — it is NEVER shared between
      workers, dynos, or machines.
    * Safe uses: read-mostly, rebuildable caches (taxonomy JSON, compiled
      regexes, embedding matrices, model name lists). A cold process simply
      rebuilds the cache on first use; correctness never depends on another
      process having warmed it.
    * Unsafe uses: anything that coordinates work across requests/workers
      (locks, counters, rate-limit buckets, job queues, "already sent"
      flags). Those belong in the database or an external store (Redis),
      not in a module global.
    * Tests: call :func:`reset_singleton` / :func:`reset_all` to drop cached
      state between tests. Factories must be pure functions of their inputs
      (no hidden reliance on ambient global state) so a reset is faithful.

Usage:
    from studybuddy.arc_state import get_or_init

    def _load_taxonomy():
        ...  # expensive, called at most once per process

    def load_taxonomy():
        return get_or_init("skills_taxonomy.taxonomy", _load_taxonomy)
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional

__all__ = [
    "LazySingleton",
    "get_or_init",
    "get_holder",
    "reset_singleton",
    "reset_all",
]


class LazySingleton:
    """A single lazily-initialized value guarded by a lock.

    The factory runs at most once per holder instance (double-checked
    locking). If the factory raises, the holder stays uninitialized and the
    next :meth:`get` retries — a poisoned cache is worse than a slow retry.
    """

    def __init__(self, factory: Callable[[], Any], name: str = "") -> None:
        self._factory = factory
        self._name = name or getattr(factory, "__name__", "value")
        self._lock = threading.Lock()
        self._initialized = False
        self._value: Any = None

    def get(self) -> Any:
        """Return the value, running the factory once on first call."""
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self._value = self._factory()
                    self._initialized = True
        return self._value

    def reset(self) -> None:
        """Drop the cached value (tests only). The next :meth:`get` rebuilds."""
        with self._lock:
            self._initialized = False
            self._value = None

    @property
    def is_initialized(self) -> bool:
        """True if the factory has run and the value is cached."""
        with self._lock:
            return self._initialized

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"LazySingleton(name={self._name!r}, initialized={self._initialized})"


_registry: Dict[str, LazySingleton] = {}
_registry_lock = threading.Lock()


def get_holder(name: str, factory: Optional[Callable[[], Any]] = None) -> LazySingleton:
    """Return the holder registered under ``name``, creating it if needed.

    ``factory`` is required on first call for a name; later calls may omit it
    (a mismatched factory for an existing name is ignored — first wins).
    """
    holder = _registry.get(name)
    if holder is None:
        if factory is None:
            raise KeyError(f"No singleton registered under {name!r}")
        with _registry_lock:
            holder = _registry.get(name)
            if holder is None:
                holder = LazySingleton(factory, name=name)
                _registry[name] = holder
    return holder


def get_or_init(name: str, factory: Callable[[], Any]) -> Any:
    """Return the process-wide singleton ``name``, initializing once via ``factory``.

    Thread-safe: concurrent first calls still run ``factory`` exactly once.
    """
    return get_holder(name, factory).get()


def reset_singleton(name: str) -> None:
    """Drop one cached singleton (tests only)."""
    holder = _registry.get(name)
    if holder is not None:
        holder.reset()


def reset_all() -> None:
    """Drop every cached singleton (tests only)."""
    with _registry_lock:
        holders = list(_registry.values())
    for holder in holders:
        holder.reset()
