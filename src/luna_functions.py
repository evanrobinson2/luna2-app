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
from nio.responses import ErrorResponse, SyncResponse, RoomMessagesResponse

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
    
# ──────────────────────────────────────────────────────────
# 1) ONE-TIME FULL FETCH
# ──────────────────────────────────────────────────────────
async def fetch_all_messages_once(
    client: AsyncClient, 
    room_ids: list[str] = None, 
    page_size: int = 100
) -> None:
    """
    Fetch *all* historical messages from the given room_ids (or all joined rooms if None),
    in paged fashion to avoid overwhelming the server. Then store them in:
      1) In-memory pandas DataFrame (returned).
      2) CSV on disk (MESSAGES_CSV).
    Also, we do NOT rely on 'sync_token' here; we aim to get the full history from earliest 
    to latest for each room. This can be a big operation if rooms are large!
    
    Args:
        client: The matrix-nio AsyncClient with valid access_token.
        room_ids (list[str]): Which rooms to fetch? If None, fetch from all joined rooms.
        page_size (int): How many messages to request per 'room_messages' call.

    Returns:
        None (but writes data to CSV and logs the process).
    """
    if not room_ids:
        # If no rooms given, use all the rooms the client is joined to
        room_ids = list(client.rooms.keys())
        logger.info(f"No room_ids specified. Using all joined rooms: {room_ids}")

    all_records = []
    for rid in room_ids:
        logger.info(f"Fetching *all* messages for room: {rid}")
        room_history = await _fetch_room_history_paged(client, rid, page_size=page_size)
        all_records.extend(room_history)

    # Convert to DataFrame
    df = pd.DataFrame(all_records, columns=["room_id", "event_id", "sender", "timestamp", "body"])
    logger.info(f"Fetched total {len(df)} messages across {len(room_ids)} room(s).")

    # Append or create CSV
    if os.path.exists(MESSAGES_CSV):
        # We’ll load the existing CSV, append, and drop duplicates
        existing_df = pd.read_csv(MESSAGES_CSV)
        combined_df = pd.concat([existing_df, df], ignore_index=True)
        combined_df.drop_duplicates(subset=["room_id", "event_id"], keep="last", inplace=True)
        combined_df.to_csv(MESSAGES_CSV, index=False)
        logger.info(f"Appended new records to existing {MESSAGES_CSV}. New total: {len(combined_df)}")
    else:
        # No existing CSV; just write fresh
        df.to_csv(MESSAGES_CSV, index=False)
        logger.info(f"Wrote all records to new CSV {MESSAGES_CSV}.")

async def _fetch_room_history_paged(
    client: AsyncClient, 
    room_id: str, 
    page_size: int
) -> list[dict]:
    """
    Helper to page backwards in time until no more messages or we hit server's earliest.
    Returns a list of records with fields: room_id, event_id, sender, timestamp, body
    """
    # We page backward starting from 'end=None' (latest) 
    # and continue until 'end' is empty or server doesn't return more chunk.
    all_events = []
    end_token = None

    while True:
        try:
            # 'room_messages' returns a RoomMessagesResponse
            response = await client.room_messages(
                room_id=room_id,
                start=end_token,
                limit=page_size,
                direction="b"  # backward in time
            )
            if not isinstance(response, RoomMessagesResponse):
                logger.warning(f"Got a non-success response: {response}")
                break
            
            chunk = response.chunk
            if not chunk:
                # No more events
                logger.info(f"No more chunk for {room_id}, done paging.")
                break

            for ev in chunk:
                # Only RoomMessageText events
                if isinstance(ev, RoomMessageText):
                    all_events.append({
                        "room_id": room_id,
                        "event_id": ev.event_id,
                        "sender": ev.sender,
                        "timestamp": ev.server_timestamp,  # or ev.timestamp
                        "body": ev.body
                    })
            
            end_token = response.end
            if not end_token:
                logger.info(f"Got empty 'end' token for {room_id}, done paging.")
                break

            logger.debug(f"Fetched {len(chunk)} messages this page for room={room_id}, new end={end_token}")

            # A small sleep to avoid spamming the server
            await asyncio.sleep(0.25)

        except Exception as e:
            logger.exception(f"Error in room_messages paging for {room_id}: {e}")
            break

    return all_events


# ──────────────────────────────────────────────────────────
# 2) FETCH ONLY NEW MESSAGES (SINCE A SYNC TOKEN)
# ──────────────────────────────────────────────────────────
async def fetch_all_new_messages(client: AsyncClient) -> None:
    """
    Uses client.sync(...) with a stored sync_token to retrieve only new messages across all joined rooms.
    Then appends them to the CSV & merges into memory as well.
    
    Steps:
      1) Load local 'sync_token' from disk (if any).
      2) Call client.sync(..., since=token).
      3) Parse the timeline events from each room, collect messages, 
         append to CSV, remove duplicates.
      4) Store the updated sync_token to disk.
    """
    old_token = load_sync_token() or None
    logger.info(f"Starting incremental sync from token={old_token}")

    # Perform a single sync with a short timeout to gather new events
    response = await client.sync(timeout=3000, since=old_token)
    if not isinstance(response, SyncResponse):
        logger.warning(f"Failed to sync for new messages: {response}")
        return
    
    # Collect timeline events
    new_records = []
    for room_id, room_data in response.rooms.join.items():
        # 'timeline.events' is a list of event objects
        for event in room_data.timeline.events:
            if isinstance(event, RoomMessageText):
                new_records.append({
                    "room_id": room_id,
                    "event_id": event.event_id,
                    "sender": event.sender,
                    "timestamp": event.server_timestamp,
                    "body": event.body,
                })

    logger.info(f"Fetched {len(new_records)} new messages across {len(response.rooms.join)} joined rooms.")

    # Append to CSV
    if new_records:
        df_new = pd.DataFrame(new_records, columns=["room_id", "event_id", "sender", "timestamp", "body"])

        if os.path.exists(MESSAGES_CSV):
            existing_df = pd.read_csv(MESSAGES_CSV)
            combined_df = pd.concat([existing_df, df_new], ignore_index=True)
            combined_df.drop_duplicates(subset=["room_id", "event_id"], keep="last", inplace=True)
            combined_df.to_csv(MESSAGES_CSV, index=False)
            logger.info(f"Appended new messages to {MESSAGES_CSV}. Updated total: {len(combined_df)}")
        else:
            df_new.to_csv(MESSAGES_CSV, index=False)
            logger.info(f"Wrote new messages to fresh CSV {MESSAGES_CSV}.")

    # Update the sync token so future calls only fetch *newer* content
    new_token = response.next_batch
    if new_token:
        store_sync_token(new_token)
        logger.info(f"Updated local sync token => {new_token}")