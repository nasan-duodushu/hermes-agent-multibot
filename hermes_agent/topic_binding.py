"""Topic-binding module with bot-aware isolation.

Each bot instance gets its own isolated topic namespace so that
multiple bots running in the same process never leak state to
each other.  A *TopicRegistry* is scoped to a single bot_id;
a *DerivedState* subscribes to one or more topics and
automatically recomputes when any upstream topic publishes.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


# ── per-bot registry store (module-level, thread-safe) ──────────────
_global_lock = threading.Lock()
_registries: Dict[str, "TopicRegistry"] = {}


def get_registry(bot_id: str) -> "TopicRegistry":
    """Return (or create) the TopicRegistry for *bot_id*."""
    with _global_lock:
        if bot_id not in _registries:
            _registries[bot_id] = TopicRegistry(bot_id=bot_id)
        return _registries[bot_id]


def clear_registry(bot_id: str) -> None:
    """Remove the registry for *bot_id* (useful in teardown / tests)."""
    with _global_lock:
        _registries.pop(bot_id, None)


def clear_all_registries() -> None:
    """Remove every registry (test helper)."""
    with _global_lock:
        _registries.clear()


# ── Topic ────────────────────────────────────────────────────────────
@dataclass
class Topic:
    """A named, observable value slot inside one bot's namespace."""

    name: str
    _value: Any = None
    _subscribers: List[Callable[..., None]] = field(default_factory=list)

    @property
    def value(self) -> Any:
        return self._value

    def publish(self, value: Any) -> None:
        """Set the value and notify all subscribers."""
        self._value = value
        for cb in self._subscribers:
            cb(self.name, value)

    def subscribe(self, callback: Callable[..., None]) -> None:
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[..., None]) -> None:
        try:
            self._subscribers.remove(callback)
        except ValueError:
            pass


# ── DerivedState ─────────────────────────────────────────────────────
class DerivedState:
    """A computed value that auto-updates when upstream topics change.

    Parameters
    ----------
    registry : TopicRegistry
        Owning registry (scoped to one bot).
    source_topics : set[str]
        Names of upstream topics to subscribe to.
    compute : callable(dict[str, Any]) -> Any
        Pure function receiving ``{topic_name: current_value}``
        and returning the derived value.
    """

    def __init__(
        self,
        registry: "TopicRegistry",
        source_topics: Set[str],
        compute: Callable[[Dict[str, Any]], Any],
    ) -> None:
        self._registry = registry
        self._source_topics = set(source_topics)
        self._compute = compute
        self._value: Any = None
        self._initialized = False

        # subscribe to each source
        for tname in self._source_topics:
            topic = registry.ensure_topic(tname)
            topic.subscribe(self._on_topic_change)

        # compute initial value
        self._recompute()

    # ---- public API -------------------------------------------------
    @property
    def value(self) -> Any:
        return self._value

    def detach(self) -> None:
        """Unsubscribe from all source topics."""
        for tname in self._source_topics:
            topic = self._registry.get_topic(tname)
            if topic is not None:
                topic.unsubscribe(self._on_topic_change)

    # ---- internals --------------------------------------------------
    def _on_topic_change(self, _name: str, _value: Any) -> None:
        self._recompute()

    def _recompute(self) -> None:
        snapshot = {
            t: self._registry.get_value(t) for t in self._source_topics
        }
        self._value = self._compute(snapshot)
        self._initialized = True


# ── TopicRegistry (per-bot) ──────────────────────────────────────────
class TopicRegistry:
    """Isolated topic namespace for a single bot."""

    def __init__(self, bot_id: str) -> None:
        self.bot_id = bot_id
        self._topics: Dict[str, Topic] = {}

    # ---- topic management -------------------------------------------
    def ensure_topic(self, name: str) -> Topic:
        if name not in self._topics:
            self._topics[name] = Topic(name=name)
        return self._topics[name]

    def get_topic(self, name: str) -> Optional[Topic]:
        return self._topics.get(name)

    def get_value(self, name: str) -> Any:
        topic = self._topics.get(name)
        return topic.value if topic else None

    def publish(self, name: str, value: Any) -> None:
        self.ensure_topic(name).publish(value)

    def topic_names(self) -> Set[str]:
        return set(self._topics.keys())

    # ---- derived state shortcut ------------------------------------
    def derived(
        self,
        source_topics: Set[str],
        compute: Callable[[Dict[str, Any]], Any],
    ) -> DerivedState:
        return DerivedState(self, source_topics, compute)
