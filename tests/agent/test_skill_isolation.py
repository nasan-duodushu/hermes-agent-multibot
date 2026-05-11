"""Phase A2 — per-bot skill isolation tests.

Verifies that skills placed under ``<HERMES_HOME>/skills/_bot/<bot_id>/``
are visible only to the matching ``bot_instance_id`` while skills under
``_shared/`` (or any other top-level path) remain visible to every bot.

Convention mirrors Phase A1's ``_bot/<id>/memory_store.db`` layout: a
single shared HERMES_HOME houses per-bot subtrees, the runtime reads the
active bot from ``HERMES_SESSION_BOT_INSTANCE_ID``, and ``_find_all_skills``
filters paths accordingly.
"""
from pathlib import Path
from unittest.mock import patch

from tools.skills_tool import (
    _find_all_skills,
    _skill_visible_to_current_bot,
)


def _make_skill(skills_dir, name, body="Do the thing.", category=None):
    """Helper to create a minimal skill directory with SKILL.md."""
    if category:
        skill_dir = skills_dir / category / name
    else:
        skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    content = f"""---
name: {name}
description: Description for {name}.
---

# {name}

{body}
"""
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return skill_dir


# ── _skill_visible_to_current_bot direct unit tests ────────────────────


class TestVisibilityHelper:
    """Pure-function tests for the visibility predicate."""

    def test_empty_bot_id_disables_isolation(self, tmp_path):
        skill_md = tmp_path / "_bot" / "riko" / "x" / "SKILL.md"
        assert _skill_visible_to_current_bot(skill_md, tmp_path, "") is True

    def test_top_level_skill_visible_to_any_bot(self, tmp_path):
        skill_md = tmp_path / "freeskill" / "SKILL.md"
        assert _skill_visible_to_current_bot(skill_md, tmp_path, "sakura") is True

    def test_shared_dir_visible_to_any_bot(self, tmp_path):
        skill_md = tmp_path / "_shared" / "common" / "SKILL.md"
        assert _skill_visible_to_current_bot(skill_md, tmp_path, "sakura") is True

    def test_bot_subdir_visible_to_matching_bot(self, tmp_path):
        skill_md = tmp_path / "_bot" / "sakura" / "ns-loop" / "SKILL.md"
        assert _skill_visible_to_current_bot(skill_md, tmp_path, "sakura") is True

    def test_bot_subdir_hidden_from_other_bot(self, tmp_path):
        skill_md = tmp_path / "_bot" / "riko" / "kanban" / "SKILL.md"
        assert _skill_visible_to_current_bot(skill_md, tmp_path, "sakura") is False

    def test_deep_nested_path_under_bot_dir(self, tmp_path):
        skill_md = tmp_path / "_bot" / "sakura" / "category" / "deep" / "SKILL.md"
        assert _skill_visible_to_current_bot(skill_md, tmp_path, "sakura") is True
        assert _skill_visible_to_current_bot(skill_md, tmp_path, "riko") is False

    def test_unknown_bot_id_only_sees_shared(self, tmp_path):
        shared = tmp_path / "_shared" / "x" / "SKILL.md"
        sakura_only = tmp_path / "_bot" / "sakura" / "y" / "SKILL.md"
        assert _skill_visible_to_current_bot(shared, tmp_path, "stranger") is True
        assert _skill_visible_to_current_bot(sakura_only, tmp_path, "stranger") is False

    def test_path_outside_scan_dir_falls_through(self, tmp_path):
        """relative_to() raises → helper conservatively returns True."""
        elsewhere = Path("/elsewhere/_bot/riko/x/SKILL.md")
        assert _skill_visible_to_current_bot(elsewhere, tmp_path, "sakura") is True


# ── _find_all_skills integration tests ─────────────────────────────────


def _patch_session_bot(bot_id):
    """Patch session_context to return the given bot_instance_id."""
    return patch(
        "tools.skills_tool._current_bot_instance_id",
        return_value=bot_id,
    )


def _names(skills):
    return {s["name"] for s in skills}


class TestFindAllSkillsPerBot:
    """End-to-end: discovery filters by active bot."""

    def test_empty_bot_id_returns_all(self, tmp_path):
        _make_skill(tmp_path, "common", category="_shared")
        _make_skill(tmp_path, "sakura-only", category="_bot/sakura")
        _make_skill(tmp_path, "riko-only", category="_bot/riko")
        with patch("tools.skills_tool.SKILLS_DIR", tmp_path), _patch_session_bot(""):
            names = _names(_find_all_skills())
        assert names == {"common", "sakura-only", "riko-only"}

    def test_sakura_sees_shared_and_own(self, tmp_path):
        _make_skill(tmp_path, "common", category="_shared")
        _make_skill(tmp_path, "sakura-only", category="_bot/sakura")
        _make_skill(tmp_path, "riko-only", category="_bot/riko")
        with patch("tools.skills_tool.SKILLS_DIR", tmp_path), _patch_session_bot("sakura"):
            names = _names(_find_all_skills())
        assert names == {"common", "sakura-only"}

    def test_riko_sees_shared_and_own(self, tmp_path):
        _make_skill(tmp_path, "common", category="_shared")
        _make_skill(tmp_path, "sakura-only", category="_bot/sakura")
        _make_skill(tmp_path, "riko-only", category="_bot/riko")
        with patch("tools.skills_tool.SKILLS_DIR", tmp_path), _patch_session_bot("riko"):
            names = _names(_find_all_skills())
        assert names == {"common", "riko-only"}

    def test_unknown_bot_only_sees_shared(self, tmp_path):
        _make_skill(tmp_path, "common", category="_shared")
        _make_skill(tmp_path, "sakura-only", category="_bot/sakura")
        with patch("tools.skills_tool.SKILLS_DIR", tmp_path), _patch_session_bot("stranger"):
            names = _names(_find_all_skills())
        assert names == {"common"}

    def test_top_level_skill_visible_to_any_bot(self, tmp_path):
        """Skills not under ``_bot/<id>/`` (e.g. legacy top-level layout) are
        always visible — this preserves backward compatibility for existing
        installs that have not migrated to the ``_shared/_bot`` convention."""
        _make_skill(tmp_path, "legacy")
        with patch("tools.skills_tool.SKILLS_DIR", tmp_path), _patch_session_bot("sakura"):
            names = _names(_find_all_skills())
        assert names == {"legacy"}

    def test_no_skills_dir_yields_nothing(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with patch("tools.skills_tool.SKILLS_DIR", empty), _patch_session_bot("sakura"):
            assert _find_all_skills() == []


class TestPerBotOverrideOrdering:
    """When the same skill name appears in both ``_shared/`` and
    ``_bot/<bot_id>/``, the per-bot copy must win (by stable scan order)."""

    def test_bot_specific_overrides_shared(self, tmp_path):
        # Same name in both places; differing bodies prove identity.
        _make_skill(tmp_path, "tools", body="SHARED VERSION", category="_shared")
        _make_skill(tmp_path, "tools", body="SAKURA OVERRIDE", category="_bot/sakura")
        with patch("tools.skills_tool.SKILLS_DIR", tmp_path), _patch_session_bot("sakura"):
            skills = _find_all_skills()
        names = [s["name"] for s in skills]
        # name appears exactly once (de-duplicated by name)
        assert names.count("tools") == 1

    def test_other_bot_falls_back_to_shared(self, tmp_path):
        _make_skill(tmp_path, "tools", category="_shared")
        _make_skill(tmp_path, "tools", category="_bot/sakura")
        with patch("tools.skills_tool.SKILLS_DIR", tmp_path), _patch_session_bot("riko"):
            names = _names(_find_all_skills())
        # riko cannot see the sakura override — they get the shared one
        assert names == {"tools"}
