"""
create_and_login_bot.py

Handles creating a new bot persona record + user account + ephemeral login,
THEN registers event handlers & spawns the bot's sync loop.
"""

import logging
import asyncio

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
    :return:          Success/error string.
    """

    # 1) Validate & parse localpart
    if not bot_id.startswith("@") or ":" not in bot_id:
        return f"[create_and_login_bot] Invalid bot_id => {bot_id}"

    localpart = bot_id.split(":")[0].replace("@", "")  # e.g. "spiderbot"

    # 2) Create persona in personalities.json
    try:
        luna.luna_personas.create_bot(
            bot_id=bot_id,
            password=password,
            displayname=displayname,
            creator_user_id=creator_user_id,
            system_prompt=system_prompt,
            traits=traits
        )
        logger.info(f"[create_and_login_bot] Persona created for {bot_id}.")
    except Exception as e:
        msg = f"[create_and_login_bot] Could not create persona => {e}"
        logger.exception(msg)
        return msg

    # 3) Create the user in Synapse
    username = localpart  # the localpart only
    creation_msg = await create_user(username, password, is_admin=is_admin)
    if not creation_msg.startswith("Created user"):
        # e.g. "Error creating user..." or "HTTP 409 user already exists..."
        err = f"[create_and_login_bot] Synapse user creation failed => {creation_msg}"
        logger.error(err)
        return err

    # 4) Ephemeral login
    try:
        client = await load_or_login_client_v2(
            homeserver_url="http://localhost:8008",  # or from config
            user_id=bot_id,
            password=password,
            device_name=f"{localpart}_device"
        )
        logger.info(f"[create_and_login_bot] Ephemeral login success => {bot_id}")
    except Exception as e:
        logger.exception(f"[create_and_login_bot] Ephemeral login failed => {e}")
        return f"Error ephemeral-logging in {bot_id}: {e}"

    # 5) Register event callbacks for message/invite/member
    client.add_event_callback(
        lambda room, evt: handle_bot_room_message(client, localpart, room, evt),
        RoomMessageText
    )
    client.add_event_callback(
        lambda room, evt: handle_bot_invite(client, localpart, room, evt),
        InviteMemberEvent
    )
    client.add_event_callback(
        lambda room, evt: handle_bot_member_event(client, localpart, room, evt),
        RoomMemberEvent
    )
    logger.info(f"[create_and_login_bot] Registered event handlers for '{localpart}'.")

    # 6) Start a sync loop for this bot & store references in global BOTS + BOT_TASKS
    try:
        from luna.core import BOTS, BOT_TASKS, run_bot_sync
        BOTS[localpart] = client
        sync_task = asyncio.create_task(run_bot_sync(client, localpart))
        BOT_TASKS.append(sync_task)
        logger.info(f"[create_and_login_bot] Bot '{localpart}' sync loop started.")

    except Exception as e:
        logger.exception(f"[create_and_login_bot] Could not store references or start sync => {e}")
        return f"Error hooking bot '{localpart}' into global loops => {e}"

    success_msg = f"Successfully created & logged in => {bot_id}"
    logger.info(success_msg)
    return success_msg


# Optional: quick test harness
if __name__ == "__main__":
    async def test_run():
        user_id_full = "@testbot123:localhost"
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
