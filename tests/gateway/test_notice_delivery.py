from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import SendResult
from gateway.run import GatewayRunner
from gateway.session import SessionSource


def _make_source(bot_instance_id=None) -> SessionSource:
    return SessionSource(
        platform=Platform.SLACK,
        chat_id="C123",
        chat_type="channel",
        user_id="U123",
        thread_id="111.222",
        bot_instance_id=bot_instance_id,
    )


def _make_runner(extra=None):
    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={
            Platform.SLACK: PlatformConfig(enabled=True, token="***", extra=extra or {})
        }
    )
    adapter = MagicMock()
    adapter.send = AsyncMock(return_value=SendResult(success=True, message_id="public-1"))
    adapter.send_private_notice = AsyncMock(return_value=SendResult(success=True, message_id="private-1"))
    adapter._pending_messages = {}
    runner.adapters = {Platform.SLACK: adapter}
    runner._platform_adapters = {Platform.SLACK: [adapter]}
    runner._adapter_keys = {}
    runner._adapter_for_source = GatewayRunner._adapter_for_source.__get__(runner, GatewayRunner)
    runner._source_bot_instance_id = GatewayRunner._source_bot_instance_id.__get__(runner, GatewayRunner)
    runner._session_key_for_source = GatewayRunner._session_key_for_source.__get__(runner, GatewayRunner)
    runner._running_agents = {}
    runner._running_agents_ts = {}
    runner._pending_messages = {}
    runner._draining = False
    runner._busy_input_mode = "interrupt"
    return runner, adapter


@pytest.mark.asyncio
async def test_deliver_platform_notice_uses_private_delivery_when_configured():
    runner, adapter = _make_runner(extra={"notice_delivery": "private"})

    await runner._deliver_platform_notice(_make_source(), "hello")

    adapter.send_private_notice.assert_awaited_once_with(
        "C123",
        "U123",
        "hello",
        metadata={"thread_id": "111.222"},
    )
    adapter.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_platform_notice_falls_back_to_public_when_private_fails():
    runner, adapter = _make_runner(extra={"notice_delivery": "private"})
    adapter.send_private_notice = AsyncMock(return_value=SendResult(success=False, error="nope"))

    await runner._deliver_platform_notice(_make_source(), "hello")

    adapter.send.assert_awaited_once_with("C123", "hello", metadata={"thread_id": "111.222"})


@pytest.mark.asyncio
async def test_deliver_platform_notice_uses_public_delivery_by_default():
    runner, adapter = _make_runner()

    await runner._deliver_platform_notice(_make_source(), "hello")

    adapter.send.assert_awaited_once_with("C123", "hello", metadata={"thread_id": "111.222"})
    adapter.send_private_notice.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_platform_notice_uses_bot_specific_adapter_when_present():
    runner, default_adapter = _make_runner()
    alpha_adapter = MagicMock()
    alpha_adapter._bot_instance_id = "alpha"
    alpha_adapter.send = AsyncMock(return_value=SendResult(success=True, message_id="public-alpha"))
    alpha_adapter.send_private_notice = AsyncMock(return_value=SendResult(success=True, message_id="private-alpha"))

    runner._platform_adapters[Platform.SLACK] = [default_adapter, alpha_adapter]
    runner._source_bot_instance_id = lambda source: getattr(source, "bot_instance_id", None)

    await runner._deliver_platform_notice(_make_source(bot_instance_id="alpha"), "hello")

    alpha_adapter.send_private_notice.assert_not_awaited()
    alpha_adapter.send.assert_awaited_once_with("C123", "hello", metadata={"thread_id": "111.222"})
    default_adapter.send.assert_not_awaited()
