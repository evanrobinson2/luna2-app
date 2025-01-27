"""
create_and_login_bot.py

Handles creating a new bot persona record + user account + ephemeral login,
THEN registers event handlers & spawns the bot's sync loop.
"""

import logging
from typing import Dict, Any
import asyncio
import re
import secrets  # for fallback random localpart (if needed)

from nio import RoomMessageText, InviteMemberEvent, RoomMemberEvent, AsyncClient

# Adjust these imports to match your new layout:
import luna.luna_personas
from luna.luna_functions import (
    create_user,
    load_or_login_client_v2
)
from luna.luna_command_extensions.bot_message_handler import handle_bot_room_message
from luna.luna_command_extensions.bot_member_event_handler import handle_bot_member_event
from luna.luna_command_extensions.bot_invite_handler import handle_bot_invite

logger = logging.getLogger(__name__)

# Regex that matches valid characters for localparts in Matrix user IDs:
# (Synapse typically allows `[a-z0-9._=/-]+` by default).
VALID_LOCALPART_REGEX = re.compile(r'[a-z0-9._=\-/]+')

async def create_and_login_bot(
    bot_id: str,
    password: str,
    displayname: str,
    system_prompt: str,
    traits: dict,
    creator_user_id: str = "@lunabot:localhost",
    is_admin: bool = False
) -> Dict[str, Any]:
    """
    1) Creates a local persona entry in personalities.json (using bot_id as the key).
    2) Calls create_user(...) to register with Synapse.
    3) Performs ephemeral login (load_or_login_client_v2) => returns an AsyncClient for that user.
    4) Registers event handlers, spawns the bot’s sync loop.
    5) Stores references (AsyncClient + sync task) in the global BOTS/TASKS.
    
    Returns a dictionary with:
        {
          "ok": bool,             # True if successful, False if any step failed
          "bot_id": str or None,  # final sanitized bot ID (e.g. "@teenage_ninja:localhost")
          "client": AsyncClient or None,
          "html": str or None,    # success or error message in HTML form
          "error": str or None    # plain-text error if something failed
        }
    """

    logger.debug("[create_and_login_bot] Called with bot_id=%r, displayname=%r", bot_id, displayname)

    # 1) Validate & parse localpart
    if not bot_id.startswith("@") or ":" not in bot_id:
        err = f"[create_and_login_bot] Invalid bot_id => {bot_id}"
        logger.warning(err)
        return {
            "ok": False,
            "bot_id": None,
            "client": None,
            "html": f"<p>{err}</p>",
            "error": err
        }

    original_localpart = bot_id.split(":")[0].replace("@", "", 1)
    logger.debug("Original localpart extracted => %r", original_localpart)

    # 2) Sanitize localpart
    tmp = original_localpart.lower()
    sanitized = "".join(ch for ch in tmp if VALID_LOCALPART_REGEX.match(ch))
    if not sanitized:
        random_suffix = secrets.token_hex(4)
        sanitized = f"bot_{random_suffix}"
        logger.debug("Localpart was invalid, using fallback => %r", sanitized)
    elif sanitized != original_localpart.lower():
        logger.debug("Sanitized localpart from %r to %r", original_localpart, sanitized)

    new_bot_id = f"@{sanitized}:localhost"
    logger.debug("Final bot_id => %r", new_bot_id)
    bot_id = new_bot_id

    # 3) Create persona in personalities.json
    try:
        logger.debug("Creating persona in personalities.json => %r", bot_id)
        luna.luna_personas.create_bot(
            bot_id=bot_id,
            password=password,
            displayname=displayname,
            creator_user_id=creator_user_id,
            system_prompt=system_prompt,
            traits=traits
        )
        logger.info("[create_and_login_bot] Persona created for %s.", bot_id)
    except Exception as e:
        msg = f"[create_and_login_bot] Could not create persona => {e}"
        logger.exception(msg)
        return {
            "ok": False,
            "bot_id": None,
            "client": None,
            "html": f"<p>{msg}</p>",
            "error": str(e)
        }

    # 4) Create the user in Synapse
    matrix_localpart = sanitized
    logger.debug("Attempting create_user(localpart=%r)", matrix_localpart)
    creation_msg = await create_user(matrix_localpart, password, is_admin=is_admin)
    if not creation_msg.startswith("Created user"):
        err = f"[create_and_login_bot] Synapse user creation failed => {creation_msg}"
        logger.error(err)
        return {
            "ok": False,
            "bot_id": None,
            "client": None,
            "html": f"<p>{err}</p>",
            "error": creation_msg
        }

    # 5) Ephemeral login
    try:
        logger.debug("Attempting ephemeral login => bot_id=%r", bot_id)
        client = await load_or_login_client_v2(
            homeserver_url="http://localhost:8008",
            user_id=bot_id,
            password=password,
            device_name=f"{sanitized}_device"
        )
        logger.info("[create_and_login_bot] Ephemeral login success => %s", bot_id)
    except Exception as e:
        err = f"[create_and_login_bot] Ephemeral login failed => {e}"
        logger.exception(err)
        return {
            "ok": False,
            "bot_id": None,
            "client": None,
            "html": f"<p>{err}</p>",
            "error": str(e)
        }

    # 6) Register event callbacks
    try:
        client.add_event_callback(
            lambda room, evt: handle_bot_room_message(client, sanitized, room, evt),
            RoomMessageText
        )
        client.add_event_callback(
            lambda room, evt: handle_bot_invite(client, sanitized, room, evt),
            InviteMemberEvent
        )
        client.add_event_callback(
            lambda room, evt: handle_bot_member_event(client, sanitized, room, evt),
            RoomMemberEvent
        )
        logger.info("[create_and_login_bot] Registered event handlers for '%s'.", sanitized)
    except Exception as e:
        err = f"[create_and_login_bot] Error registering event callbacks => {e}"
        logger.exception(err)
        return {
            "ok": False,
            "bot_id": bot_id,
            "client": client,
            "html": f"<p>{err}</p>",
            "error": str(e)
        }

    # 7) Start the sync loop & store references
    try:
        from luna.core import BOTS, BOT_TASKS, run_bot_sync
        BOTS[sanitized] = client
        sync_task = asyncio.create_task(run_bot_sync(client, sanitized))
        BOT_TASKS.append(sync_task)
        logger.info("[create_and_login_bot] Bot '%s' sync loop started.", sanitized)

    except Exception as e:
        err = f"[create_and_login_bot] Could not start sync => {e}"
        logger.exception(err)
        return {
            "ok": False,
            "bot_id": bot_id,
            "client": client,
            "html": f"<p>{err}</p>",
            "error": str(e)
        }

    # 8) Final success
    success_msg = f"Successfully created & logged in => {bot_id}"
    logger.info(success_msg)
    return {
        "ok": True,
        "bot_id": bot_id,         # final sanitized bot ID
        "client": client,         # ephemeral bot client
        "html": f"<p>{success_msg}</p>",
        "error": None
    }
