import json

from gateway.channel_directory import _build_from_sessions
from hermes_cli.config import get_hermes_home


def test_channel_directory_keeps_same_chat_for_different_bots_distinct(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    sessions_path = sessions_dir / "sessions.json"

    data = {
        "agent:alpha:telegram:group:-100": {
            "chat_type": "group",
            "origin": {
                "platform": "telegram",
                "chat_id": "-100",
                "chat_name": "Shared Group",
                "bot_instance_id": "alpha",
            },
        },
        "agent:beta:telegram:group:-100": {
            "chat_type": "group",
            "origin": {
                "platform": "telegram",
                "chat_id": "-100",
                "chat_name": "Shared Group",
                "bot_instance_id": "beta",
            },
        },
    }
    sessions_path.write_text(json.dumps(data), encoding="utf-8")

    entries = _build_from_sessions("telegram")
    ids = {entry["id"] for entry in entries}
    assert ids == {"alpha:-100", "beta:-100"}
