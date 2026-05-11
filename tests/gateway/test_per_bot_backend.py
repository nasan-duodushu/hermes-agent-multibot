"""Per-bot LLM backend override tests.

Verifies that telegram.bots[<id>].extra.{llm_base_url, llm_api_key,
llm_provider, llm_api_mode, llm_model} take effect at
_resolve_session_agent_runtime() so one hermes instance can host
multiple bots each talking to a different LLM backend.

The `llm_*` prefix is required to avoid colliding with
gateway/platforms/telegram.py which already reads `extra.base_url`
as a custom Telegram Bot API server URL (line 911).

Companion to test_multi_telegram_runner.py / test_multibot_runtime_resolution.py:
those cover bot-aware model NAME routing; this covers bot-aware BACKEND routing.
"""
import pytest

from gateway.config import (
    GatewayConfig,
    Platform,
    PlatformConfig,
    TelegramBotConfig,
    TelegramPlatformConfig,
)
from gateway.run import GatewayRunner
from gateway.session import SessionSource


def _make_runner(monkeypatch, tmp_path, bots):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    telegram_cfg = TelegramPlatformConfig(
        enabled=True,
        token="primary_token_***",
        bots=bots,
    )
    config = GatewayConfig(
        platforms={Platform.TELEGRAM: telegram_cfg},
        sessions_dir=tmp_path / "sessions",
    )
    return GatewayRunner(config)


@pytest.fixture
def multibot_runner(monkeypatch, tmp_path):
    return _make_runner(
        monkeypatch,
        tmp_path,
        bots=[
            TelegramBotConfig(
                id="liko",
                token="liko_token",
                enabled=True,
                extra={
                    "llm_base_url": "https://grok2api.example/v1",
                    "llm_api_key": "sk-grok-liko",
                    "llm_provider": "custom",
                },
            ),
            TelegramBotConfig(
                id="yuzi",
                token="yuzi_token",
                enabled=True,
                extra={
                    "llm_base_url": "http://127.0.0.1:3003/v1",
                    "llm_api_key": "sk-windsurf-yuzi",
                    "llm_provider": "custom",
                    "llm_api_mode": "responses",
                },
            ),
        ],
    )


def _src(bot_instance_id):
    return SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="5595034210",
        chat_type="dm",
        bot_instance_id=bot_instance_id,
    )


def test_lookup_per_bot_backend_returns_liko_extras(multibot_runner):
    out = multibot_runner._lookup_per_bot_backend(_src("liko"))
    assert out == {
        "base_url": "https://grok2api.example/v1",
        "api_key": "sk-grok-liko",
        "provider": "custom",
    }


def test_lookup_per_bot_backend_returns_yuzi_extras_with_api_mode(multibot_runner):
    out = multibot_runner._lookup_per_bot_backend(_src("yuzi"))
    assert out == {
        "base_url": "http://127.0.0.1:3003/v1",
        "api_key": "sk-windsurf-yuzi",
        "provider": "custom",
        "api_mode": "responses",
    }


def test_lookup_per_bot_backend_empty_for_missing_bot_id(multibot_runner):
    assert multibot_runner._lookup_per_bot_backend(_src(None)) == {}
    assert multibot_runner._lookup_per_bot_backend(_src("")) == {}


def test_lookup_per_bot_backend_empty_for_unknown_bot(multibot_runner):
    assert multibot_runner._lookup_per_bot_backend(_src("ghost_bot")) == {}


def test_lookup_per_bot_backend_empty_for_non_telegram_platform(monkeypatch, tmp_path):
    runner = _make_runner(
        monkeypatch,
        tmp_path,
        bots=[
            TelegramBotConfig(
                id="liko",
                token="t",
                enabled=True,
                extra={"llm_base_url": "https://x.example/v1"},
            ),
        ],
    )
    source = SessionSource(platform=Platform.DISCORD, chat_id="c1", bot_instance_id="liko")
    assert runner._lookup_per_bot_backend(source) == {}


def test_lookup_per_bot_backend_empty_when_telegram_not_multibot_config(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    config = GatewayConfig(
        platforms={Platform.TELEGRAM: PlatformConfig(enabled=True, token="t")},
        sessions_dir=tmp_path / "sessions",
    )
    runner = GatewayRunner(config)
    assert runner._lookup_per_bot_backend(_src("liko")) == {}


def test_lookup_per_bot_backend_ignores_non_string_extras(monkeypatch, tmp_path):
    runner = _make_runner(
        monkeypatch,
        tmp_path,
        bots=[
            TelegramBotConfig(
                id="liko",
                token="t",
                enabled=True,
                extra={
                    "llm_base_url": "https://valid.example/v1",
                    "llm_api_key": 12345,  # not a string -> ignored
                    "llm_provider": "   ",  # whitespace-only -> ignored
                },
            ),
        ],
    )
    out = runner._lookup_per_bot_backend(_src("liko"))
    assert out == {"base_url": "https://valid.example/v1"}


def test_lookup_per_bot_backend_does_not_mistake_telegram_extra_base_url(monkeypatch, tmp_path):
    """If a bot configures `extra.base_url` (Telegram custom API server),
    that MUST NOT leak into LLM runtime — only `extra.llm_base_url` does."""
    runner = _make_runner(
        monkeypatch,
        tmp_path,
        bots=[
            TelegramBotConfig(
                id="liko",
                token="t",
                enabled=True,
                extra={
                    # This is Telegram-side, not LLM-side
                    "base_url": "https://telegram-bot-api.example/api",
                    # No llm_base_url at all
                },
            ),
        ],
    )
    out = runner._lookup_per_bot_backend(_src("liko"))
    assert out == {}, "extra.base_url is for Telegram API and must not be returned as LLM backend"


def test_resolve_session_agent_runtime_applies_per_bot_overrides(monkeypatch, multibot_runner):
    monkeypatch.setattr(
        "gateway.run._resolve_runtime_agent_kwargs",
        lambda **kwargs: {
            "api_key": "global_key",
            "base_url": "https://global.example/v1",
            "provider": "global_provider",
            "api_mode": None,
        },
    )
    _model, runtime_kwargs = multibot_runner._resolve_session_agent_runtime(
        source=_src("liko")
    )
    assert runtime_kwargs["base_url"] == "https://grok2api.example/v1"
    assert runtime_kwargs["api_key"] == "sk-grok-liko"
    assert runtime_kwargs["provider"] == "custom"
    assert runtime_kwargs["api_mode"] is None


def test_resolve_session_agent_runtime_yuzi_gets_different_backend(monkeypatch, multibot_runner):
    monkeypatch.setattr(
        "gateway.run._resolve_runtime_agent_kwargs",
        lambda **kwargs: {
            "api_key": "global_key",
            "base_url": "https://global.example/v1",
            "provider": "global_provider",
            "api_mode": None,
        },
    )
    _model, runtime_kwargs = multibot_runner._resolve_session_agent_runtime(
        source=_src("yuzi")
    )
    assert runtime_kwargs["base_url"] == "http://127.0.0.1:3003/v1"
    assert runtime_kwargs["api_key"] == "sk-windsurf-yuzi"
    assert runtime_kwargs["provider"] == "custom"
    assert runtime_kwargs["api_mode"] == "responses"


def test_resolve_session_agent_runtime_no_override_when_bot_id_missing(monkeypatch, multibot_runner):
    monkeypatch.setattr(
        "gateway.run._resolve_runtime_agent_kwargs",
        lambda **kwargs: {
            "api_key": "global_key",
            "base_url": "https://global.example/v1",
            "provider": "global_provider",
            "api_mode": None,
        },
    )
    _model, runtime_kwargs = multibot_runner._resolve_session_agent_runtime(
        source=_src(None)
    )
    assert runtime_kwargs["base_url"] == "https://global.example/v1"
    assert runtime_kwargs["api_key"] == "global_key"
    assert runtime_kwargs["provider"] == "global_provider"


def test_resolve_session_agent_runtime_no_override_for_unknown_bot(monkeypatch, multibot_runner):
    monkeypatch.setattr(
        "gateway.run._resolve_runtime_agent_kwargs",
        lambda **kwargs: {
            "api_key": "global_key",
            "base_url": "https://global.example/v1",
            "provider": "global_provider",
            "api_mode": None,
        },
    )
    _model, runtime_kwargs = multibot_runner._resolve_session_agent_runtime(
        source=_src("ghost_bot")
    )
    assert runtime_kwargs["base_url"] == "https://global.example/v1"


def test_resolve_session_agent_runtime_session_override_beats_per_bot(monkeypatch, multibot_runner):
    source = _src("liko")
    session_key = multibot_runner._session_key_for_source(source)
    multibot_runner._session_model_overrides[session_key] = {
        "model": "session-model",
        "provider": "session_provider",
        "api_key": "session_key",
        "base_url": "https://session.example/v1",
        "api_mode": None,
    }
    _model, runtime_kwargs = multibot_runner._resolve_session_agent_runtime(
        source=source, session_key=session_key
    )
    assert runtime_kwargs["base_url"] == "https://session.example/v1"
    assert runtime_kwargs["api_key"] == "session_key"
    assert runtime_kwargs["provider"] == "session_provider"
