"""
luna_functions.py

Contains:
- Token-based login logic (load_or_login_client)
- Global reference to the Director client
- Message & invite callbacks
"""

import asyncio
import logging
import sys
import json
import os
from nio import (
    AsyncClient,
    LoginResponse,
    RoomMessageText,
    InviteMemberEvent,
    RoomCreateResponse,
    RoomInviteResponse,
    LocalProtocolError
)

logger = logging.getLogger(__name__)

DIRECTOR_CLIENT: AsyncClient = None  # Global reference for event callbacks
TOKEN_FILE = "director_token.json"   # Where we store/reuse the access token

async def load_or_login_client(homeserver_url: str, username: str, password: str) -> AsyncClient:
    """
    Attempt to load a saved access token from TOKEN_FILE. If it exists,
    reuse that token. Otherwise, do a password login, and store the new token.
    Also sets DIRECTOR_CLIENT global so event callbacks can use it.
    """
    global DIRECTOR_CLIENT

    full_user_id = f"@{username}:localhost"  # adapt if needed
    client = None

    # 1) Check for existing token file
    if os.path.exists(TOKEN_FILE):
        logger.debug(f"Found {TOKEN_FILE}, attempting token-based login.")
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
            saved_user_id = data.get("user_id")
            saved_access_token = data.get("access_token")
            saved_device_id = data.get("device_id")

        if saved_user_id and saved_access_token:
            logger.debug("Loading client with saved token credentials.")
            client = AsyncClient(homeserver=homeserver_url, user=saved_user_id)
            client.access_token = saved_access_token
            client.device_id = saved_device_id

            # Optionally, you could do a quick test (like a whoami or minimal sync).
            # If that fails, fallback to password login. We'll skip that for brevity.
            DIRECTOR_CLIENT = client
            logger.info(f"Using saved token for user {saved_user_id}.")
            return client

    # 2) If we get here, no valid token file. Perform password login.
    logger.debug("No valid token found, attempting normal password login.")
    client = AsyncClient(homeserver=homeserver_url, user=full_user_id)
    resp = await client.login(password=password, device_name="LunaDirector")
    if isinstance(resp, LoginResponse):
        logger.info("Password login succeeded, storing token.")
        store_token_info(client.user_id, client.access_token, client.device_id)

        DIRECTOR_CLIENT = client
        return client
    else:
        logger.error(f"Failed to log in: {resp}")
        logger.debug("Closing client due to login failure.")
        await client.close()
        sys.exit(1)


def store_token_info(user_id: str, access_token: str, device_id: str) -> None:
    """
    Store user_id, device_id, and access_token in a JSON file so we can reuse them later.
    """
    with open(TOKEN_FILE, "w") as f:
        json.dump({
            "user_id": user_id,
            "access_token": access_token,
            "device_id": device_id,
        }, f)
    logger.debug(f"Token info for {user_id} saved to {TOKEN_FILE}.")


###
# Event Callbacks for Room Messages and Invites
###

async def on_room_message(room, event):
    """
    Called whenever a RoomMessageText event is received in a room the client is in.
    """
    global DIRECTOR_CLIENT
    if not DIRECTOR_CLIENT:
        logger.warning("No DIRECTOR_CLIENT set. Cannot respond to messages.")
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
    """
    Called whenever the client is invited to a room.
    """
    global DIRECTOR_CLIENT
    if not DIRECTOR_CLIENT:
        logger.warning("No DIRECTOR_CLIENT set. Cannot handle invites.")
        return

    logger.info(f"Received invite to {room.room_id}, joining now.")
    try:
        await DIRECTOR_CLIENT.join(room.room_id)
    except LocalProtocolError as e:
        logger.error(f"Error joining room {room.room_id}: {e}")
