from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.platforms.base import MessageEvent, MessageType
from plugins.platforms.telegram.adapter import TelegramAdapter


class _StubRunner:
    def __init__(self, decision):
        self._decision = decision

    async def run_message_preprocess_hooks(self, context):
        return self._decision(context) if callable(self._decision) else self._decision


def _make_adapter(decision):
    cfg = SimpleNamespace(extra={})
    adapter = TelegramAdapter(cfg)
    adapter._message_handler = SimpleNamespace(__self__=_StubRunner(decision))
    adapter._bot = SimpleNamespace(id=42, username="qoala2_bot")
    adapter.handle_message = AsyncMock()
    adapter._enqueue_text_event = AsyncMock()
    adapter._should_process_message = lambda *_a, **_kw: True
    adapter._apply_telegram_group_observe_attribution = lambda event: event
    adapter._ensure_forum_commands = AsyncMock()
    return adapter


def _make_message(text="hello", *, is_bot=False, reply_to_bot=False):
    from_user = SimpleNamespace(id=100, is_bot=is_bot, username="sender_bot" if is_bot else "arkhi", full_name="Arkhi")
    reply_user = SimpleNamespace(id=42) if reply_to_bot else None
    reply_to_message = SimpleNamespace(message_id=9, text="prior", from_user=reply_user) if reply_to_bot else None
    chat = SimpleNamespace(id=-1001, type="supergroup", title="War Room", is_forum=False)
    return SimpleNamespace(
        text=text,
        caption=None,
        chat=chat,
        from_user=from_user,
        sender_chat=None,
        message_id=77,
        message_thread_id=None,
        is_topic_message=False,
        date=None,
        entities=[],
        caption_entities=[],
        reply_to_message=reply_to_message,
        quote=None,
    )


def _make_update(message):
    return SimpleNamespace(message=message, effective_message=message, update_id=555)


@pytest.mark.asyncio
async def test_apply_preprocess_hook_rewrites_text():
    adapter = _make_adapter({"action": "rewrite", "message": "[at]qoala2_bot halo"})
    msg = _make_message("hello")
    event = MessageEvent(
        text="hello",
        message_type=MessageType.TEXT,
        source=adapter.build_source(chat_id="-1001", chat_name="War Room", chat_type="group", user_id="100", user_name="Arkhi", thread_id=None, chat_topic=None, message_id="77"),
    )

    patched = await adapter._apply_preprocess_hook(event, msg)

    assert patched is not None
    assert patched.text == "[at]qoala2_bot halo"


@pytest.mark.asyncio
async def test_apply_preprocess_hook_ignores_bot_origin_message():
    adapter = _make_adapter(lambda ctx: {"action": "ignore", "reason": "bot-origin"} if ctx["from_user_is_bot"] else {"action": "allow"})
    msg = _make_message("hello", is_bot=True)
    event = MessageEvent(
        text="hello",
        message_type=MessageType.TEXT,
        source=adapter.build_source(chat_id="-1001", chat_name="War Room", chat_type="group", user_id="100", user_name="Arkhi", thread_id=None, chat_topic=None, message_id="77"),
    )

    patched = await adapter._apply_preprocess_hook(event, msg)

    assert patched is None


@pytest.mark.asyncio
async def test_preprocess_context_preserves_bot_origin_and_reply_metadata():
    adapter = _make_adapter({"action": "allow"})
    msg = _make_message("[at]qoala2_bot halo", is_bot=True, reply_to_bot=True)
    event = MessageEvent(
        text="[at]qoala2_bot halo",
        message_type=MessageType.TEXT,
        source=adapter.build_source(chat_id="-1001", chat_name="War Room", chat_type="group", user_id="100", user_name="Arkhi", thread_id="123", chat_topic=None, message_id="77"),
    )

    ctx = adapter._telegram_preprocess_context(event, msg)

    assert ctx["platform"] == "telegram"
    assert ctx["chat_type"] == "group"
    assert ctx["thread_id"] == "123"
    assert ctx["message"] == "[at]qoala2_bot halo"
    assert ctx["from_user_is_bot"] is True
    assert ctx["from_bot_username"] == "sender_bot"
    assert ctx["is_reply_to_bot"] is True
