import json

from gateway import mirror


def test_find_session_id_prefers_matching_bot_instance_id(tmp_path, monkeypatch):
    monkeypatch.setattr(mirror, "_SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(mirror, "_SESSIONS_INDEX", tmp_path / "sessions.json")

    data = {
        "agent:alpha:telegram:dm:chat1": {
            "session_id": "sess-alpha",
            "updated_at": "2026-05-10T10:00:00",
            "origin": {
                "platform": "telegram",
                "chat_id": "chat1",
                "user_id": "u1",
                "bot_instance_id": "alpha",
            },
        },
        "agent:beta:telegram:dm:chat1": {
            "session_id": "sess-beta",
            "updated_at": "2026-05-10T10:05:00",
            "origin": {
                "platform": "telegram",
                "chat_id": "chat1",
                "user_id": "u1",
                "bot_instance_id": "beta",
            },
        },
    }
    (tmp_path / "sessions.json").write_text(json.dumps(data), encoding="utf-8")

    assert mirror._find_session_id("telegram", "chat1", user_id="u1", bot_instance_id="alpha") == "sess-alpha"
    assert mirror._find_session_id("telegram", "chat1", user_id="u1", bot_instance_id="beta") == "sess-beta"


def test_find_session_id_without_bot_instance_id_keeps_legacy_behavior(tmp_path, monkeypatch):
    monkeypatch.setattr(mirror, "_SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(mirror, "_SESSIONS_INDEX", tmp_path / "sessions.json")

    data = {
        "agent:main:telegram:dm:chat1": {
            "session_id": "sess-main",
            "updated_at": "2026-05-10T10:00:00",
            "origin": {
                "platform": "telegram",
                "chat_id": "chat1",
                "user_id": "u1",
            },
        }
    }
    (tmp_path / "sessions.json").write_text(json.dumps(data), encoding="utf-8")

    assert mirror._find_session_id("telegram", "chat1", user_id="u1") == "sess-main"
