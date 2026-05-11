from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from gateway.config import GatewayConfig, HomeChannel, Platform, TelegramBotConfig, TelegramPlatformConfig
from gateway.platforms.base import SendResult
from gateway.session import SessionSource


def _make_source(bot_instance_id: str, chat_id: str = "c1", thread_id: str | None = None) -> SessionSource:
    return SessionSource(
        platform=Platform.TELEGRAM,
        user_id="u1",
        chat_id=chat_id,
        user_name="tester",
        chat_type="dm",
        thread_id=thread_id,
        bot_instance_id=bot_instance_id,
    )


def _make_runner():
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={
            Platform.TELEGRAM: TelegramPlatformConfig(
                enabled=True,
                token="tok",
                home_channel=HomeChannel(
                    platform=Platform.TELEGRAM,
                    chat_id="platform-home",
                    name="Platform Home",
                ),
                bots=[
                    TelegramBotConfig(
                        id="alpha",
                        token="tok-a",
                        home_channel=HomeChannel(
                            platform=Platform.TELEGRAM,
                            chat_id="alpha-home",
                            name="Alpha Home",
                            thread_id="topic-alpha",
                        ),
                    ),
                    TelegramBotConfig(
                        id="beta",
                        token="tok-b",
                        home_channel=HomeChannel(
                            platform=Platform.TELEGRAM,
                            chat_id="beta-home",
                            name="Beta Home",
                            thread_id="topic-beta",
                        ),
                    ),
                ],
            )
        }
    )
    runner.adapters = {}
    runner._platform_adapters = {}
    runner._adapter_keys = {}
    runner.delivery_router = SimpleNamespace(adapters={})
    runner._running_agents = {}
    runner._restart_requested = True
    runner._draining = False
    runner._shutdown_event = MagicMock()
    runner._running = True
    runner._exit_cleanly = False
    runner._exit_reason = None
    runner._background_tasks = set()
    runner._pending_messages = {}
    runner._pending_approvals = {}
    runner._busy_ack_ts = {}
    runner._running_agents_ts = {}
    runner.session_store = MagicMock()
    runner.session_store._entries = {}
    runner._get_cached_session_source = MagicMock(return_value=None)
    runner._update_runtime_status = MagicMock()
    runner._restart_drain_timeout = 0.1
    runner._restart_detached = False
    runner._restart_via_service = False
    runner._session_db = None
    runner._agent_cache = {}
    runner._agent_cache_lock = None
    runner._stop_task = None
    return runner


def _register_adapter(runner, bot_instance_id: str):
    adapter = MagicMock()
    adapter.platform = Platform.TELEGRAM
    adapter._bot_instance_id = bot_instance_id
    adapter.send = AsyncMock(return_value=SendResult(success=True, message_id=f"{bot_instance_id}-msg"))
    adapter.cancel_background_tasks = AsyncMock()
    adapter.disconnect = AsyncMock()
    runner._register_adapter(adapter)
    return adapter


def test_running_agent_count_can_scope_by_bot_instance_id():
    runner = _make_runner()
    runner._running_agents = {
        "agent:alpha:telegram:dm:c1": object(),
        "agent:beta:telegram:dm:c1": object(),
        "agent:alpha:telegram:dm:c2": object(),
    }

    assert runner._running_agent_count() == 3
    assert runner._running_agent_count(bot_instance_id="alpha") == 2
    assert runner._running_agent_count(bot_instance_id="beta") == 1


async def _drain_for_bot(runner, bot_instance_id: str):
    return await runner._drain_active_agents(0, bot_instance_id=bot_instance_id)


def test_snapshot_running_agents_filters_by_bot_instance_id():
    from gateway.run import _AGENT_PENDING_SENTINEL

    runner = _make_runner()
    alpha_agent = object()
    beta_agent = object()
    runner._running_agents = {
        "agent:alpha:telegram:dm:c1": alpha_agent,
        "agent:beta:telegram:dm:c1": beta_agent,
        "agent:alpha:telegram:dm:c2": _AGENT_PENDING_SENTINEL,
    }

    snapshot = runner._snapshot_running_agents(bot_instance_id="alpha")
    assert snapshot == {"agent:alpha:telegram:dm:c1": alpha_agent}


async def _notify_shutdown_for_bot(runner, bot_instance_id: str):
    return await runner._notify_active_sessions_of_shutdown(bot_instance_id=bot_instance_id)


def test_interrupt_running_agents_only_hits_selected_bot():
    runner = _make_runner()
    alpha_agent = MagicMock()
    beta_agent = MagicMock()
    runner._running_agents = {
        "agent:alpha:telegram:dm:c1": alpha_agent,
        "agent:beta:telegram:dm:c1": beta_agent,
    }

    runner._interrupt_running_agents("restart", bot_instance_id="alpha")

    alpha_agent.interrupt.assert_called_once_with("restart")
    beta_agent.interrupt.assert_not_called()


import pytest


@pytest.mark.asyncio
async def test_notify_active_sessions_of_shutdown_prefers_matching_bot_adapter():
    runner = _make_runner()
    alpha_adapter = _register_adapter(runner, "alpha")
    beta_adapter = _register_adapter(runner, "beta")
    alpha_source = _make_source("alpha", chat_id="alpha-chat", thread_id="topic-1")
    beta_source = _make_source("beta", chat_id="beta-chat", thread_id="topic-2")
    runner._running_agents = {
        "agent:alpha:telegram:dm:alpha-chat:topic-1": object(),
        "agent:beta:telegram:dm:beta-chat:topic-2": object(),
    }
    runner._get_cached_session_source = MagicMock(side_effect=lambda key: {
        "agent:alpha:telegram:dm:alpha-chat:topic-1": alpha_source,
        "agent:beta:telegram:dm:beta-chat:topic-2": beta_source,
    }.get(key))

    await _notify_shutdown_for_bot(runner, "alpha")

    assert alpha_adapter.send.await_count == 2
    beta_adapter.send.assert_not_awaited()
    first_args, first_kwargs = alpha_adapter.send.await_args_list[0]
    second_args, second_kwargs = alpha_adapter.send.await_args_list[1]
    assert first_args[0] == "alpha-chat"
    assert first_kwargs["metadata"] == {"thread_id": "topic-1"}
    assert second_args[0] == "alpha-home"
    assert second_kwargs["metadata"] == {"thread_id": "topic-alpha"}


@pytest.mark.asyncio
async def test_notify_active_sessions_of_shutdown_only_pings_selected_bot_home_channel():
    runner = _make_runner()
    alpha_adapter = _register_adapter(runner, "alpha")
    beta_adapter = _register_adapter(runner, "beta")

    await _notify_shutdown_for_bot(runner, "beta")

    beta_adapter.send.assert_awaited_once()
    alpha_adapter.send.assert_not_awaited()
    args, kwargs = beta_adapter.send.await_args
    assert args[0] == "beta-home"
    assert kwargs["metadata"] == {"thread_id": "topic-beta"}
