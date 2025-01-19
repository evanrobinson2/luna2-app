"""
luna_message_handler3.py

Example usage of the new command router + help command in a simplified
Matrix event handler for text messages.
"""

import random
import asyncio
import logging
from luna.context_helper import build_context
from luna import bot_messages_store
from luna.ai_functions import get_gpt_response
import time
from nio import (
    AsyncClient,
    RoomMessageText,
    RoomSendResponse,
)

from luna.luna_command_extensions.command_router import handle_console_command

logger = logging.getLogger(__name__)
BOT_START_TIME = time.time() * 1000

async def handle_luna_message3(bot_client: AsyncClient, bot_localpart: str, room, event):
    """
    A new message handler that:
      - Ignores messages from itself
      - Checks if message starts with '!' => route to handle_console_command
      - Otherwise, do a fallback (like echo or GPT).
      - Sends typing indicators for realism.
    """

    # do not respond to messages from the past, under any circumstances
    if event.server_timestamp < BOT_START_TIME:
        logger.debug("Skipping old event => %s", event.event_id)
        return

    bot_full_id = bot_client.user

    # 1) Ignore messages from itself
    if event.sender == bot_full_id:
        logger.debug("Ignoring message from myself: %s", event.sender)
        return

    # 2) Check if it's a text message
    if not isinstance(event, RoomMessageText):
        logger.debug("Ignoring non-text message.")
        return

    message_body = event.body or ""
    logger.info("Received message in room=%s from=%s => %r", room.room_id, event.sender, message_body)

    # e.g. after verifying not from ourselves, and that it's text
    bot_messages_store.append_message(
        bot_localpart=bot_localpart,
        room_id=room.room_id,
        event_id=event.event_id,
        sender=event.sender,
        timestamp=event.server_timestamp,
        body=message_body
    )

    # 5) Start typing indicator
    try:
        await bot_client.room_typing(room.room_id, True, timeout=5000)
        logger.info("Sent 'typing start' indicator.")
    except Exception as e:
        logger.warning("Could not send 'typing start' indicator => %s", e)

    await asyncio.sleep(0.5) # wait at least a half a second to respond

    # 6) If it starts with "!", treat it as a command
    if message_body.startswith("!"):
        # dispatch to console_command
        reply_text = await handle_console_command(
            bot_client,
            room.room_id,
            message_body,
            event.sender
        )
        # Some commands (like !help) return HTML. Let's send it as formatted text.
        if reply_text.strip().startswith("<table") or "<table" in reply_text:
            await send_formatted_text(bot_client, room.room_id, reply_text)
        else:
            # fallback plain text
            await send_text(bot_client, room.room_id, reply_text)
    else:
        # Fallback path (e.g., echo or GPT)
        # 4) Random delay to mimic "typing"
        await asyncio.sleep(random.uniform(0.5, 2.0))

        # Regular message: send GPT response in plain text
        gpt_reply = await _call_gpt(bot_localpart, room.room_id, message_body)
        await send_text(bot_client, room.room_id, gpt_reply)

    # 7) Stop typing indicator
    try:
        await bot_client.room_typing(room.room_id, False, timeout=0)
        logger.info("Sent 'typing stop' indicator.")
    except Exception as e:
        logger.warning("Could not send 'typing stop' indicator => %s", e)


async def send_text(bot_client: AsyncClient, room_id: str, text: str):
    """Send a plain text message (no HTML formatting)."""
    content = {
        "msgtype": "m.text",
        "body": text,
    }
    resp = await bot_client.room_send(
        room_id=room_id,
        message_type="m.room.message",
        content=content,
    )
    if isinstance(resp, RoomSendResponse):
        logger.info(f"Sent text => event_id={resp.event_id}")
    else:
        logger.warning(f"Failed to send text => {resp}")


async def send_formatted_text(bot_client: AsyncClient, room_id: str, html_content: str):
    """
    Send an HTML-formatted message with a plain-text fallback.
    """
    # For fallback, just strip tags (naive approach).
    fallback_text = remove_html_tags(html_content)

    content = {
        "msgtype": "m.text",
        "body": fallback_text,
        "format": "org.matrix.custom.html",
        "formatted_body": html_content
    }
    resp = await bot_client.room_send(
        room_id=room_id,
        message_type="m.room.message",
        content=content,
    )
    if isinstance(resp, RoomSendResponse):
        logger.info(f"Sent formatted text => event_id={resp.event_id}")
    else:
        logger.warning(f"Failed to send formatted text => {resp}")


def remove_html_tags(html: str) -> str:
    """Minimal HTML tag remover for fallback body."""
    import re
    return re.sub(r'<[^>]+>', '', html).strip()

async def _call_gpt(bot_localpart: str, room_id: str, user_message: str) -> str:
    """
    Build context (including system prompt) + user message => GPT call.
    Returns the text reply from GPT.
    """
    logger.debug("_call_gpt => building context for localpart=%s, room_id=%s", bot_localpart, room_id)
    context_config = {"max_history": 10}
    gpt_context = build_context(bot_localpart, room_id, context_config)

    # Append the new user message
    gpt_context.append({"role": "user", "content": user_message})

    logger.debug("GPT context => %s", gpt_context)
    reply = await get_gpt_response(
        messages=gpt_context,
        model="chatgpt-4o-latest",
        temperature=0.7,
        max_tokens=300
    )
    return reply
