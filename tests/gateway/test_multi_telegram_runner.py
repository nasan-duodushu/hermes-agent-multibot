"""Tests for GatewayRunner Telegram multi-bot fan-out behavior."""

from dataclasses import dataclass
from unittest.mock import MagicMock

from gateway.config import Platform, PlatformConfig
from gateway.run import GatewayRunner


@dataclass(eq=False)
class FakeAdapter:
    platform: Platform
    _bot_instance_id: str | None = None


class DummyDeliveryRouter:
    def __init__(self):
        self.adapters = {}


class DummyConfig:
    group_sessions_per_user = True
    thread_sessions_per_user = False


def _make_runner():
    runner = object.__new__(GatewayRunner)
    runner.adapters = {}
    runner._platform_adapters = {}
    runner._adapter_keys = {}
    runner.delivery_router = DummyDeliveryRouter()
    runner._update_platform_runtime_status = MagicMock()
    runner.config = DummyConfig()
    return runner


def test_register_adapter_keeps_platform_primary_and_tracks_siblings():
    runner = _make_runner()
    alpha = FakeAdapter(platform=Platform.TELEGRAM, _bot_instance_id="alpha")
    beta = FakeAdapter(platform=Platform.TELEGRAM, _bot_instance_id="beta")

    runner._register_adapter(alpha)
    runner._register_adapter(beta)

    assert runner.adapters[Platform.TELEGRAM] is alpha
    assert runner._platform_adapters[Platform.TELEGRAM] == [alpha, beta]
    assert runner.delivery_router.adapters is runner.adapters
    assert runner._adapter_keys[alpha] == "telegram/alpha"
    assert runner._adapter_keys[beta] == "telegram/beta"


def test_unregister_adapter_promotes_sibling_for_platform_primary():
    runner = _make_runner()
    alpha = FakeAdapter(platform=Platform.TELEGRAM, _bot_instance_id="alpha")
    beta = FakeAdapter(platform=Platform.TELEGRAM, _bot_instance_id="beta")

    runner._register_adapter(alpha)
    runner._register_adapter(beta)
    runner._unregister_adapter(alpha)

    assert runner.adapters[Platform.TELEGRAM] is beta
    assert runner._platform_adapters[Platform.TELEGRAM] == [beta]
    assert alpha not in runner._adapter_keys


def test_unregister_adapter_removes_platform_when_last_instance_gone():
    runner = _make_runner()
    alpha = FakeAdapter(platform=Platform.TELEGRAM, _bot_instance_id="alpha")

    runner._register_adapter(alpha)
    runner._unregister_adapter(alpha)

    assert Platform.TELEGRAM not in runner.adapters
    assert Platform.TELEGRAM not in runner._platform_adapters
    assert runner.delivery_router.adapters is runner.adapters


def test_adapter_instance_key_defaults_to_platform_for_non_multi_instance_adapter():
    runner = _make_runner()
    discord_adapter = FakeAdapter(platform=Platform.DISCORD)

    assert runner._adapter_instance_key(discord_adapter) == "discord"


def test_create_adapter_passes_bot_instance_id_to_telegram_adapter(monkeypatch):
    runner = _make_runner()

    class FakeTelegramAdapter:
        def __init__(self, config, bot_instance_id="default"):
            self.config = config
            self.bot_instance_id = bot_instance_id

    monkeypatch.setattr("gateway.run.check_telegram_requirements", lambda: True, raising=False)
    import gateway.platforms.telegram as telegram_module
    monkeypatch.setattr(telegram_module, "check_telegram_requirements", lambda: True)
    monkeypatch.setattr(telegram_module, "TelegramAdapter", FakeTelegramAdapter)

    adapter = GatewayRunner._create_adapter(
        runner,
        Platform.TELEGRAM,
        PlatformConfig(token="tok-support"),
        instance_id="support",
    )

    assert isinstance(adapter, FakeTelegramAdapter)
    assert adapter.bot_instance_id == "support"


def test_multi_bot_config_iterates_enabled_bots_for_runner_fanout_shape():
    class FakeTelegramBotConfig:
        def __init__(self, bot_id: str, token: str | None, enabled: bool = True):
            self.id = bot_id
            self.token = token
            self.api_key = None
            self.enabled = enabled

    class FakeTelegramPlatformConfig(PlatformConfig):
        def __init__(self, *, enabled: bool, bots: list[FakeTelegramBotConfig]):
            super().__init__(enabled=enabled)
            self.bots = bots

        def iter_enabled_bots(self):
            return [bot for bot in self.bots if bot.enabled and (bot.token or bot.api_key)]

    cfg = FakeTelegramPlatformConfig(
        enabled=True,
        bots=[
            FakeTelegramBotConfig("alpha", "tok-a", True),
            FakeTelegramBotConfig("beta", "tok-b", True),
            FakeTelegramBotConfig("gamma", None, True),
            FakeTelegramBotConfig("delta", "tok-d", False),
        ],
    )

    enabled = cfg.iter_enabled_bots()

    assert [bot.id for bot in enabled] == ["alpha", "beta"]
