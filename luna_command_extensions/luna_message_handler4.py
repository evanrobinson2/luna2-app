"""
luna_message_handler4.py

Admin-only behavior, but now GPT fallback is interpreted as Markdown and sent
via 'org.matrix.custom.html', so it can render bold/italics/etc. in the client.
We assume there's no color code being injected – any mention highlighting is
still a client-side theme/notifications setting.
"""

import os
import time
import logging
import urllib.parse
import aiohttp
import random
import asyncio
import time
import logging
import re
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

async def handle_luna_message4(bot_client: AsyncClient, bot_localpart: str, room, event):
    """
    1) Ignores old/self messages
    2) Must be text
    3) Saves inbound
    4) If DM (2 participants) => handle commands or GPT
       Else => role-play channel => commands => respond by DM
    """
    message_body = event.body or ""
    logger.info("handle_luna_message4: room=%s from=%s => %r",
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
      - If command => handle, respond in same room
      - Else => GPT fallback => interpret as Markdown
    """
    await _start_typing(bot_client, room.room_id)

    if message_body.startswith("!"):
        # commands
        reply_text = await handle_console_command(bot_client, room.room_id, message_body, event.sender)

        if "<table" in reply_text:
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
      - Only respond to commands => respond right in the same room thread
      - Tag each response with "context_cue": "SYSTEM RESPONSE"
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
            event.sender
        )

        # 4) If the command output includes tables (<table>), we send HTML
        if "<table" in command_reply:
            await send_formatted_text(
                bot_client, 
                room.room_id, 
                command_reply,
                context_cue="SYSTEM RESPONSE"
            )
        else:
            await send_text(
                bot_client, 
                room.room_id, 
                command_reply,
                context_cue="SYSTEM RESPONSE"
            )

    finally:
        # 5) Stop typing no matter what
        await bot_client.sync(timeout=500) 
        await _stop_typing(bot_client, room.room_id)



# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
# @TODO delete this if it's truly not being used
async def _ensure_dm_room(bot_client: AsyncClient, user_id: str) -> str:
    for rid, room_obj in bot_client.rooms.items():
        if len(room_obj.users) == 2 and user_id in room_obj.users:
            logger.debug("Found existing DM => %s", rid)
            return rid

    # create if not found
    logger.debug("No existing DM => create for %s", user_id)
    try:
        resp = await bot_client.room_create(
            invite=[user_id],
            is_direct=True,
            name=f"DM_with_{user_id}"
        )
        if isinstance(resp, RoomCreateResponse):
            logger.info("Created DM => %s", resp.room_id)
            return resp.room_id
        else:
            logger.warning("room_create => %s", resp)
            return "!failedDM:localhost"
    except Exception as e:
        logger.exception("Error creating DM => %s", e)
        return "!failedDM:localhost"

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
        model="chatgpt-4o-latest",
        temperature=0.7,
        max_tokens=2000
    )
    return reply

# ---------------------------------------------------------------------
# Senders
# ---------------------------------------------------------------------
async def send_text(bot_client: AsyncClient, room_id: str, text: str, context_cue: str = None):
    """
    Sends plain text. If `context_cue` is provided, we add it to the message content.
    """
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

def remove_html_tags(text: str) -> str:
    import re
    return re.sub(r'<[^>]*>', '', text or "").strip()

