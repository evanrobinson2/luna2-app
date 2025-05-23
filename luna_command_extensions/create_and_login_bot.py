"""
create_and_login_bot.py

Handles creating a new bot persona record + user account + ephemeral login,
THEN registers event handlers & spawns the bot's sync loop.
"""

import logging
from typing import Dict, Any
import asyncio
import re
import json
import secrets  # for fallback random localpart (if needed)
import aiohttp

from nio import RoomMessageText, InviteMemberEvent, RoomMemberEvent, AsyncClient, LoginResponse

# Adjust these imports to match your new layout:
import luna.GLOBALS as g
import luna.luna_personas

# Regex that matches valid characters for localparts in Matrix user IDs:
# (Synapse typically allows `[a-z0-9._=/-]+` by default).
VALID_LOCALPART_REGEX = re.compile(r'[a-z0-9._=\-/]+')

async def run_bot_sync(bot_client: AsyncClient, localpart: str):
    """
    Simple sync loop for each bot, runs until SHOULD_SHUT_DOWN is True.
    """
    while not g.SHOULD_SHUT_DOWN:
        try:
            await bot_client.sync(timeout=5000)
        except Exception as e:
            g.LOGGER.exception(
                f"[run_bot_sync] Bot '{localpart}' had sync error: {e}"
            )
            await asyncio.sleep(2)  # brief backoff
        else:
            # If no error, give control to other tasks
            await asyncio.sleep(0)


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

    g.LOGGER.debug("[create_and_login_bot] Called with bot_id=%r, displayname=%r", bot_id, displayname)

    # 1) Validate & parse localpart
    if not bot_id.startswith("@") or ":" not in bot_id:
        err = f"[create_and_login_bot] Invalid bot_id => {bot_id}"
        g.LOGGER.warning(err)
        return {
            "ok": False,
            "bot_id": None,
            "client": None,
            "html": f"<p>{err}</p>",
            "error": err
        }

    original_localpart = bot_id.split(":")[0].replace("@", "", 1)
    g.LOGGER.debug("Original localpart extracted => %r", original_localpart)

    # 2) Sanitize localpart
    tmp = original_localpart.lower()
    sanitized = "".join(ch for ch in tmp if VALID_LOCALPART_REGEX.match(ch))
    if not sanitized:
        random_suffix = secrets.token_hex(4)
        sanitized = f"bot_{random_suffix}"
        g.LOGGER.debug("Localpart was invalid, using fallback => %r", sanitized)
    elif sanitized != original_localpart.lower():
        g.LOGGER.debug("Sanitized localpart from %r to %r", original_localpart, sanitized)

    new_bot_id = f"@{sanitized}:localhost"
    g.LOGGER.debug("Final bot_id => %r", new_bot_id)
    bot_id = new_bot_id

    # 3) Create persona in personalities.json
    try:
        g.LOGGER.debug("Creating persona in personalities.json => %r", bot_id)
        luna.luna_personas.create_bot(
            bot_id=bot_id,
            password=password,
            displayname=displayname,
            creator_user_id=creator_user_id,
            system_prompt=system_prompt,
            traits=traits
        )
        g.LOGGER.info("[create_and_login_bot] Persona created for %s.", bot_id)
    except Exception as e:
        msg = f"[create_and_login_bot] Could not create persona => {e}"
        g.LOGGER.exception(msg)
        return {
            "ok": False,
            "bot_id": None,
            "client": None,
            "html": f"<p>{msg}</p>",
            "error": str(e)
        }

    # 4) Create the user in Synapse
    matrix_localpart = sanitized
    g.LOGGER.debug("Attempting create_user(localpart=%r)", matrix_localpart)
    creation_msg = await create_user(matrix_localpart, password, is_admin=is_admin)
    if not creation_msg.startswith("Created user"):
        err = f"[create_and_login_bot] Synapse user creation failed => {creation_msg}"
        g.LOGGER.error(err)
        return {
            "ok": False,
            "bot_id": None,
            "client": None,
            "html": f"<p>{err}</p>",
            "error": creation_msg
        }

    # 5) Ephemeral login
    try:
        g.LOGGER.debug("Attempting ephemeral login => bot_id=%r", bot_id)
        client = await load_or_login_client_v2(
            homeserver_url="http://localhost:8008",
            user_id=bot_id,
            password=password,
            device_name=f"{sanitized}_device"
        )
        g.LOGGER.info("[create_and_login_bot] Ephemeral login success => %s", bot_id)
    except Exception as e:
        err = f"[create_and_login_bot] Ephemeral login failed => {e}"
        g.LOGGER.exception(err)
        return {
            "ok": False,
            "bot_id": None,
            "client": None,
            "html": f"<p>{err}</p>",
            "error": str(e)
        }

    # 6) Register event callbacks
    from luna.luna_command_extensions.bot_message_handler import handle_bot_room_message  # new advanced version
    from luna.luna_command_extensions.bot_invite_handler import handle_bot_invite  # new advanced version
    from luna.luna_command_extensions.bot_message_handler import handle_bot_room_message  # new advanced version
    from luna.luna_command_extensions.bot_member_event_handler import handle_bot_member_event  # new advanced version
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
            g.LOGGER.info("[create_and_login_bot] Registered event handlers for '%s'.", sanitized)
    except Exception as e:
        err = f"[create_and_login_bot] Error registering event callbacks => {e}"
        g.LOGGER.exception(err)
        return {
            "ok": False,
            "bot_id": bot_id,
            "client": client,
            "html": f"<p>{err}</p>",
            "error": str(e)
        }

    # 7) Start the sync loop & store references
    g.BOTS[sanitized] = client
    sync_task = asyncio.create_task(run_bot_sync(client, sanitized))
    g.BOT_TASKS.append(sync_task)
    g.LOGGER.info("[create_and_login_bot] Bot '%s' sync loop started.", sanitized)

    # 8) Final success
    success_msg = f"Successfully created & logged in => {bot_id}"
    g.LOGGER.info(success_msg)
    return {
        "ok": True,
        "bot_id": bot_id,         # final sanitized bot ID
        "client": client,         # ephemeral bot client
        "html": f"<p>{success_msg}</p>",
        "error": None
    }

async def create_user(username: str, password: str, is_admin: bool = False) -> str:
    """
    The single Luna function to create a user.
    1) Loads the admin token from tokens.json.
    2) Calls add_user_via_admin_api(...) from luna_functions.py.
    3) Returns a success/error message.
    """
    # 1) Load admin token
    HOMESERVER_URL = "http://localhost:8008"  # or read from config
    try:
        with open("data/tokens.json", "r") as f:
            data = json.load(f)
        admin_token = data["access_token"]
    except Exception as e:
        err_msg = f"Error loading admin token from tokens.json: {e}"
        g.LOGGER.error(err_msg)
        return err_msg

    # 2) Delegate the actual call to your existing function
    #    (Yes, ironically still referencing `luna_functions`, but that’s how your code is structured)
    result = await add_user_via_admin_api(
        homeserver_url=HOMESERVER_URL,
        admin_token=admin_token,
        username=username,
        password=password,
        is_admin=is_admin
    )

    # 3) Return the result message
    return result

async def load_or_login_client_v2(
    homeserver_url: str,
    user_id: str,
    password: str,
    device_name: str = "BotDevice"
) -> AsyncClient:
    """
    load_or_login_client_ephemeral

    A simplified function that logs in a Matrix user via password each time,
    returning a ready-to-use AsyncClient. No tokens are stored or reused.

    Args:
      homeserver_url: Your Synapse server address, e.g. "http://localhost:8008"
      user_id: A full Matrix user ID (e.g. "@inky:localhost") or localpart if you prefer
      password: The account's password.
      device_name: A label for the login session.

    Returns:
      An AsyncClient logged in as `user_id`. If login fails, raises Exception.
    """

    # If the caller passed only the local part (like "inky"), you might want to ensure:
    #   if not user_id.startswith("@"):
    #       user_id = f"@{user_id}:localhost"
    # But that depends on your usage.

    g.LOGGER.info(f"[load_or_login_client_v2] [{user_id}] Attempting password login...")

    # 1) Construct the client
    client = AsyncClient(homeserver=homeserver_url, user=user_id)

    # 2) Attempt the password login
    resp = await client.login(password=password, device_name=device_name)

    # 3) Check result
    if isinstance(resp, LoginResponse):
        g.LOGGER.info(f"[{user_id}] Password login succeeded. user_id={client.user_id}")
        return client
    else:
        g.LOGGER.error(f"[{user_id}] Password login failed => {resp}")
        raise Exception(f"Password login failed for {user_id}: {resp}")

# ──────────────────────────────────────────────────────────
# ADMIN API FOR CREATING USERS
# ──────────────────────────────────────────────────────────
async def add_user_via_admin_api(
    homeserver_url: str,
    admin_token: str,
    username: str,
    password: str,
    is_admin: bool = False
) -> str:
    """
    Creates a new user by hitting the Synapse Admin API.
    """
    user_id = f"@{username}:localhost"
    url = f"{homeserver_url}/_synapse/admin/v2/users/{user_id}"

    body = {
        "password": password,
        "admin": is_admin,
        "deactivated": False
    }
    headers = {
        "Authorization": f"Bearer {admin_token}"
    }

    g.LOGGER.info(f"Creating user {user_id}, admin={is_admin} via {url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.request("PUT", url, headers=headers, json=body) as resp:
                if resp.status in (200, 201):
                    g.LOGGER.info(f"Created user {user_id} (HTTP {resp.status})")
                    return f"Created user {user_id} (admin={is_admin})."
                else:
                    text = await resp.text()
                    g.LOGGER.error(f"Error creating user {user_id}: {resp.status} => {text}")
                    return f"HTTP {resp.status}: {text}"

    except aiohttp.ClientError as e:
        g.LOGGER.exception(f"Network error creating user {user_id}")
        return f"Network error: {e}"
    except Exception as e:
        g.LOGGER.exception("Unexpected error.")
        return f"Unexpected error: {e}"
