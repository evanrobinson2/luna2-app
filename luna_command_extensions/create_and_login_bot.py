"""
create_and_login_bot.py

Handles creating a new bot persona record + user account + ephemeral login,
THEN registers event handlers & spawns the bot's sync loop.
"""

import logging
import asyncio
import re
import secrets  # for fallback random localpart (if needed)

from nio import RoomMessageText, InviteMemberEvent, RoomMemberEvent

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
) -> str:
    """
    1) Creates a local persona entry in personalities.json (using bot_id as key).
    2) Calls create_user(...) to register with Synapse.
    3) Does ephemeral login (load_or_login_client_v2).
    4) Registers event handlers, spawns the bot’s sync loop.
    5) Stores references (AsyncClient + sync task) in the globals BOTS and BOT_TASKS.

    :param bot_id: Full Matrix user ID, e.g. "@spiderbot:localhost".
    :param password:  The password for the new bot.
    :param displayname: The user-friendly name for the bot.
    :param system_prompt: GPT system instructions or persona description.
    :param traits:    A dictionary of arbitrary trait key-values (e.g. theme, power).
    :param creator_user_id: Who “spawned” this bot. Default is @lunabot:localhost.
    :param is_admin:  Whether to create an admin user in Synapse. Defaults False.
    :return:          Success or error string (unchanged).
    """

    logger.debug("[create_and_login_bot] Called with bot_id=%r, displayname=%r", bot_id, displayname)

    # ------------------------------------------------------------------
    # 1) Validate & parse localpart
    # ------------------------------------------------------------------
    if not bot_id.startswith("@") or ":" not in bot_id:
        err = f"[create_and_login_bot] Invalid bot_id => {bot_id}"
        logger.warning(err)
        return err

    # Example: bot_id="@myGuy!:localhost"
    # localpart => "myGuy!"
    original_localpart = bot_id.split(":")[0].replace("@", "", 1)
    logger.debug("Original localpart extracted => %r", original_localpart)

    # ------------------------------------------------------------------
    # 2) Sanitize the localpart
    # ------------------------------------------------------------------
    # Convert to lowercase for consistency
    tmp = original_localpart.lower()
    # Keep only valid characters
    sanitized = "".join(ch for ch in tmp if VALID_LOCALPART_REGEX.match(ch))

    # If sanitized ends up empty, fallback to random
    if not sanitized:
        # e.g. "bot_" + short random suffix
        random_suffix = secrets.token_hex(4)  # e.g. "a1b2"
        sanitized = f"bot_{random_suffix}"
        logger.debug("Localpart was invalid, using fallback => %r", sanitized)
    elif sanitized != original_localpart.lower():
        # Provide a debug log to note that we changed it
        logger.debug("Sanitized localpart from %r to %r", original_localpart, sanitized)

    # Rebuild the bot_id with the sanitized localpart
    # e.g. bot_id="@sanitized:localhost"
    new_bot_id = f"@{sanitized}:localhost"
    logger.debug("Final bot_id => %r", new_bot_id)

    # We'll just overwrite the caller's bot_id with new_bot_id, for consistency
    bot_id = new_bot_id

    # ------------------------------------------------------------------
    # 3) Create persona in personalities.json
    # ------------------------------------------------------------------
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
        return msg

    # ------------------------------------------------------------------
    # 4) Create the user in Synapse
    # ------------------------------------------------------------------
    # localpart for matrix creation => everything after "@..." but before :...
    # e.g. "sanitized"
    matrix_localpart = sanitized
    logger.debug("Attempting create_user(localpart=%r)", matrix_localpart)
    creation_msg = await create_user(matrix_localpart, password, is_admin=is_admin)

    if not creation_msg.startswith("Created user"):
        # e.g. "Error creating user..." or "HTTP 409 user already exists..."
        err = f"[create_and_login_bot] Synapse user creation failed => {creation_msg}"
        logger.error(err)
        return err

    # ------------------------------------------------------------------
    # 5) Ephemeral login
    # ------------------------------------------------------------------
    try:
        logger.debug("Attempting ephemeral login => bot_id=%r", bot_id)
        client = await load_or_login_client_v2(
            homeserver_url="http://localhost:8008",  # or from config
            user_id=bot_id,
            password=password,
            device_name=f"{sanitized}_device"
        )
        logger.info("[create_and_login_bot] Ephemeral login success => %s", bot_id)
    except Exception as e:
        logger.exception("[create_and_login_bot] Ephemeral login failed => %s", e)
        return f"Error ephemeral-logging in {bot_id}: {e}"

    # ------------------------------------------------------------------
    # 6) Register event callbacks
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 7) Start the sync loop & store references
    # ------------------------------------------------------------------
    try:
        from luna.core import BOTS, BOT_TASKS, run_bot_sync
        BOTS[sanitized] = client
        sync_task = asyncio.create_task(run_bot_sync(client, sanitized))
        BOT_TASKS.append(sync_task)
        logger.info("[create_and_login_bot] Bot '%s' sync loop started.", sanitized)

    except Exception as e:
        logger.exception("[create_and_login_bot] Could not store references or start sync => %s", e)
        return f"Error hooking bot '{sanitized}' into global loops => {e}"

    # ------------------------------------------------------------------
    # 8) Return final success message
    # ------------------------------------------------------------------
    success_msg = f"Successfully created & logged in => {bot_id}"
    logger.info(success_msg)
    return success_msg


# Optional: quick test harness
if __name__ == "__main__":
    async def test_run():
        user_id_full = "@testbot(!!!):localhost"  # intentionally invalid chars
        pwd  = "testbotPass!"
        display = "Test Bot #123"
        s_prompt = "You are a friendly test-bot for demonstration."
        traits_example = {"color": "blue", "hobby": "testing code"}
        
        result = await create_and_login_bot(
            bot_id=user_id_full,
            password=pwd,
            displayname=display,
            system_prompt=s_prompt,
            traits=traits_example
        )
        print(result)

    asyncio.run(test_run())
