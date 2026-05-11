from gateway.session_context import clear_session_vars, get_session_env, set_session_vars


def test_session_context_exposes_bot_instance_id():
    tokens = set_session_vars(
        platform="telegram",
        chat_id="123",
        session_key="agent:alpha:telegram:dm:123",
        bot_instance_id="alpha",
    )
    try:
        assert get_session_env("HERMES_SESSION_BOT_INSTANCE_ID", "") == "alpha"
    finally:
        clear_session_vars(tokens)


def test_session_context_clears_bot_instance_id_without_env_fallback(monkeypatch):
    monkeypatch.setenv("HERMES_SESSION_BOT_INSTANCE_ID", "stale")
    tokens = set_session_vars(bot_instance_id="beta")
    clear_session_vars(tokens)
    assert get_session_env("HERMES_SESSION_BOT_INSTANCE_ID", "") == ""
