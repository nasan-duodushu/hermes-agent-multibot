"""Pydantic models for the gateway."""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class BotState(str, enum.Enum):
    """Lifecycle states for a managed bot."""

    pending = "pending"
    running = "running"
    stopping = "stopping"
    error = "error"


# Allowed state transitions – key is the *from* state, value is set of valid *to* states.
ALLOWED_TRANSITIONS: dict[BotState, frozenset[BotState]] = {
    BotState.pending: frozenset({BotState.running, BotState.error}),
    BotState.running: frozenset({BotState.stopping, BotState.error}),
    BotState.stopping: frozenset({BotState.pending, BotState.error}),
    BotState.error: frozenset({BotState.pending}),
}


def is_valid_transition(from_state: BotState, to_state: BotState) -> bool:
    """Return True if the transition is allowed."""
    return to_state in ALLOWED_TRANSITIONS.get(from_state, frozenset())


class BotRecord(BaseModel):
    """Internal record for a registered bot."""

    bot_id: str
    token: str
    state: BotState = BotState.pending
    topics: list[str] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def transition_to(self, new_state: BotState, error_message: str | None = None) -> None:
        """Transition to *new_state*, raising ValueError on illegal transitions."""
        if not is_valid_transition(self.state, new_state):
            raise ValueError(
                f"Cannot transition bot {self.bot_id!r} from {self.state.value!r} "
                f"to {new_state.value!r}"
            )
        self.state = new_state
        self.error_message = error_message if new_state == BotState.error else None
        self.updated_at = datetime.now(timezone.utc)


class TopicUpdate(BaseModel):
    """Thin wrapper around an incoming Telegram-style update, tagged with a topic."""

    bot_id: str
    topic: str
    payload: dict[str, Any] = Field(default_factory=dict)
