import pytest

from gateway.run import _parse_session_key
from gateway.session import SessionSource, build_session_key
from gateway.config import Platform


def test_parse_session_key_understands_multibot_namespace():
    parsed = _parse_session_key("agent:alpha:telegram:dm:12345")
    assert parsed == {
        "bot_instance_id": "alpha",
        "platform": "telegram",
        "chat_type": "dm",
        "chat_id": "12345",
    }


def test_parse_session_key_keeps_thread_id_for_dm():
    parsed = _parse_session_key("agent:beta:telegram:dm:12345:topic-7")
    assert parsed == {
        "bot_instance_id": "beta",
        "platform": "telegram",
        "chat_type": "dm",
        "chat_id": "12345",
        "thread_id": "topic-7",
    }


def test_parse_session_key_remains_backward_compatible_with_agent_main():
    parsed = _parse_session_key("agent:main:telegram:group:-100:42")
    assert parsed == {
        "bot_instance_id": "main",
        "platform": "telegram",
        "chat_type": "group",
        "chat_id": "-100",
    }


def test_build_session_key_and_parse_round_trip_multibot_dm():
    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="12345",
        chat_type="dm",
        user_id="u1",
        bot_instance_id="alpha",
    )
    session_key = build_session_key(source)
    assert session_key == "agent:alpha:telegram:dm:12345"
    assert _parse_session_key(session_key)["bot_instance_id"] == "alpha"
