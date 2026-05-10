"""Tests for topic_binding – bot-aware isolation & derived state."""

import pytest

from hermes_agent.topic_binding import (
    DerivedState,
    Topic,
    TopicRegistry,
    clear_all_registries,
    clear_registry,
    get_registry,
)


@pytest.fixture(autouse=True)
def _clean_registries():
    """Ensure each test starts with a clean global registry store."""
    clear_all_registries()
    yield
    clear_all_registries()


# ── Topic 基础 ───────────────────────────────────────────────────────
class TestTopic:
    def test_publish_and_read(self):
        t = Topic(name="price")
        assert t.value is None
        t.publish(42)
        assert t.value == 42

    def test_subscribe_callback(self):
        received = []
        t = Topic(name="sig")
        t.subscribe(lambda name, val: received.append((name, val)))
        t.publish("hello")
        assert received == [("sig", "hello")]

    def test_unsubscribe(self):
        received = []
        cb = lambda name, val: received.append(val)
        t = Topic(name="x")
        t.subscribe(cb)
        t.publish(1)
        t.unsubscribe(cb)
        t.publish(2)
        assert received == [1]  # 2 不应被收到

    def test_duplicate_subscribe_ignored(self):
        count = [0]
        cb = lambda n, v: count.__setitem__(0, count[0] + 1)
        t = Topic(name="dup")
        t.subscribe(cb)
        t.subscribe(cb)  # 重复，应忽略
        t.publish(True)
        assert count[0] == 1


# ── Bot-aware 隔离 ───────────────────────────────────────────────────
class TestBotIsolation:
    def test_separate_registries_per_bot(self):
        r1 = get_registry("bot-A")
        r2 = get_registry("bot-B")
        assert r1 is not r2
        assert r1.bot_id == "bot-A"
        assert r2.bot_id == "bot-B"

    def test_same_bot_returns_same_registry(self):
        assert get_registry("bot-A") is get_registry("bot-A")

    def test_clear_registry(self):
        r = get_registry("bot-C")
        r.publish("t", 1)
        clear_registry("bot-C")
        r2 = get_registry("bot-C")
        assert r2 is not r
        assert r2.get_value("t") is None

    def test_topics_do_not_leak_across_bots(self):
        r1 = get_registry("bot-X")
        r2 = get_registry("bot-Y")
        r1.publish("secret", 999)
        assert r2.get_value("secret") is None


# ── TopicRegistry ────────────────────────────────────────────────────
class TestTopicRegistry:
    def test_ensure_and_get(self):
        reg = TopicRegistry(bot_id="t")
        topic = reg.ensure_topic("foo")
        assert reg.get_topic("foo") is topic
        assert reg.get_topic("bar") is None

    def test_publish_and_get_value(self):
        reg = TopicRegistry(bot_id="t")
        reg.publish("k", 100)
        assert reg.get_value("k") == 100

    def test_topic_names(self):
        reg = TopicRegistry(bot_id="t")
        reg.ensure_topic("a")
        reg.ensure_topic("b")
        assert reg.topic_names() == {"a", "b"}


# ── DerivedState ─────────────────────────────────────────────────────
class TestDerivedState:
    def test_initial_computation(self):
        reg = TopicRegistry(bot_id="d")
        reg.publish("x", 3)
        reg.publish("y", 4)
        ds = reg.derived({"x", "y"}, lambda s: s["x"] + s["y"])
        assert ds.value == 7

    def test_auto_recompute_on_publish(self):
        reg = TopicRegistry(bot_id="d")
        reg.publish("a", 1)
        ds = reg.derived({"a"}, lambda s: s["a"] * 10)
        assert ds.value == 10
        reg.publish("a", 5)
        assert ds.value == 50

    def test_detach_stops_updates(self):
        reg = TopicRegistry(bot_id="d")
        reg.publish("v", 1)
        ds = reg.derived({"v"}, lambda s: s["v"])
        assert ds.value == 1
        ds.detach()
        reg.publish("v", 99)
        assert ds.value == 1  # 不再更新

    def test_derived_with_none_sources(self):
        reg = TopicRegistry(bot_id="d")
        ds = reg.derived({"missing"}, lambda s: s.get("missing", "default"))
        assert ds.value is None  # missing topic value is None

    def test_multi_source_partial_update(self):
        reg = TopicRegistry(bot_id="d")
        reg.publish("p", 10)
        reg.publish("q", 20)
        history = []
        ds = reg.derived(
            {"p", "q"},
            lambda s: s["p"] + s["q"],
        )
        assert ds.value == 30
        reg.publish("p", 100)
        assert ds.value == 120  # 100 + 20
