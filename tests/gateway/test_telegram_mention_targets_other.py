"""Tests for ``_message_targets_other_entity`` gating (multi-bot per-bot mention filter).

When a bot has ``require_mention=False`` it would historically respond to
every group message.  In multi-bot deployments this causes the permissive
bot (e.g. the user's main assistant) to "steal" messages that are clearly
addressed to another bot via ``@other_bot`` or ``@username``.  The helper
:meth:`TelegramAdapter._message_targets_other_entity` reports whether a
message explicitly names someone other than this adapter's bot; the gate
then blocks even when ``require_mention=False``.
"""
from types import SimpleNamespace

from gateway.config import Platform, PlatformConfig
from gateway.platforms.telegram import TelegramAdapter


def _make_adapter(require_mention=False):
    adapter = object.__new__(TelegramAdapter)
    adapter.platform = Platform.TELEGRAM
    adapter.config = PlatformConfig(
        enabled=True,
        token="***",
        extra={"require_mention": require_mention},
    )
    adapter._bot = SimpleNamespace(id=999, username="hermes_bot")
    adapter._mention_patterns = []
    return adapter


def _mention_entity(text, mention):
    offset = text.index(mention)
    return SimpleNamespace(type="mention", offset=offset, length=len(mention))


def _text_mention_entity(offset, length, user_id):
    return SimpleNamespace(
        type="text_mention",
        offset=offset,
        length=length,
        user=SimpleNamespace(id=user_id),
    )


def _message(text=None, caption=None, entities=None, caption_entities=None):
    return SimpleNamespace(
        text=text,
        caption=caption,
        entities=entities or [],
        caption_entities=caption_entities or [],
        message_thread_id=None,
        chat=SimpleNamespace(id=-100, type="group"),
        reply_to_message=None,
    )


# ── _message_targets_other_entity direct tests ────────────────────────

class TestTargetsOtherEntity:
    """Unit tests for the helper, independent of the full gate."""

    def test_no_mentions_returns_false(self):
        adapter = _make_adapter()
        msg = _message(text="hello world")
        assert adapter._message_targets_other_entity(msg) is False

    def test_mention_of_self_returns_false(self):
        adapter = _make_adapter()
        text = "@hermes_bot please help"
        msg = _message(text=text, entities=[_mention_entity(text, "@hermes_bot")])
        assert adapter._message_targets_other_entity(msg) is False

    def test_mention_of_another_bot_returns_true(self):
        adapter = _make_adapter()
        text = "@other_bot test this"
        msg = _message(text=text, entities=[_mention_entity(text, "@other_bot")])
        assert adapter._message_targets_other_entity(msg) is True

    def test_mention_of_another_user_returns_true(self):
        adapter = _make_adapter()
        text = "@alice take a look"
        msg = _message(text=text, entities=[_mention_entity(text, "@alice")])
        assert adapter._message_targets_other_entity(msg) is True

    def test_text_mention_of_self_returns_false(self):
        adapter = _make_adapter()
        text = "hey you"
        msg = _message(text=text, entities=[_text_mention_entity(0, 3, 999)])
        assert adapter._message_targets_other_entity(msg) is False

    def test_text_mention_of_other_user_returns_true(self):
        adapter = _make_adapter()
        text = "hey you"
        msg = _message(text=text, entities=[_text_mention_entity(0, 3, 7777)])
        assert adapter._message_targets_other_entity(msg) is True

    def test_mention_in_caption_works(self):
        adapter = _make_adapter()
        caption = "cc @other_bot"
        msg = _message(caption=caption, caption_entities=[_mention_entity(caption, "@other_bot")])
        assert adapter._message_targets_other_entity(msg) is True

    def test_bare_at_without_entity_is_ignored(self):
        """A literal ``@foo`` substring without a MENTION entity is not a mention."""
        adapter = _make_adapter()
        msg = _message(text="email me at foo@example.com")
        assert adapter._message_targets_other_entity(msg) is False

    def test_mixed_self_and_other_returns_true(self):
        """When the message mentions both self and another, it still "targets other"."""
        adapter = _make_adapter()
        text = "@hermes_bot please ping @other_bot"
        msg = _message(
            text=text,
            entities=[
                _mention_entity(text, "@hermes_bot"),
                _mention_entity(text, "@other_bot"),
            ],
        )
        assert adapter._message_targets_other_entity(msg) is True

    def test_empty_entity_is_ignored(self):
        adapter = _make_adapter()
        msg = _message(
            text="something",
            entities=[SimpleNamespace(type="mention", offset=-1, length=0)],
        )
        assert adapter._message_targets_other_entity(msg) is False


# ── _should_process_message integration with require_mention=False ────

class TestRequireMentionFalseWithOtherTarget:
    """A ``require_mention=False`` bot must NOT respond when the message
    explicitly addresses a different bot/user."""

    def test_free_chat_with_no_mentions_still_processes(self):
        adapter = _make_adapter(require_mention=False)
        msg = _message(text="hello everyone")
        assert adapter._should_process_message(msg) is True

    def test_blocks_when_other_bot_is_mentioned(self):
        adapter = _make_adapter(require_mention=False)
        text = "@other_bot please run the task"
        msg = _message(text=text, entities=[_mention_entity(text, "@other_bot")])
        assert adapter._should_process_message(msg) is False

    def test_still_processes_when_self_mentioned(self):
        adapter = _make_adapter(require_mention=False)
        text = "@hermes_bot you handle it"
        msg = _message(text=text, entities=[_mention_entity(text, "@hermes_bot")])
        assert adapter._should_process_message(msg) is True


class TestRequireMentionTrueUnchanged:
    """Bots with ``require_mention=True`` keep their original behaviour —
    the new helper never weakens the strict gate."""

    def test_blocks_plain_message(self):
        adapter = _make_adapter(require_mention=True)
        msg = _message(text="hello everyone")
        assert adapter._should_process_message(msg) is False

    def test_passes_on_self_mention(self):
        adapter = _make_adapter(require_mention=True)
        text = "@hermes_bot help"
        msg = _message(text=text, entities=[_mention_entity(text, "@hermes_bot")])
        assert adapter._should_process_message(msg) is True

    def test_blocks_on_other_mention(self):
        adapter = _make_adapter(require_mention=True)
        text = "@other_bot do a thing"
        msg = _message(text=text, entities=[_mention_entity(text, "@other_bot")])
        assert adapter._should_process_message(msg) is False
