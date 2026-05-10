"""Topic-based update router.

The router maintains per-bot handler registrations scoped by *topic*.  When an
update arrives it is fanned out to every handler whose (bot_id, topic) pair
matches, enforcing **bot-aware isolation** – handlers registered for bot A
never see updates routed to bot B.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Awaitable, Callable, Sequence

from gateway.models import TopicUpdate

# A handler is an async callable that receives a TopicUpdate and returns None.
Handler = Callable[[TopicUpdate], Awaitable[None]]


class UpdateRouter:
    """Fan-out router keyed on (bot_id, topic)."""

    def __init__(self) -> None:
        # (bot_id, topic) -> list[Handler]
        self._handlers: dict[tuple[str, str], list[Handler]] = defaultdict(list)

    # -- registration ---------------------------------------------------------

    def subscribe(self, bot_id: str, topic: str, handler: Handler) -> None:
        """Register *handler* for updates matching *(bot_id, topic)*."""
        key = (bot_id, topic)
        if handler in self._handlers[key]:
            return  # idempotent
        self._handlers[key].append(handler)

    def subscribe_many(self, bot_id: str, topics: Sequence[str], handler: Handler) -> None:
        """Convenience: subscribe *handler* to multiple topics at once."""
        for t in topics:
            self.subscribe(bot_id, t, handler)

    def unsubscribe(self, bot_id: str, topic: str, handler: Handler) -> None:
        """Remove *handler* from *(bot_id, topic)*.  No-op if not registered."""
        key = (bot_id, topic)
        handlers = self._handlers.get(key)
        if handlers and handler in handlers:
            handlers.remove(handler)
            if not handlers:
                del self._handlers[key]

    def unsubscribe_bot(self, bot_id: str) -> int:
        """Remove **all** handlers for *bot_id*.  Returns count of removed entries."""
        to_remove = [k for k in self._handlers if k[0] == bot_id]
        for k in to_remove:
            del self._handlers[k]
        return len(to_remove)

    # -- dispatch -------------------------------------------------------------

    async def dispatch(self, update: TopicUpdate) -> list[BaseException | None]:
        """Fan out *update* to all matching handlers.

        Returns a list aligned with the handler list: ``None`` for success,
        the exception instance for failures.  Handlers run concurrently via
        `asyncio.gather(..., return_exceptions=True)`.
        """
        key = (update.bot_id, update.topic)
        handlers = self._handlers.get(key)
        if not handlers:
            return []
        results = await asyncio.gather(
            *(h(update) for h in handlers),
            return_exceptions=True,
        )
        return [r if isinstance(r, BaseException) else None for r in results]

    # -- introspection --------------------------------------------------------

    def topics_for_bot(self, bot_id: str) -> set[str]:
        """Return the set of topics that have at least one handler for *bot_id*."""
        return {topic for (bid, topic) in self._handlers if bid == bot_id}

    def handler_count(self, bot_id: str, topic: str) -> int:
        return len(self._handlers.get((bot_id, topic), []))
