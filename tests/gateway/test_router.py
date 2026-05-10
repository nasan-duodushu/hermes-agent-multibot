"""Tests for gateway.router – topic-based, bot-aware update dispatch."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from gateway.models import TopicUpdate
from gateway.router import UpdateRouter


@pytest.fixture
def router() -> UpdateRouter:
    return UpdateRouter()


# ── helpers ──────────────────────────────────────────────────────────────────

def make_collector() -> tuple[list[TopicUpdate], Any]:
    """Return (collected_list, async_handler)."""
    collected: list[TopicUpdate] = []

    async def _handler(update: TopicUpdate) -> None:
        collected.append(update)

    return collected, _handler


# ── subscribe / dispatch ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_to_matching_handler(router: UpdateRouter) -> None:
    collected, handler = make_collector()
    router.subscribe("bot-1", "commands", handler)

    update = TopicUpdate(bot_id="bot-1", topic="commands", payload={"text": "/start"})
    results = await router.dispatch(update)

    assert len(collected) == 1
    assert collected[0].payload["text"] == "/start"
    assert results == [None]  # no errors


@pytest.mark.asyncio
async def test_dispatch_no_match_returns_empty(router: UpdateRouter) -> None:
    collected, handler = make_collector()
    router.subscribe("bot-1", "commands", handler)

    update = TopicUpdate(bot_id="bot-1", topic="payments")
    results = await router.dispatch(update)

    assert results == []
    assert collected == []


@pytest.mark.asyncio
async def test_dispatch_fan_out_multiple_handlers(router: UpdateRouter) -> None:
    c1, h1 = make_collector()
    c2, h2 = make_collector()
    router.subscribe("bot-1", "commands", h1)
    router.subscribe("bot-1", "commands", h2)

    update = TopicUpdate(bot_id="bot-1", topic="commands")
    results = await router.dispatch(update)

    assert len(c1) == 1
    assert len(c2) == 1
    assert results == [None, None]


# ── bot-aware isolation ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_isolation_between_bots(router: UpdateRouter) -> None:
    """Handler for bot-A must NOT receive updates routed to bot-B."""
    c_a, h_a = make_collector()
    c_b, h_b = make_collector()
    router.subscribe("bot-a", "commands", h_a)
    router.subscribe("bot-b", "commands", h_b)

    update_b = TopicUpdate(bot_id="bot-b", topic="commands", payload={"x": 1})
    await router.dispatch(update_b)

    assert c_a == [], "bot-a handler must NOT see bot-b update"
    assert len(c_b) == 1


# ── subscribe_many ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subscribe_many(router: UpdateRouter) -> None:
    collected, handler = make_collector()
    router.subscribe_many("bot-1", ["commands", "payments"], handler)

    await router.dispatch(TopicUpdate(bot_id="bot-1", topic="commands"))
    await router.dispatch(TopicUpdate(bot_id="bot-1", topic="payments"))

    assert len(collected) == 2


# ── unsubscribe ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unsubscribe_single(router: UpdateRouter) -> None:
    collected, handler = make_collector()
    router.subscribe("bot-1", "cmd", handler)
    router.unsubscribe("bot-1", "cmd", handler)

    await router.dispatch(TopicUpdate(bot_id="bot-1", topic="cmd"))
    assert collected == []


@pytest.mark.asyncio
async def test_unsubscribe_bot_removes_all(router: UpdateRouter) -> None:
    _, h1 = make_collector()
    _, h2 = make_collector()
    router.subscribe("bot-1", "a", h1)
    router.subscribe("bot-1", "b", h2)
    removed = router.unsubscribe_bot("bot-1")
    assert removed == 2
    assert router.topics_for_bot("bot-1") == set()


# ── idempotent subscribe ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subscribe_idempotent(router: UpdateRouter) -> None:
    collected, handler = make_collector()
    router.subscribe("bot-1", "cmd", handler)
    router.subscribe("bot-1", "cmd", handler)  # duplicate – should be no-op

    await router.dispatch(TopicUpdate(bot_id="bot-1", topic="cmd"))
    assert len(collected) == 1  # handler called only once


# ── error handling in dispatch ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_captures_handler_error(router: UpdateRouter) -> None:
    async def bad_handler(update: TopicUpdate) -> None:
        raise RuntimeError("boom")

    collected, good_handler = make_collector()
    router.subscribe("bot-1", "cmd", bad_handler)
    router.subscribe("bot-1", "cmd", good_handler)

    results = await router.dispatch(TopicUpdate(bot_id="bot-1", topic="cmd"))

    # bad handler produced an error, good handler succeeded
    assert isinstance(results[0], RuntimeError)
    assert results[1] is None
    assert len(collected) == 1  # good handler still ran


# ── introspection ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_topics_for_bot(router: UpdateRouter) -> None:
    _, h = make_collector()
    router.subscribe("bot-1", "a", h)
    router.subscribe("bot-1", "b", h)
    router.subscribe("bot-2", "c", h)
    assert router.topics_for_bot("bot-1") == {"a", "b"}
    assert router.topics_for_bot("bot-2") == {"c"}


@pytest.mark.asyncio
async def test_handler_count(router: UpdateRouter) -> None:
    _, h1 = make_collector()
    _, h2 = make_collector()
    router.subscribe("bot-1", "cmd", h1)
    router.subscribe("bot-1", "cmd", h2)
    assert router.handler_count("bot-1", "cmd") == 2
    assert router.handler_count("bot-1", "nope") == 0
