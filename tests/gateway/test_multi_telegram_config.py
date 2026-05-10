"""Tests for Telegram multi-bot config bridging and env overrides."""

from gateway.config import (
    GatewayConfig,
    Platform,
    TelegramBotConfig,
    TelegramPlatformConfig,
    _apply_env_overrides,
    load_gateway_config,
)


def test_gateway_config_from_dict_uses_telegram_platform_config_for_platforms_section():
    config = GatewayConfig.from_dict(
        {
            "platforms": {
                "telegram": {
                    "enabled": True,
                    "bots": [
                        {"id": "alpha", "token": "tok-alpha", "enabled": True},
                        {"id": "beta", "token": "tok-beta", "enabled": True},
                    ],
                }
            }
        }
    )

    telegram_cfg = config.platforms[Platform.TELEGRAM]

    assert isinstance(telegram_cfg, TelegramPlatformConfig)
    assert [bot.id for bot in telegram_cfg.iter_enabled_bots()] == ["alpha", "beta"]


def test_telegram_platform_config_from_dict_bridges_legacy_single_bot_shape():
    cfg = TelegramPlatformConfig.from_dict(
        {
            "enabled": True,
            "token": "tok-legacy",
            "reply_to_mode": "all",
            "extra": {"require_mention": True},
        }
    )

    assert len(cfg.bots) == 1
    assert cfg.bots[0].id == "default"
    assert cfg.bots[0].token == "tok-legacy"
    assert cfg.bots[0].reply_to_mode == "all"
    assert cfg.bots[0].extra["require_mention"] is True


def test_apply_env_overrides_loads_telegram_bots_json(monkeypatch):
    config = GatewayConfig()
    monkeypatch.setenv(
        "TELEGRAM_BOTS_JSON",
        '[{"id":"alpha","token":"tok-a"},{"id":"beta","token":"tok-b","enabled":true}]',
    )
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_HOME_CHANNEL", raising=False)
    monkeypatch.delenv("TELEGRAM_REPLY_TO_MODE", raising=False)

    _apply_env_overrides(config)

    telegram_cfg = config.platforms[Platform.TELEGRAM]
    assert isinstance(telegram_cfg, TelegramPlatformConfig)
    assert [bot.id for bot in telegram_cfg.bots] == ["alpha", "beta"]
    assert [bot.id for bot in telegram_cfg.iter_enabled_bots()] == ["alpha", "beta"]


def test_apply_env_overrides_patches_default_bot_without_overwriting_explicit_bots(monkeypatch):
    config = GatewayConfig(
        platforms={
            Platform.TELEGRAM: TelegramPlatformConfig(
                enabled=True,
                bots=[TelegramBotConfig(id="alpha", token="tok-a", enabled=True)],
            )
        }
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok-default")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "-100555")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL_NAME", "Ops")
    monkeypatch.setenv("TELEGRAM_REPLY_TO_MODE", "all")
    monkeypatch.delenv("TELEGRAM_BOTS_JSON", raising=False)

    _apply_env_overrides(config)

    telegram_cfg = config.platforms[Platform.TELEGRAM]
    assert isinstance(telegram_cfg, TelegramPlatformConfig)
    assert [bot.id for bot in telegram_cfg.bots] == ["alpha", "default"]
    default_bot = next(bot for bot in telegram_cfg.bots if bot.id == "default")
    alpha_bot = next(bot for bot in telegram_cfg.bots if bot.id == "alpha")
    assert default_bot.token == "tok-default"
    assert default_bot.home_channel is not None
    assert default_bot.home_channel.chat_id == "-100555"
    assert default_bot.reply_to_mode == "all"
    assert alpha_bot.token == "tok-a"


def test_load_gateway_config_bridges_legacy_telegram_yaml_to_platform_bots(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "telegram:\n"
        "  enabled: true\n"
        "  token: tok-legacy\n"
        "  reply_to_mode: all\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOTS_JSON", raising=False)
    monkeypatch.delenv("TELEGRAM_HOME_CHANNEL", raising=False)
    monkeypatch.delenv("TELEGRAM_REPLY_TO_MODE", raising=False)

    config = load_gateway_config()

    telegram_cfg = config.platforms[Platform.TELEGRAM]
    assert isinstance(telegram_cfg, TelegramPlatformConfig)
    assert telegram_cfg.enabled is True
    assert [bot.id for bot in telegram_cfg.bots] == ["default"]
    assert telegram_cfg.bots[0].token == "tok-legacy"
    assert telegram_cfg.bots[0].reply_to_mode == "all"
