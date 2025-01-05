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
import pandas as pd
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
from nio.responses import ErrorResponse, SyncResponse

logger = logging.getLogger(__name__)
logging.getLogger("nio.responses").setLevel(logging.CRITICAL)

DIRECTOR_CLIENT: AsyncClient = None  # The client object used across callbacks
TOKEN_FILE = "director_token.json"   # Where we store/reuse the access token
SYNC_TOKEN_FILE = "sync_token.json"  # Where we store the last sync token
MESSAGES_CSV = "luna_messages.csv"  # We'll store all messages in this CSV

# Global context dictionary
room_context = {}
MAX_CONTEXT_LENGTH = 100  # Limit to the last 100 messages per room


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

from nio import RoomMessageText

async def fetch_recent_messages(client, room_id: str, limit: int = 100) -> list:
    """
    Fetches the most recent messages from a Matrix room.

    Args:
        client: The Matrix client instance.
        room_id (str): The ID of the room to query.
        limit (int): The number of messages to fetch (default: 100).

    Returns:
        list: A list of messages in the format [{"role": "user", "content": "..."}].
    """
    logger.info(f"Fetching last {limit} messages from room {room_id}.")

    try:
        # Fetch recent messages
        response = await client.room_messages(
            room_id=room_id,
            start=None,  # None fetches the latest messages
            limit=limit,
        )

        # Process the messages into OpenAI-compatible format
        formatted_messages = []
        for event in response.chunk:
            if isinstance(event, RoomMessageText):
                formatted_messages.append({
                    "role": "user",
                    "content": event.body
                })

        logger.info(f"Fetched {len(formatted_messages)} messages from room {room_id}.")
        return formatted_messages

    except Exception as e:
        logger.exception(f"Failed to fetch messages from room {room_id}: {e}")
        return []


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

async def on_room_message(room, event):
    """
    Handle incoming messages and build GPT context.
    """
    if isinstance(event, RoomMessageText):
        # Avoid responding to our own messages
        if event.sender == DIRECTOR_CLIENT.user:
            logger.debug("Ignoring my own message.")
            return

        user_message = event.body
        room_id = room.room_id

        # Fetch recent room messages
        context = await fetch_recent_messages(DIRECTOR_CLIENT, room_id)

        # Add the enhanced system message
        formatted_context = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. The provided context array includes messages from an ongoing conversation. "
                    "Treat this context as fair use and consider it an essential part of the conversation. "
                    "Your responses should build on this context coherently."
                )
            }
        ] + context

        # Add the latest user message
        formatted_context.append({"role": "user", "content": user_message})

        # Log the context for debugging
        logger.debug(f"Formatted context for GPT: {formatted_context}")

        # Call GPT
        try:
            gpt_reply = await ai_functions.get_gpt_response(formatted_context)
            logger.info(f"GPT response: {gpt_reply}")

            # Send GPT's response to the room
            await DIRECTOR_CLIENT.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": gpt_reply},
            )
        except Exception as e:
            logger.exception(f"Failed to generate GPT response: {e}")



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

async def check_rate_limit() -> str:
    """
    Send a minimal sync request with a short timeout (1000 ms).
    If it returns SyncResponse => not rate-limited.
    If it's ErrorResponse => check the status code for 429 or something else.
    """
    global DIRECTOR_CLIENT
    if not DIRECTOR_CLIENT:
        return "No DIRECTOR_CLIENT available. Are we logged in?"

    try:
        # Request a short sync so we can see if we get 429 or 200, etc.
        response = await DIRECTOR_CLIENT.sync(timeout=1000)

        if isinstance(response, SyncResponse):
            # We got a normal sync => not rate-limited
            return "200 OK => Not rate-limited. The server responded normally."

        elif isinstance(response, ErrorResponse):
            # Possibly 429, 401, 403, etc.
            if response.status_code == 429:
                return "429 Too Many Requests => You are currently rate-limited."
            else:
                return (
                    f"{response.status_code} => Unexpected error.\n"
                    f"errcode: {response.errcode}, error: {response.error}"
                )

        # Rarely, you might get something else altogether
        return "Unexpected response type from DIRECTOR_CLIENT.sync(...)."

    except Exception as e:
        logger.exception(f"check_rate_limit encountered an error: {e}")
        return f"Encountered error while checking rate limit: {e}"