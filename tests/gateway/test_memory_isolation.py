"""Phase A1 — per-bot memory namespace isolation tests.

Verifies that two HolographicMemoryProvider instances, each initialised
with a different bot_instance_id, write to physically separate SQLite
databases and cannot see each other's facts.
"""
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def hermes_home(tmp_path):
    """Create a temporary HERMES_HOME directory."""
    home = tmp_path / ".hermes-test"
    home.mkdir()
    # Write minimal config.yaml so _load_plugin_config doesn't fail
    (home / "config.yaml").write_text("memory:\n  provider: holographic\n")
    return home  # Return Path object (code uses / operator)


def _make_provider():
    """Create a fresh HolographicMemoryProvider with empty config."""
    from plugins.memory.holographic import HolographicMemoryProvider
    return HolographicMemoryProvider(config={})


# ── Test 1: db_path routing ──

def test_bot_id_routes_to_subdirectory(hermes_home):
    """bot_instance_id → $HERMES_HOME/memory/<bot_id>/memory_store.db"""
    with patch("hermes_constants.get_hermes_home", return_value=hermes_home):
        p = _make_provider()
        p.initialize("sess-1", bot_instance_id="liko")
    expected = hermes_home / "memory" / "liko" / "memory_store.db"
    assert p._store is not None
    assert p._store.db_path == expected


def test_empty_bot_id_uses_legacy_path(hermes_home):
    """Empty bot_instance_id → $HERMES_HOME/memory_store.db (legacy)"""
    with patch("hermes_constants.get_hermes_home", return_value=hermes_home):
        p = _make_provider()
        p.initialize("sess-2", bot_instance_id="")
    expected = hermes_home / "memory_store.db"
    assert p._store.db_path == expected


def test_no_bot_id_kwarg_uses_legacy_path(hermes_home):
    """No bot_instance_id kwarg at all → legacy path"""
    with patch("hermes_constants.get_hermes_home", return_value=hermes_home):
        p = _make_provider()
        p.initialize("sess-3")
    expected = hermes_home / "memory_store.db"
    assert p._store.db_path == expected


# ── Test 2: physical isolation ──

def test_two_bots_separate_databases(hermes_home):
    """Facts written by bot_a are invisible to bot_b."""
    with patch("hermes_constants.get_hermes_home", return_value=hermes_home):
        pa = _make_provider()
        pa.initialize("sess-a", bot_instance_id="bot_a")

        pb = _make_provider()
        pb.initialize("sess-b", bot_instance_id="bot_b")

    # bot_a stores a fact
    result_a = json.loads(pa._handle_fact_store({
        "action": "add",
        "content": "bot_a secret: the sky is purple on planet Zog",
        "category": "general",
    }))
    assert result_a.get("status") == "added"

    # bot_b stores a different fact
    result_b = json.loads(pb._handle_fact_store({
        "action": "add",
        "content": "bot_b secret: the ocean is made of lemonade",
        "category": "general",
    }))
    assert result_b.get("status") == "added"

    # bot_a can find its own fact
    search_a = json.loads(pa._handle_fact_store({
        "action": "search",
        "query": "sky purple Zog",
    }))
    assert search_a["count"] >= 1, "bot_a should find its own fact"

    # bot_b CANNOT find bot_a's fact
    search_b = json.loads(pb._handle_fact_store({
        "action": "search",
        "query": "sky purple Zog",
    }))
    assert search_b["count"] == 0, "bot_b must NOT see bot_a's fact"

    # bot_b can find its own fact
    search_b2 = json.loads(pb._handle_fact_store({
        "action": "search",
        "query": "ocean lemonade",
    }))
    assert search_b2["count"] >= 1, "bot_b should find its own fact"

    # bot_a CANNOT find bot_b's fact
    search_a2 = json.loads(pa._handle_fact_store({
        "action": "search",
        "query": "ocean lemonade",
    }))
    assert search_a2["count"] == 0, "bot_a must NOT see bot_b's fact"


def test_physical_files_are_separate(hermes_home):
    """Verify the SQLite files are at different physical paths."""
    with patch("hermes_constants.get_hermes_home", return_value=hermes_home):
        pa = _make_provider()
        pa.initialize("s1", bot_instance_id="alpha")

        pb = _make_provider()
        pb.initialize("s2", bot_instance_id="beta")

    path_a = hermes_home / "memory" / "alpha" / "memory_store.db"
    path_b = hermes_home / "memory" / "beta" / "memory_store.db"

    assert path_a.exists(), f"Expected {path_a} to exist"
    assert path_b.exists(), f"Expected {path_b} to exist"
    assert path_a != path_b


# ── Test 3: explicit db_path in config overrides bot_instance_id ──

def test_explicit_config_db_path_wins(hermes_home):
    """User-supplied db_path in config.yaml takes precedence."""
    custom = str(hermes_home / "custom_memory.db")
    from plugins.memory.holographic import HolographicMemoryProvider
    p = HolographicMemoryProvider(config={"db_path": custom})
    with patch("hermes_constants.get_hermes_home", return_value=hermes_home):
        p.initialize("sess-x", bot_instance_id="should_be_ignored")
    assert str(p._store.db_path) == custom


# ── Test 4: AIAgent.__init__ accepts bot_instance_id ──

def test_aiagent_accepts_bot_instance_id():
    """AIAgent.__init__ signature includes bot_instance_id kwarg."""
    import inspect
    from run_agent import AIAgent
    sig = inspect.signature(AIAgent.__init__)
    assert "bot_instance_id" in sig.parameters, \
        "AIAgent.__init__ must accept bot_instance_id parameter"
