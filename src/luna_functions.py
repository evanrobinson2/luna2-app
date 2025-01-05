"""
luna_functions.py

Contains:
- Token-based login logic (load_or_login_client)
- Global reference to the Director client
- Message & invite callbacks
- Utility to load/save sync token
"""
from . import ai_functions
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
logging.getLogger("nio.responses").setLevel(logging.WARNING)

DIRECTOR_CLIENT: AsyncClient = None  # The client object used across callbacks
TOKEN_FILE = "director_token.json"   # Where we store/reuse the access token
SYNC_TOKEN_FILE = "sync_token.json"  # Where we store the last sync token

async def load_or_login_client(homeserver_url: str, username: str, password: str) -> AsyncClient:
    """
    Attempt to load a saved access token. If found, reuse it.
    Otherwise do a password login, store the new token, and return a client.
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

            DIRECTOR_CLIENT = client
            logger.info(f"Using saved token for user {saved_user_id}.")
            return client

    # 2) If no valid token file, do a normal login
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


### Sync Token Management

def load_sync_token() -> str:
    """
    Load the previously saved sync token (next_batch).
    Returns None if no file or invalid content.
    """
    if not os.path.exists(SYNC_TOKEN_FILE):
        return None
    try:
        with open(SYNC_TOKEN_FILE, "r") as f:
            return json.load(f).get("sync_token")
    except Exception as e:
        logger.warning(f"Failed to load sync token: {e}")
    return None

def store_sync_token(sync_token: str) -> None:
    """
    Persist the sync token so we won't re-fetch old messages on next run.
    """
    if not sync_token:
        return
    with open(SYNC_TOKEN_FILE, "w") as f:
        json.dump({"sync_token": sync_token}, f)
    logger.debug(f"Sync token saved to {SYNC_TOKEN_FILE}.")


### Callbacks
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
        user_message = event.body
        logger.info(f"Received message in {room.room_id} from {sender}: {user_message}")

        # Call GPT for a response
        gpt_reply = await ai_functions.get_gpt_response(user_message)
        logger.info(f"GPT replied: {gpt_reply}")

        # Send GPT response back to the room
        await DIRECTOR_CLIENT.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": gpt_reply}
        )



async def on_room_message_dep(room, event):
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

    logger.debug(f"Got an event of type: {type(event)}, content: {event.source}")

    if isinstance(event, RoomMessageText):
        sender = event.sender
        body = event.body
        logger.info(f"Received message in {room.room_id} from {sender}: {body}")
        
        ai_functions.get_ai_response(f'{body}')
        logging.info(f"GPT Response: {ai_functions.get_ai_response(f'{body}')}")
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
