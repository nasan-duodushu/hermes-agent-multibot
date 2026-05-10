from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from gateway.config import GatewayConfig, Platform, TelegramPlatformConfig
from gateway.session import SessionEntry, SessionSource, build_session_key


def _make_source(bot_instance_id: str = "alpha") -> SessionSource:
    return SessionSource(
        platform=Platform.TELEGRAM,
        user_id="u1",
        chat_id="c1",
        user_name="tester",
        chat_type="dm",
        bot_instance_id=bot_instance_id,
    )


def _make_runner(config: GatewayConfig | None = None):
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.config = config or GatewayConfig(
        platforms={Platform.TELEGRAM: TelegramPlatformConfig(enabled=True, token="tok")}
    )
    adapter = MagicMock()
    adapter.send = AsyncMock()
    runner.adapters = {Platform.TELEGRAM: adapter}
    runner._voice_mode = {}
    runner.hooks = SimpleNamespace(emit=AsyncMock(), loaded_hooks=False)
    runner._session_model_overrides = {}
    runner._pending_model_notes = {}
    runner._background_tasks = set()
    runner._running_agents = {}
    runner._pending_messages = {}
    runner._pending_approvals = {}
    runner._session_db = None
    runner._agent_cache = {}
    runner._agent_cache_lock = None
    runner._effective_model = None
    runner._effective_provider = None
    runner.session_store = MagicMock()
    session_key = build_session_key(_make_source())
    session_entry = SessionEntry(
        session_key=session_key,
        session_id="sess-1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
    )
    runner.session_store.get_or_create_session.return_value = session_entry
    runner.session_store._entries = {session_key: session_entry}
    runner._session_key_for_source = lambda source: build_session_key(source)
    return runner


def test_resolve_gateway_model_uses_bot_specific_model():
    from gateway.run import _resolve_gateway_model

    cfg = {
        "model": {"default": "global-model"},
        "platforms": {
            "telegram": {
                "bots": [
                    {"id": "alpha", "model": "bot-alpha-model"},
                    {"id": "beta", "model": "bot-beta-model"},
                ]
            }
        },
    }

    assert _resolve_gateway_model(cfg, source=_make_source("alpha")) == "bot-alpha-model"
    assert _resolve_gateway_model(cfg, source=_make_source("beta")) == "bot-beta-model"
    assert _resolve_gateway_model(cfg, source=_make_source("gamma")) == "global-model"


def test_session_key_includes_bot_instance_id_namespace():
    alpha_key = build_session_key(_make_source("alpha"))
    beta_key = build_session_key(_make_source("beta"))
    assert alpha_key == "agent:alpha:telegram:dm:c1"
    assert beta_key == "agent:beta:telegram:dm:c1"
    assert alpha_key != beta_key


def test_base_adapter_build_source_inherits_bot_instance_id():
    from gateway.platforms.base import BasePlatformAdapter

    class _DummyAdapter:
        platform = Platform.TELEGRAM
        _bot_instance_id = "alpha"

    source = BasePlatformAdapter.build_source(_DummyAdapter(), chat_id="123", chat_type="dm")
    assert source.bot_instance_id == "alpha"
