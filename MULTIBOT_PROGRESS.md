# Hermes Multi-Bot Runtime Progress

## Current phase
- Phase 1: bot_instance_id foundation — mostly complete
- Phase 2: bot-aware runtime/model resolution — in progress
- Phase 2.5: regression baseline + progress isolation — started
- Phase 3: memory/tool/secret/observability isolation — not started

## Completed
- `gateway/config.py`: Telegram multi-bot config, default-bot env bridge, `iter_enabled_bots()`
- `gateway/session.py`: session key namespace upgraded to `agent:<bot_instance_id>:...`
- `gateway/delivery.py`: delivery target carries `bot_instance_id`; adapter selection is bot-aware
- `gateway/platforms/base.py`: `build_source()` inherits adapter bot identity by default
- `gateway/platforms/telegram.py`: adapter accepts `bot_instance_id`
- `gateway/run.py`: adapter fan-out for Telegram bots, bot-aware runtime/model resolution wiring, session env bot propagation
- `gateway/session_context.py`: `HERMES_SESSION_BOT_INSTANCE_ID` context propagation
- `gateway/platforms/feishu_comment.py`: source-aware model resolution from comment session key
- `gateway/platforms/api_server.py`: source-aware model resolution from `gateway_session_key`
- `gateway/run.py::_schedule_resume_pending_sessions()`: now resolves adapters through `_adapter_for_source(source)` so restart auto-resume is bot-aware
- `gateway/run.py` reconnect/failure queue: failed adapters are now tracked with instance-aware keys (`telegram/<bot_id>`) while remaining compatible with legacy platform-only keys
- `gateway/run.py` reconnect watcher: recreates sibling adapters with `instance_id`, re-registers them via `_register_adapter()`, and updates delivery/router sibling state
- `gateway/run.py` hot-path pending/busy routing: `_queue_or_replace_pending_event()`, drain-busy ack, normal busy ack, `/queue`, `/steer` fallbacks, and photo follow-up queueing all resolve adapters via `_adapter_for_source(source)` instead of platform-primary lookup
- `gateway/run.py` notice / pairing delivery: `_deliver_platform_notice()` and unauthorized DM pairing replies now route through bot-specific adapters when `source.bot_instance_id` is present
- `gateway/run.py` voice mode persistence: voice keys now support bot-aware namespacing (`telegram/<bot_id>:<chat_id>`) so sibling bots do not collide on `/voice` state
- Regression coverage added for:
  - `tests/gateway/test_multibot_runtime_resolution.py`
  - `tests/gateway/test_session_context_multibot.py`
  - `tests/gateway/test_feishu_comment.py` bot-source case
  - `tests/gateway/test_api_server_toolset.py` bot-source case
  - `tests/gateway/test_restart_resume_pending.py` bot-specific auto-resume case
  - `tests/gateway/test_platform_reconnect.py` bot-specific reconnect case
  - `tests/gateway/test_voice_command.py` bot-specific `/voice` adapter/key isolation case
  - `tests/gateway/test_busy_session_ack.py` bot-specific busy/drain ack adapter isolation cases
  - `tests/gateway/test_notice_delivery.py` bot-specific notice adapter routing case
- Fixed suite entrypoint: `scripts/multibot-suite.sh`

## Remaining P0
- `gateway/run.py::_schedule_resume_pending_sessions()` replace platform-only adapter lookup with bot-aware adapter lookup
- Main runtime in-memory state bucketization:
  - `running_agents`
  - `inflight`
  - `dedupe`
  - lock keys
- Verify remaining `_resolve_gateway_model(..., source=...)` call sites across non-Telegram platforms

## Remaining P1
- Stabilize a single canonical multibot regression suite
- Expand restart/recovery tests for multi-adapter same-platform cases
- Decide whether to upstream `topic_binding` candidate module into gateway proper

## Remaining P2
- bot-native memory namespace
- per-bot tool policy and secret scope
- shared/groups/bots skill mount policy
- per-bot observability and runtime metrics
- non-Telegram platform unification

## Fixed regression command
```bash
cd /opt/hermes-agent && HOME=/root pytest \
  tests/gateway/test_multibot_*.py \
  tests/gateway/test_session_context_multibot.py \
  tests/gateway/test_router.py \
  tests/gateway/test_registry.py \
  tests/gateway/test_restart_notification.py \
  tests/gateway/test_restart_resume_pending.py \
  tests/gateway/test_model_switch_persistence.py \
  tests/gateway/test_api_server_toolset.py \
  tests/gateway/test_feishu_comment.py \
  tests/test_topic_binding.py -q
```

## Latest verified status
- Previous main multibot batch: 111 passed
- Feishu comment regression after bot-source patch: 21 passed, 2 warnings
- Targeted restart/reconnect/source-aware batch: 124 passed, 2 warnings
- Targeted voice+restart+reconnect batch: 266 passed
- Targeted busy-ack + voice + restart + reconnect batch: 283 passed
- Targeted notice + busy-ack + voice + restart + reconnect batch: 287 passed
