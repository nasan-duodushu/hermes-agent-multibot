"""Tests for gateway.registry – bot-aware registry with lifecycle state management."""
from __future__ import annotations

import pytest

from gateway.models import BotState
from gateway.registry import BotNotFoundError, BotRegistry, DuplicateBotError


@pytest.fixture
def registry() -> BotRegistry:
    return BotRegistry()


# ── register / unregister ────────────────────────────────────────────────────

async def test_register_creates_pending_bot(registry: BotRegistry) -> None:
    rec = await registry.register("bot-1", "tok-1", topics=["commands"])
    assert rec.bot_id == "bot-1"
    assert rec.state == BotState.pending
    assert rec.topics == ["commands"]
    assert "bot-1" in registry
    assert len(registry) == 1


async def test_register_duplicate_raises(registry: BotRegistry) -> None:
    await registry.register("bot-1", "tok-1")
    with pytest.raises(DuplicateBotError):
        await registry.register("bot-1", "tok-2")


async def test_unregister_removes_bot(registry: BotRegistry) -> None:
    await registry.register("bot-1", "tok-1")
    removed = await registry.unregister("bot-1")
    assert removed.bot_id == "bot-1"
    assert "bot-1" not in registry


async def test_unregister_unknown_raises(registry: BotRegistry) -> None:
    with pytest.raises(BotNotFoundError):
        await registry.unregister("nope")


# ── state transitions ────────────────────────────────────────────────────────

async def test_valid_transition_pending_to_running(registry: BotRegistry) -> None:
    await registry.register("b", "t")
    rec = await registry.transition("b", BotState.running)
    assert rec.state == BotState.running


async def test_valid_transition_running_to_error(registry: BotRegistry) -> None:
    await registry.register("b", "t")
    await registry.transition("b", BotState.running)
    rec = await registry.transition("b", BotState.error, error_message="crash")
    assert rec.state == BotState.error
    assert rec.error_message == "crash"


async def test_valid_transition_error_to_pending(registry: BotRegistry) -> None:
    await registry.register("b", "t")
    await registry.transition("b", BotState.running)
    await registry.transition("b", BotState.error, error_message="oops")
    rec = await registry.transition("b", BotState.pending)
    assert rec.state == BotState.pending
    assert rec.error_message is None  # cleared on non-error state


async def test_invalid_transition_raises(registry: BotRegistry) -> None:
    await registry.register("b", "t")
    # pending -> stopping is NOT allowed
    with pytest.raises(ValueError, match="Cannot transition"):
        await registry.transition("b", BotState.stopping)


async def test_transition_unknown_bot_raises(registry: BotRegistry) -> None:
    with pytest.raises(BotNotFoundError):
        await registry.transition("ghost", BotState.running)


# ── queries ──────────────────────────────────────────────────────────────────

async def test_list_bots_filter_by_state(registry: BotRegistry) -> None:
    await registry.register("a", "t")
    await registry.register("b", "t")
    await registry.transition("b", BotState.running)
    assert len(registry.list_bots(state=BotState.pending)) == 1
    assert len(registry.list_bots(state=BotState.running)) == 1
    assert len(registry.list_bots()) == 2


async def test_bots_needing_recovery(registry: BotRegistry) -> None:
    await registry.register("a", "t")
    await registry.register("b", "t")
    await registry.transition("b", BotState.running)
    # 'a' is pending → needs recovery
    assert [b.bot_id for b in registry.bots_needing_recovery()] == ["a"]


# ── topic management ─────────────────────────────────────────────────────────

async def test_set_topics(registry: BotRegistry) -> None:
    await registry.register("b", "t", topics=["x"])
    rec = await registry.set_topics("b", ["y", "z"])
    assert rec.topics == ["y", "z"]


# ── bot-aware isolation ──────────────────────────────────────────────────────

async def test_bots_are_isolated(registry: BotRegistry) -> None:
    """State change on bot A must NOT affect bot B."""
    await registry.register("a", "t1", topics=["commands"])
    await registry.register("b", "t2", topics=["payments"])
    await registry.transition("a", BotState.running)
    assert registry.get("b").state == BotState.pending  # unchanged
