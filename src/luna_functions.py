"""
src/luna_functions.py

Contains:
- Global toggle and references
- Director login logic
- Invite and message callbacks
- Helper to send messages
- Helper to create new channels + auto-invite default user
- Helper to invite arbitrary users or 'admin'
- Now includes get_auto_join_enabled() to support the 'autojoin' console command
"""

import asyncio
import logging
import sys

from nio import (
    AsyncClient,
    LoginResponse,
    RoomMessageText,
    InviteMemberEvent,
    RoomCreateResponse,
    RoomInviteResponse
)

logger = logging.getLogger(__name__)

DIRECTOR_CLIENT: AsyncClient = None  # Global reference
AUTO_JOIN_ENABLED = True             # Toggle for auto-join (boolean)

# Hard-code some user you want invited
DEFAULT_INVITE_USER = "@me:localhost"

async def director_login(homeserver_url: str, username: str, password: str) -> AsyncClient:
    logger.debug(f"director_login: homeserver_url={homeserver_url}, username={username}")

    client = AsyncClient(homeserver_url, f"@{username}:localhost")
    logger.debug("Attempting to log in...")

    resp = await client.login(password=password, device_name="LunaDirector")
    logger.debug(f"Login response object: {resp}")

    if isinstance(resp, LoginResponse):
        logger.info("Director logged in successfully.")
        global DIRECTOR_CLIENT
        DIRECTOR_CLIENT = client
        return client
    else:
        logger.error(f"Failed to log in: {resp}")
        logger.debug("Closing client due to login failure...")
        await client.close()
        sys.exit(1)

def set_auto_join(enable: bool) -> None:
    """
    Enables (True) or disables (False) automatic joining of invites.
    """
    global AUTO_JOIN_ENABLED
    AUTO_JOIN_ENABLED = enable

def get_auto_join_enabled() -> bool:
    """
    Returns whether auto-join is currently enabled (True) or disabled (False).
    """
    return AUTO_JOIN_ENABLED

async def on_room_message(room, event):
    if not DIRECTOR_CLIENT:
        logger.warning("No DIRECTOR_CLIENT set. Cannot respond.")
        return

    if event.sender == DIRECTOR_CLIENT.user:
        logger.debug("Received message from ourselves; ignoring.")
        return

    if isinstance(event, RoomMessageText):
        sender = event.sender
        body = event.body
        logger.info(f"Received message in {room.room_id} from {sender}: {body}")

        response = f"Hello {sender}, you said '{body}' (auto-respond)."
        logger.debug(f"Sending response: {response}")

        await DIRECTOR_CLIENT.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": response}
        )

async def on_invite_event(room, event):
    if not DIRECTOR_CLIENT:
        logger.warning("No DIRECTOR_CLIENT set. Cannot handle invites.")
        return

    # We log the current boolean state
    logger.info(f"Received invite to {room.room_id}, AUTO_JOIN_ENABLED={AUTO_JOIN_ENABLED}")

    if AUTO_JOIN_ENABLED:
        logger.info(f"Joining {room.room_id}...")
        await DIRECTOR_CLIENT.join(room.room_id)
    else:
        logger.info(f"Auto-join is disabled; ignoring invite.")

async def console_send_message(room_id: str, text: str):
    logger.debug(f"console_send_message to {room_id}: {text}")
    if not DIRECTOR_CLIENT:
        logger.warning("No DIRECTOR_CLIENT available for sending.")
        return

    await DIRECTOR_CLIENT.room_send(
        room_id=room_id,
        message_type="m.room.message",
        content={"msgtype": "m.text", "body": text},
    )
    logger.debug("Console-triggered message sent.")

# 1. CREATE NEW ROOM
async def director_create_room(room_name: str):
    """
    Creates a new Matrix room named `room_name` and invites `DEFAULT_INVITE_USER`.
    """
    if not DIRECTOR_CLIENT:
        logger.warning("No DIRECTOR_CLIENT available for creating rooms.")
        return

    logger.info(f"Creating room with name: {room_name}, inviting {DEFAULT_INVITE_USER}...")

    try:
        create_resp = await DIRECTOR_CLIENT.room_create(
            name=room_name,
            invite=[DEFAULT_INVITE_USER],
            is_direct=False
        )

        if isinstance(create_resp, RoomCreateResponse):
            logger.info(f"Room created! ID: {create_resp.room_id}")
            return create_resp.room_id
        else:
            logger.warning(f"Room creation response was not a success: {create_resp}")
            return None

    except Exception as e:
        logger.error(f"Error creating room: {e}")
        return None

# 2. ADD PARTICIPANT (Invite arbitrary user)
async def director_invite_user(room_id: str, user_id: str):
    """
    Invite `user_id` to join the given `room_id`.
    """
    if not DIRECTOR_CLIENT:
        logger.warning("No DIRECTOR_CLIENT set. Cannot invite users.")
        return

    logger.info(f"Inviting user '{user_id}' to room {room_id}...")

    try:
        invite_resp = await DIRECTOR_CLIENT.room_invite(room_id, user_id)

        if isinstance(invite_resp, RoomInviteResponse):
            logger.info(f"Invited {user_id} to {room_id} successfully.")
        else:
            logger.warning(f"Invite response was not a success: {invite_resp}")

    except Exception as e:
        logger.error(f"Error inviting user {user_id} to {room_id}: {e}")

# 3. INVITE ADMIN
async def director_invite_admin(room_id: str):
    """
    Invite an 'admin' user to the given room.
    For demonstration, we assume the admin user is @admin:localhost or similar.
    """
    admin_user = "@admin:localhost"
    logger.info(f"Inviting 'admin' user {admin_user} to room {room_id}...")
    await director_invite_user(room_id, admin_user)

def get_director():
    """
    Return the Director client object (if any) for advanced usage,
    or None if not logged in.
    """
    return DIRECTOR_CLIENT
