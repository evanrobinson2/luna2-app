"""
luna_message_handler5.py

Admin-only behavior, but now GPT fallback is interpreted as Markdown and sent
via 'org.matrix.custom.html', so it can render bold/italics/etc. in the client.

We have updated this version so that role-play channel responses are posted
in a thread (using "m.relates_to": { "rel_type": "m.thread", ... }). DM behavior
remains unchanged, posting in the main timeline.
"""

import time
import logging
import random
import asyncio
import time
import logging
import markdown  # for converting GPT's string to HTML

from nio import (
    AsyncClient,
    RoomMessageText,
    RoomSendResponse,
    RoomCreateResponse
)

from luna.luna_command_extensions.command_router import handle_console_command
from luna.context_helper import build_context
from luna.ai_functions import get_gpt_response
from luna import bot_messages_store

logger = logging.getLogger(__name__)
BOT_START_TIME = time.time() * 1000

async def handle_luna_message5(bot_client: AsyncClient, bot_localpart: str, room, event: RoomMessageText):
    """
    1) Ignores old/self messages
    2) Must be text
    3) Saves inbound
    4) If DM (2 participants) => handle commands or GPT
       Else => role-play channel => commands => respond in-thread
    """
    message_body = event.body or ""
    logger.info("handle_luna_message5: room=%s from=%s => %r",
                room.room_id, event.sender, message_body)

    # 3) store inbound
    bot_messages_store.append_message(
        bot_localpart=bot_localpart,
        room_id=room.room_id,
        event_id=event.event_id,
        sender=event.sender,
        timestamp=event.server_timestamp,
        body=message_body
    )

    # 1) ignore old / from self
    if event.server_timestamp < BOT_START_TIME:
        logger.debug("Ignoring old event => %s", event.event_id)
        return

    bot_full_id = bot_client.user
    if event.sender == bot_full_id:
        logger.debug("Ignoring message from myself: %s", event.sender)
        return

    # 2) Must be text
    if not isinstance(event, RoomMessageText):
        logger.debug("Ignoring non-text event => %s", event.type)
        return

    # 4) DM vs. role-play channel
    participant_count = len(room.users)
    if participant_count == 2:
        await _handle_dm_channel(bot_client, bot_localpart, room, event, message_body)
    else:
        await _handle_roleplay_channel(bot_client, bot_localpart, room, event, message_body)


async def _handle_dm_channel(bot_client, bot_localpart, room, event, message_body):
    """
    2-participant DM:
      - If command => handle, respond in same room (main timeline)
      - Else => GPT fallback => interpret as Markdown
      - No thread usage here, unchanged from previous logic.
    """
    await _start_typing(bot_client, room.room_id)

    if message_body.startswith("!"):
        # commands
        reply_text = await handle_console_command(bot_client, room.room_id, message_body, event.sender, event)

        if "<table" in (reply_text or ""):
            # Possibly HTML from e.g. !help
            await send_formatted_text(bot_client, room.room_id, reply_text)
        else:
            await send_text(bot_client, room.room_id, reply_text)

    else:
        # GPT fallback => interpret as Markdown
        await asyncio.sleep(random.uniform(0.5, 2.0))
        gpt_reply = await _call_gpt(bot_localpart, room.room_id, message_body)

        # Convert GPT’s string from Markdown => HTML
        # (If GPT doesn't use markdown, it still renders fine.)
        reply_html = markdown.markdown(gpt_reply, extensions=["extra", "sane_lists"])
        # Then post it with formatted_text
        await send_formatted_text(bot_client, room.room_id, reply_html)
    
    await bot_client.sync(timeout=500)
    
    await _stop_typing(bot_client, room.room_id)


async def _handle_roleplay_channel(bot_client, bot_localpart, room, event, message_body):
    """
    If 3+ participants => role-play context:
      - Only respond to commands => respond in a thread referencing the user’s event
      - Tag each response with context_cue="SYSTEM RESPONSE"
    """
    # 1) If the message does NOT start with '!', ignore
    if not message_body.startswith("!"):
        logger.debug("Ignoring non-command in role-play channel.")
        return

    # 2) Indicate typing
    await _start_typing(bot_client, room.room_id)

    try:
        # 3) Handle the console command
        command_reply = await handle_console_command(
            bot_client, 
            room.room_id, 
            message_body, 
            event.sender,
            event
        )

        if command_reply is not None:
            # 4) If the command output includes tables (<table>), we send HTML - in thread
            if "<table" in command_reply:
                await send_formatted_text_in_thread(
                    bot_client, 
                    room.room_id, 
                    event.event_id,           # parent's event_id
                    command_reply,
                    context_cue="SYSTEM RESPONSE"
                )
            else:
                await send_text_in_thread(
                    bot_client, 
                    room.room_id, 
                    event.event_id,
                    command_reply,
                    context_cue="SYSTEM RESPONSE"
                )

    finally:
        # 5) Stop typing no matter what
        await bot_client.sync(timeout=500) 
        await _stop_typing(bot_client, room.room_id)


async def _start_typing(bot_client: AsyncClient, room_id: str):
    try:
        await bot_client.room_typing(room_id, True, timeout=5000)
        logger.debug("Typing start => %s", room_id)
    except Exception as e:
        logger.warning("Could not send typing start => %s", e)

async def _stop_typing(bot_client: AsyncClient, room_id: str):
    try:
        await bot_client.room_typing(room_id, False, timeout=0)
        logger.debug("Typing stop => %s", room_id)
    except Exception as e:
        logger.warning("Could not send typing stop => %s", e)


async def _call_gpt(bot_localpart: str, room_id: str, user_message: str) -> str:
    context_config = {"max_history": 10}
    gpt_context = build_context(bot_localpart, room_id, context_config)
    gpt_context.append({"role": "user", "content": user_message})
    logger.debug("GPT context => %s", gpt_context)

    reply = await get_gpt_response(
        messages=gpt_context,
        model="gpt-4o",
        temperature=0.7,
        max_tokens=2000
    )
    return reply

# ---------------------------------------------------------------------
# Senders for main timeline
# ---------------------------------------------------------------------
async def send_text(bot_client: AsyncClient, room_id: str, text: str, context_cue: str = None):
    """
    Sends plain text to the main timeline. If `context_cue` is provided, we add it to the message content.
    """
    if text is None:
        return

    content = {
        "msgtype": "m.text",
        "body": text
    }
    if context_cue:
        content["context_cue"] = context_cue  # custom field

    resp = await bot_client.room_send(room_id, "m.room.message", content=content)
    if isinstance(resp, RoomSendResponse):
        logger.info("Sent text => event_id=%s in %s", resp.event_id, room_id)
    else:
        logger.warning("Failed to send text => %s", resp)


async def send_formatted_text(bot_client: AsyncClient, room_id: str, html_content: str, context_cue: str = None):
    """
    Sends HTML in 'formatted_body', with a stripped fallback in 'body'.
    This can handle any markdown->html or other markup.
    """
    if html_content is None:
        return

    fallback_text = remove_html_tags(html_content)
    content = {
        "msgtype": "m.text",
        "body": fallback_text,
        "format": "org.matrix.custom.html",
        "formatted_body": html_content
    }

    if context_cue:
        content["context_cue"] = context_cue  # custom field

    resp = await bot_client.room_send(room_id=room_id, message_type="m.room.message", content=content)
    if isinstance(resp, RoomSendResponse):
        logger.info("Sent formatted text => event_id=%s in %s", resp.event_id, room_id)
    else:
        logger.warning("Failed to send formatted text => %s", resp)

# ---------------------------------------------------------------------
# Senders for thread
# ---------------------------------------------------------------------
async def send_text_in_thread(bot_client: AsyncClient, room_id: str, parent_event_id: str, text: str, context_cue: str = None):
    """
    Sends plain text as a threaded reply to parent_event_id.
    """
    if text is None:
        return

    content = {
        "msgtype": "m.text",
        "body": text,
        "m.relates_to": {
            "rel_type": "m.thread",
            "event_id": parent_event_id
        }
    }

    if context_cue:
        content["context_cue"] = context_cue  # custom field

    resp = await bot_client.room_send(
        room_id=room_id,
        message_type="m.room.message",
        content=content
    )
    if isinstance(resp, RoomSendResponse):
        logger.info("Sent text in thread => event_id=%s in %s (parent=%s)",
                    resp.event_id, room_id, parent_event_id)
    else:
        logger.warning("Failed to send text in thread => %s", resp)


async def send_formatted_text_in_thread(bot_client: AsyncClient, room_id: str, parent_event_id: str, html_content: str, context_cue: str = None):
    """
    Sends HTML as a threaded reply to parent_event_id, with a stripped fallback in 'body'.
    """
    if html_content is None:
        return

    fallback_text = remove_html_tags(html_content)
    content = {
        "msgtype": "m.text",
        "body": fallback_text,
        "format": "org.matrix.custom.html",
        "formatted_body": html_content,
        "m.relates_to": {
            "rel_type": "m.thread",
            "event_id": parent_event_id
        }
    }

    if context_cue:
        content["context_cue"] = context_cue  # custom field

    resp = await bot_client.room_send(
        room_id=room_id,
        message_type="m.room.message",
        content=content
    )
    if isinstance(resp, RoomSendResponse):
        logger.info("Sent formatted text in thread => event_id=%s in %s (parent=%s)",
                    resp.event_id, room_id, parent_event_id)
    else:
        logger.warning("Failed to send formatted text in thread => %s", resp)


def remove_html_tags(text: str) -> str:
    import re
    return re.sub(r'<[^>]*>', '', text or "").strip()
