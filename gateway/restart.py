"""Shared gateway restart constants and restart/recovery metadata helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from hermes_cli.config import DEFAULT_CONFIG

# EX_TEMPFAIL from sysexits.h — used to ask the service manager to restart
# the gateway after a graceful drain/reload path completes.
GATEWAY_SERVICE_RESTART_EXIT_CODE = 75

DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT = float(
    DEFAULT_CONFIG["agent"]["restart_drain_timeout"]
)


def parse_restart_drain_timeout(raw: object) -> float:
    """Parse a configured drain timeout, falling back to the shared default."""
    try:
        value = float(raw) if str(raw or "").strip() else DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT
    except (TypeError, ValueError):
        return DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT
    return max(0.0, value)


def normalize_bot_instance_id(raw: object) -> Optional[str]:
    """Normalize persisted/runtime bot IDs so restart metadata compares consistently."""
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def build_restart_target_payload(
    *,
    platform: object,
    chat_id: object,
    thread_id: object = None,
    bot_instance_id: object = None,
    requested_at: object = None,
    update_id: object = None,
) -> dict[str, Any]:
    """Build restart/recovery routing metadata with normalized bot identity."""
    payload: dict[str, Any] = {
        "platform": getattr(platform, "value", platform),
        "chat_id": chat_id,
    }
    if thread_id:
        payload["thread_id"] = thread_id
    normalized_bot_instance_id = normalize_bot_instance_id(bot_instance_id)
    if normalized_bot_instance_id:
        payload["bot_instance_id"] = normalized_bot_instance_id
    if requested_at is not None:
        payload["requested_at"] = requested_at
    if update_id is not None:
        payload["update_id"] = update_id
    return payload


def load_restart_target_payload(path: Path) -> Optional[dict[str, Any]]:
    """Read persisted restart/recovery metadata, normalizing bot identity if present."""
    try:
        data = json.loads(path.read_text())
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    normalized_bot_instance_id = normalize_bot_instance_id(data.get("bot_instance_id"))
    if normalized_bot_instance_id:
        data["bot_instance_id"] = normalized_bot_instance_id
    else:
        data.pop("bot_instance_id", None)
    return data
