"""Bot registry – add / remove / lookup / state transitions.

The registry enforces **bot-aware isolation**: each bot_id maps to exactly one
`BotRecord`, state transitions are validated, and topic bindings are scoped
per-bot.
"""
from __future__ import annotations

import asyncio
from typing import Sequence

from gateway.models import BotRecord, BotState


class DuplicateBotError(Exception):
    """Raised when trying to register a bot_id that already exists."""


class BotNotFoundError(KeyError):
    """Raised when a bot_id is not in the registry."""


class BotRegistry:
    """In-memory bot registry with lifecycle state management.

    Thread-safety: uses an `asyncio.Lock` to serialise mutations so that
    concurrent coroutines cannot put the registry into an inconsistent state.
    """

    def __init__(self) -> None:
        self._bots: dict[str, BotRecord] = {}
        self._lock = asyncio.Lock()

    # -- queries (lock-free, dict reads are atomic in CPython) ----------------

    def get(self, bot_id: str) -> BotRecord:
        try:
            return self._bots[bot_id]
        except KeyError:
            raise BotNotFoundError(bot_id)

    def list_bots(self, state: BotState | None = None) -> list[BotRecord]:
        """Return all bots, optionally filtered by state."""
        if state is None:
            return list(self._bots.values())
        return [b for b in self._bots.values() if b.state == state]

    def __len__(self) -> int:
        return len(self._bots)

    def __contains__(self, bot_id: str) -> bool:
        return bot_id in self._bots

    # -- mutations (locked) ---------------------------------------------------

    async def register(self, bot_id: str, token: str, topics: Sequence[str] = ()) -> BotRecord:
        """Register a new bot in *pending* state."""
        async with self._lock:
            if bot_id in self._bots:
                raise DuplicateBotError(f"Bot {bot_id!r} already registered")
            record = BotRecord(bot_id=bot_id, token=token, topics=list(topics))
            self._bots[bot_id] = record
            return record

    async def unregister(self, bot_id: str) -> BotRecord:
        """Remove a bot from the registry entirely."""
        async with self._lock:
            try:
                return self._bots.pop(bot_id)
            except KeyError:
                raise BotNotFoundError(bot_id)

    async def transition(self, bot_id: str, new_state: BotState, error_message: str | None = None) -> BotRecord:
        """Transition the bot to *new_state*.

        Raises `BotNotFoundError` if bot_id is unknown and `ValueError` on
        illegal state transitions.
        """
        async with self._lock:
            record = self.get(bot_id)  # may raise BotNotFoundError
            record.transition_to(new_state, error_message=error_message)
            return record

    async def set_topics(self, bot_id: str, topics: Sequence[str]) -> BotRecord:
        """Replace the topic list for *bot_id*."""
        async with self._lock:
            record = self.get(bot_id)
            record.topics = list(topics)
            return record

    # -- recovery helpers -----------------------------------------------------

    def bots_needing_recovery(self) -> list[BotRecord]:
        """Return bots in `pending` or `error` state (candidates for recovery)."""
        return [
            b for b in self._bots.values()
            if b.state in (BotState.pending, BotState.error)
        ]
