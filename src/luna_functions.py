"""
luna_functions.py

Contains:
- Token-based login logic (load_or_login_client)
- Global reference to the Director client
- Message & invite callbacks
- Utility to load/save sync token
"""
from src import ai_functions

import asyncio
import aiohttp
import logging
import time
import json
import pandas as pd
import os
import datetime
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
from src.luna_personas import _load_personalities
logger = logging.getLogger(__name__)
logging.getLogger("nio.responses").setLevel(logging.CRITICAL)

# ──────────────────────────────────────────────────────────
# GLOBALS
# ──────────────────────────────────────────────────────────
DIRECTOR_CLIENT: AsyncClient = None  # The client object used across callbacks
TOKEN_FILE = "data/director_token.json"   # Where we store/reuse the access token
SYNC_TOKEN_FILE = "data/sync_token.json"  # Where we store the last sync token
MESSAGES_CSV = "data/luna_messages.csv"   # We'll store all messages in this CSV

# Global context dictionary (if needed by your logic)
room_context = {}
MAX_CONTEXT_LENGTH = 100  # Limit to the last 100 messages per room

# ──────────────────────────────────────────────────────────
# TOKEN-BASED LOGIN
# ──────────────────────────────────────────────────────────
async def load_or_login_client(homeserver_url: str, username: str, password: str) -> AsyncClient:
    """
    Attempt to load a saved access token. If found, verify it by calling whoami().
    If valid, reuse it. If invalid (or absent), do a normal password login and store
    the resulting token. Returns an AsyncClient ready to use.
    """
    global DIRECTOR_CLIENT

    full_user_id = f"@{username}:localhost"  # Adjust the domain if needed
    client = None

    # 1. Check for an existing token file
    if os.path.exists(TOKEN_FILE):
        logger.debug(f"Found {TOKEN_FILE}; attempting token-based login.")
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
            saved_user_id = data.get("user_id")
            saved_access_token = data.get("access_token")
            saved_device_id = data.get("device_id")

        # 2. If the file contains valid fields, construct a client
        if saved_user_id and saved_access_token:
            logger.debug("Loading client with saved token credentials.")
            client = AsyncClient(homeserver=homeserver_url, user=saved_user_id)
            client.access_token = saved_access_token
            client.device_id = saved_device_id

            # 3. Verify the token with whoami()
            try:
                whoami_resp = await client.whoami()
                if whoami_resp and whoami_resp.user_id == saved_user_id:
                    # If it matches, we're good to go
                    logger.info(f"Token-based login verified for user {saved_user_id}.")
                    DIRECTOR_CLIENT = client
                    return client
                else:
                    # Otherwise, token is invalid or stale
                    logger.warning("Token-based login invalid. Deleting token file.")
                    os.remove(TOKEN_FILE)
            except Exception as e:
                # whoami() call itself failed; treat as invalid
                logger.warning(f"Token-based verification failed: {e}. Deleting token file.")
                os.remove(TOKEN_FILE)

    # 4. If we reach here, either there was no token file or token verification failed
    logger.debug("No valid token (or it was invalid). Attempting normal password login.")
    client = AsyncClient(homeserver=homeserver_url, user=full_user_id)
    resp = await client.login(password=password, device_name="LunaDirector")
    if isinstance(resp, LoginResponse):
        # 5. Password login succeeded; store a fresh token
        logger.info(f"Password login succeeded for user {client.user_id}. Storing token...")
        store_token_info(client.user_id, client.access_token, client.device_id)
        DIRECTOR_CLIENT = client
        return client
    else:
        # 6. Password login failed: raise an exception or handle it as desired
        logger.error(f"Password login failed: {resp}")
        raise Exception("Password login failed. Check credentials or homeserver settings.")

import logging

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# CREATE USER LOGIC
# ──────────────────────────────────────────────────────────
async def create_user(username: str, password: str, is_admin: bool = False) -> str:
    """
    The single Luna function to create a user.
    1) Loads the admin token from director_token.json.
    2) Calls add_user_via_admin_api(...) from luna_functions.py.
    3) Returns a success/error message.
    """
    # 1) Load admin token
    HOMESERVER_URL = "http://localhost:8008"  # or read from config
    try:
        with open("data/director_token.json", "r") as f:
            data = json.load(f)
        admin_token = data["access_token"]
    except Exception as e:
        err_msg = f"Error loading admin token from director_token.json: {e}"
        logger.error(err_msg)
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

# ──────────────────────────────────────────────────────────
# LIST ROOMS
# ──────────────────────────────────────────────────────────
async def list_rooms() -> list[dict]:
    """
    Returns a list of rooms that DIRECTOR_CLIENT knows about, 
    including participant names.

    Each dict in the returned list includes:
       {
         "room_id": "<string>",
         "name": "<string>",
         "joined_members_count": <int>,
         "participants": [<list of user IDs or display names>]
       }
    """
    if not DIRECTOR_CLIENT:
        logger.warning("list_rooms called, but DIRECTOR_CLIENT is None.")
        return []

    rooms_info = []
    for room_id, room_obj in DIRECTOR_CLIENT.rooms.items():
        room_name = room_obj.display_name or "(unnamed)"
        participant_list = [user_id for user_id in room_obj.users.keys()]

        rooms_info.append({
            "room_id": room_id,
            "name": room_name,
            "joined_members_count": len(participant_list),
            "participants": participant_list
        })

    return rooms_info


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

    logger.info(f"Creating user {user_id}, admin={is_admin} via {url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.request("PUT", url, headers=headers, json=body) as resp:
                if resp.status in (200, 201):
                    logger.info(f"Created user {user_id} (HTTP {resp.status})")
                    return f"Created user {user_id} (admin={is_admin})."
                else:
                    text = await resp.text()
                    logger.error(f"Error creating user {user_id}: {resp.status} => {text}")
                    return f"HTTP {resp.status}: {text}"

    except aiohttp.ClientError as e:
        logger.exception(f"Network error creating user {user_id}")
        return f"Network error: {e}"
    except Exception as e:
        logger.exception("Unexpected error.")
        return f"Unexpected error: {e}"

# ──────────────────────────────────────────────────────────
# RECENT MESSAGES
# ──────────────────────────────────────────────────────────
async def fetch_recent_messages(room_id: str, limit: int = 100) -> list:
    """
    Fetches the most recent messages from a Matrix room. Used to build context for
    """
    logger.info(f"Fetching last {limit} messages from room {room_id}.")
    client = DIRECTOR_CLIENT
    try:
        response = await client.room_messages(
            room_id=room_id,
            start=None,  # None fetches the latest messages
            limit=limit,
        )
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
    Write the token file to disk, so we can reuse it in later runs.
    """
    data = {
        "user_id": user_id,
        "access_token": access_token,
        "device_id": device_id
    }
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f)
    logger.debug(f"Stored token data for {user_id} into {TOKEN_FILE}.")


# ──────────────────────────────────────────────────────────
# SYNC TOKEN MANAGEMENT
# ──────────────────────────────────────────────────────────
def load_sync_token() -> str:
    """
    Load the previously saved sync token (next_batch).
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

async def post_gpt_reply(room_id: str, gpt_reply: str) -> None:
    """
    Helper to post a GPT-generated reply to a given room,
    using the global DIRECTOR_CLIENT if it's set.
    """
    global DIRECTOR_CLIENT

    if not DIRECTOR_CLIENT:
        logger.warning("No DIRECTOR_CLIENT set; cannot post GPT reply.")
        return

    try:
        await DIRECTOR_CLIENT.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": gpt_reply},
        )
        logger.info(f"Posted GPT reply to room {room_id}")
    except Exception as e:
        logger.exception(f"Failed to send GPT reply: {e}")


# ──────────────────────────────────────────────────────────
# The specialized dispatch function is replaced with the import below
# We rely on that file (luna_functions_handledispatch.py) to handle routing
# but it calls back into this file for actual matrix actions.
# ──────────────────────────────────────────────────────────
# covered by another import from src.luna_functions_handledispatch import on_room_message


# ──────────────────────────────────────────────────────────
# ON INVITE EVENT
# ──────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────
# CHECK RATE LIMIT
# ──────────────────────────────────────────────────────────
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
        response = await DIRECTOR_CLIENT.sync(timeout=1000)

        if isinstance(response, SyncResponse):
            return "200 OK => Not rate-limited. The server responded normally."
        elif isinstance(response, ErrorResponse):
            if response.status_code == 429:
                return "429 Too Many Requests => You are currently rate-limited."
            else:
                return (
                    f"{response.status_code} => Unexpected error.\n"
                    f"errcode: {response.errcode}, error: {response.error}"
                )
        return "Unexpected response type from DIRECTOR_CLIENT.sync(...)."
    except Exception as e:
        logger.exception(f"check_rate_limit encountered an error: {e}")
        return f"Encountered error while checking rate limit: {e}"

def _print_progress(stop_event):
    """
    Prints '...' every second until stop_event is set.
    """
    while not stop_event.is_set():
        print("...", end='', flush=True)
        time.sleep(1)

async def fetch_all_messages_once(
    client: AsyncClient, 
    room_ids: list[str] = None, 
    page_size: int = 100
) -> None:
    """
    Fetch *all* historical messages from the given room_ids (or all joined rooms if None).
    Populates the MESSAGES_CSV file, creating it if it doesn't exist or is empty.
    """
    if not room_ids:
        room_ids = list(client.rooms.keys())
        logger.info(f"No room_ids specified. Using all joined rooms: {room_ids}")

    all_records = []
    for rid in room_ids:
        logger.info(f"Fetching *all* messages for room: {rid}")
        room_history = await _fetch_room_history_paged(client, rid, page_size=page_size)
        all_records.extend(room_history)

    if not all_records:
        logger.warning("No messages fetched. CSV file will not be updated.")
        return

    df = pd.DataFrame(all_records, columns=["room_id", "event_id", "sender", "timestamp", "body"])
    logger.info(f"Fetched total {len(df)} messages across {len(room_ids)} room(s).")

    if os.path.exists(MESSAGES_CSV):
        try:
            # Attempt to read existing CSV
            existing_df = pd.read_csv(MESSAGES_CSV)
            logger.debug(f"Existing CSV loaded with {len(existing_df)} records.")
        except pd.errors.EmptyDataError:
            # Handle empty CSV by creating an empty DataFrame with the correct columns
            existing_df = pd.DataFrame(columns=["room_id", "event_id", "sender", "timestamp", "body"])
            logger.warning(f"{MESSAGES_CSV} is empty. Creating a new DataFrame with columns.")

        # Combine existing and new records
        combined_df = pd.concat([existing_df, df], ignore_index=True)
        # Drop duplicates based on 'room_id' and 'event_id'
        combined_df.drop_duplicates(subset=["room_id", "event_id"], keep="last", inplace=True)
        # Save back to CSV
        combined_df.to_csv(MESSAGES_CSV, index=False)
        logger.info(f"Appended new records to existing {MESSAGES_CSV}. New total: {len(combined_df)}")
    else:
        # If CSV doesn't exist, create it with the new records
        df.to_csv(MESSAGES_CSV, index=False)
        logger.info(f"Wrote all records to new CSV {MESSAGES_CSV}.")

async def _fetch_room_history_paged(
    client: AsyncClient, 
    room_id: str, 
    page_size: int
) -> list[dict]:
    """
    Helper to page backwards in time until no more messages or we hit server's earliest.
    ...
    """
    all_events = []
    end_token = None

    while True:
        try:
            response = await client.room_messages(
                room_id=room_id,
                start=end_token,
                limit=page_size,
                direction="b"
            )
            if not isinstance(response, RoomMessagesResponse):
                logger.warning(f"Got a non-success response: {response}")
                break
            
            chunk = response.chunk
            if not chunk:
                logger.info(f"No more chunk for {room_id}, done paging.")
                break

            for ev in chunk:
                if isinstance(ev, RoomMessageText):
                    all_events.append({
                        "room_id": room_id,
                        "event_id": ev.event_id,
                        "sender": ev.sender,
                        "timestamp": ev.server_timestamp,
                        "body": ev.body
                    })
            
            end_token = response.end
            if not end_token:
                logger.info(f"Got empty 'end' token for {room_id}, done paging.")
                break

            logger.debug(f"Fetched {len(chunk)} messages this page for room={room_id}, new end={end_token}")
            await asyncio.sleep(0.25)

        except Exception as e:
            logger.exception(f"Error in room_messages paging for {room_id}: {e}")
            break

    return all_events

async def fetch_all_messages_once(
    client, 
    room_ids: list[str] = None, 
    page_size: int = 100
) -> None:
    """
    Fetch *all* historical messages from the given room_ids (or all joined rooms if None),
    then write them to a CSV, including a human-readable 'date' column in the first position.
    """
    if not room_ids:
        room_ids = list(client.rooms.keys())
        logger.info(f"No room_ids specified. Using all joined rooms: {room_ids}")

    all_records = []
    for rid in room_ids:
        logger.info(f"Fetching *all* messages for room: {rid}")
        room_history = await _fetch_room_history_paged(client, rid, page_size=page_size)
        all_records.extend(room_history)

    if not all_records:
        logger.warning("No messages fetched. CSV file will not be updated.")
        return

    # Build the DataFrame with a new column 'date' in the first column
    df = pd.DataFrame(
        all_records, 
        columns=["date", "room_id", "event_id", "sender", "timestamp", "body"]  # order matters
    )
    logger.info(f"Fetched total {len(df)} messages across {len(room_ids)} room(s).")

    if os.path.exists(MESSAGES_CSV):
        try:
            existing_df = pd.read_csv(MESSAGES_CSV)
            logger.debug(f"Existing CSV loaded with {len(existing_df)} records.")
        except pd.errors.EmptyDataError:
            # Handle empty CSV by creating an empty DataFrame with the correct columns
            existing_df = pd.DataFrame(columns=["date", "room_id", "event_id", "sender", "timestamp", "body"])
            logger.warning(f"{MESSAGES_CSV} is empty. Creating a new DataFrame with columns.")

        combined_df = pd.concat([existing_df, df], ignore_index=True)
        combined_df.drop_duplicates(subset=["room_id", "event_id"], keep="last", inplace=True)
        combined_df.to_csv(MESSAGES_CSV, index=False)
        logger.info(f"Appended new records to existing {MESSAGES_CSV}. New total: {len(combined_df)}")
    else:
        # If CSV doesn't exist, create it with the new records
        df.to_csv(MESSAGES_CSV, index=False)
        logger.info(f"Wrote all records to new CSV {MESSAGES_CSV}.")


async def _fetch_room_history_paged(
    client, 
    room_id: str, 
    page_size: int
) -> list[dict]:
    """
    Helper to page backwards in time until no more messages or we hit the server's earliest.
    For each event, create a 'date' field in ISO format from the server timestamp.
    """
    from nio import RoomMessageText
    all_events = []
    end_token = None

    while True:
        try:
            response = await client.room_messages(
                room_id=room_id,
                start=end_token,
                limit=page_size,
                direction="b"
            )
            if not isinstance(response, RoomMessagesResponse):
                logger.warning(f"Got a non-success response: {response}")
                break

            chunk = response.chunk
            if not chunk:
                logger.info(f"No more chunk for {room_id}, done paging.")
                break

            for ev in chunk:
                if isinstance(ev, RoomMessageText):
                    # Convert 'server_timestamp' (ms) => human-readable UTC time
                    # e.g. '2025-01-11 21:29:33'
                    dt_utc = datetime.datetime.utcfromtimestamp(ev.server_timestamp / 1000.0)
                    dt_str = dt_utc.strftime("%Y-%m-%d %H:%M:%S")

                    all_events.append({
                        "date": dt_str,                   # new field
                        "room_id": room_id,
                        "event_id": ev.event_id,
                        "sender": ev.sender,
                        "timestamp": ev.server_timestamp, # keep the original numeric
                        "body": ev.body
                    })

            end_token = response.end
            if not end_token:
                logger.info(f"Got empty 'end' token for {room_id}, done paging.")
                break

            logger.debug(f"Fetched {len(chunk)} messages this page for room={room_id}, new end={end_token}")
            await asyncio.sleep(0.25)

        except Exception as e:
            logger.exception(f"Error in room_messages paging for {room_id}: {e}")
            break

    return all_events

# ──────────────────────────────────────────────────────────
# LIST USERS
# ──────────────────────────────────────────────────────────
async def list_users() -> list[dict]:
    """
    Returns a list of all users on the Synapse server, using the admin API.
    ...
    """
    homeserver_url = "http://localhost:8008"  # adjust if needed
    try:
        with open("data/director_token.json", "r") as f:
            data = json.load(f)
        admin_token = data["access_token"]
    except Exception as e:
        logger.error(f"Unable to load admin token from director_token.json: {e}")
        return []

    url = f"{homeserver_url}/_synapse/admin/v2/users"
    headers = {"Authorization": f"Bearer {admin_token}"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    resp_data = await resp.json()
                    raw_users = resp_data.get("users", [])
                    users_list = []
                    for u in raw_users:
                        users_list.append({
                            "user_id": u.get("name"),
                            "displayname": u.get("displayname"),
                            "admin": u.get("admin", False),
                            "deactivated": u.get("deactivated", False),
                        })
                    return users_list
                else:
                    text = await resp.text()
                    logger.error(f"Failed to list users (HTTP {resp.status}): {text}")
                    return []
    except Exception as e:
        logger.exception(f"Error calling list_users admin API: {e}")
        return []


# ──────────────────────────────────────────────────────────
# INVITE USER TO ROOM
# ──────────────────────────────────────────────────────────
async def invite_user_to_room(user_id: str, room_id_or_alias: str) -> str:
    """
    Force-join (invite) an existing Matrix user to a room/alias by calling
    the Synapse Admin API (POST /_synapse/admin/v1/join/<room_id_or_alias>)
    with a JSON body: {"user_id": "<user_id>"}

    Unlike a normal Matrix invite, this bypasses user consent. The user is
    automatically joined if they're local to this homeserver.

    Requirements:
      - The user running this code (DIRECTOR_CLIENT) must be a homeserver admin.
      - The user_id must be local to this server.
      - The admin must already be in the room with permission to invite.
    """
    from src.luna_functions import DIRECTOR_CLIENT, getClient  # or your actual import path

    # Ensure we have a valid client with admin credentials
    client = getClient()  # or use DIRECTOR_CLIENT directly
    if not client:
        error_msg = "Error: No DIRECTOR_CLIENT available."
        logger.error(error_msg)
        return error_msg

    admin_token = client.access_token
    if not admin_token:
        error_msg = "Error: No admin token is present in DIRECTOR_CLIENT."
        logger.error(error_msg)
        return error_msg

    homeserver_url = client.homeserver
    # Endpoint for forced join
    endpoint = f"{homeserver_url}/_synapse/admin/v1/join/{room_id_or_alias}"

    payload = {"user_id": user_id}
    headers = {"Authorization": f"Bearer {admin_token}"}

    logger.debug("Force-joining user %s to room %s via %s", user_id, room_id_or_alias, endpoint)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, json=payload) as resp:
                if resp.status in (200, 201):
                    logger.info(f"Successfully forced {user_id} into {room_id_or_alias}.")
                    return f"Forcibly joined {user_id} to {room_id_or_alias}."
                else:
                    text = await resp.text()
                    logger.error(f"Failed to force-join {user_id} to {room_id_or_alias}: {text}")
                    return f"Error {resp.status} forcibly joining {user_id} => {text}"
    except Exception as e:
        logger.exception(f"Exception while forcing {user_id} into {room_id_or_alias}: {e}")
        return f"Exception forcibly joining {user_id} => {e}"

# ──────────────────────────────────────────────────────────
# DELETE MATRIX USER
# ──────────────────────────────────────────────────────────
async def delete_matrix_user(localpart: str) -> str:
    """
    Deletes a user from Synapse using the admin API.
    ...
    """
    from src.luna_functions import get_admin_token  # or however you load it
    admin_token = get_admin_token()

    user_id = f"@{localpart}:localhost"
    url = f"http://localhost:8008/_synapse/admin/v2/users/{user_id}"
    headers = {"Authorization": f"Bearer {admin_token}"}

    import aiohttp
    import logging
    logger = logging.getLogger(__name__)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.delete(url, headers=headers) as resp:
                if resp.status == 200:
                    return f"Deleted Matrix user {user_id} successfully."
                elif resp.status == 404:
                    return f"Matrix user {user_id} not found. Possibly already deleted."
                else:
                    text = await resp.text()
                    return f"Error {resp.status} deleting user {user_id}: {text}"
    except Exception as e:
        logger.exception(f"Error in delete_matrix_user({user_id}): {e}")
        return f"Exception deleting user {user_id}: {e}"

def getClient():
    return DIRECTOR_CLIENT
