import logging
import os
import time
import pandas as pd
import aiohttp
from urllib.parse import quote

from nio import RoomMessageText
from nio.responses import RoomSendResponse

from src.ai_functions import get_gpt_response
from src.luna_functions import getClient

logger = logging.getLogger(__name__)

# ---- Global Constants ----
LUNA_USER_ID = "@lunabot:localhost"
MESSAGES_CSV = "data/luna_messages.csv"
ROUTE_LIMIT = 25

# A simple global route counter to help prevent infinite loop “ping-pong.”
MAX_USERS_TO_ROUTE = 0

async def on_room_message(room, event):
    """
    Main entry point for handling an inbound text message:
      1. Check if it's new (write to CSV if so).
      2. If not new, skip responding.
      3. If private chat (2 participants) => single GPT call as Luna.
      4. If group chat (>=3 participants) => respond only if mentioned,
         building GPT context for each mention.
      5. Log any GPT-based replies to the same CSV to avoid duplicates on restart.
    """
    # 1) Confirm it's a text event
    if not isinstance(event, RoomMessageText):
        logger.debug("on_room_message(): on_room_message(): Ignoring non-text event (event_id=%s).", event.event_id)
        return

    # 2) Ignore if the sender is the bot itself
    if event.sender == LUNA_USER_ID:
        logger.info("Ignoring self-message from the bot. event_id=%s", event.event_id)
        return

    # 3) Log inbound message
    logger.info(
        "Received text event: room_id=%s, event_id=%s, sender=%s, body=%r",
        room.room_id, event.event_id, event.sender, event.body
    )

    # 4) Store inbound message in CSV (skip duplicates), see Part C
    is_new_message = await store_inbound_message(room, event)
    if not is_new_message:
        # If it's a duplicate, skip all GPT logic to avoid re-responding
        logger.info("Already processed event_id=%s => no further action.", event.event_id)
        return

    # 5) Decide how to respond based on participant count
    participants = getattr(room, "users", {})
    participant_count = len(participants)
    logger.info("Room %s has %d participants.", room.room_id, participant_count)

    if participant_count == 2:
        # 5A) Private chat => single GPT response as Luna
        await handle_private_gpt_response(room, event)
    else:
        # 5B) Group chat => respond only if mentioned
        await handle_group_mentions(room, event)

    logger.debug("on_room_message(): on_room_message(): Finished on_room_message for event_id=%s.", event.event_id)

async def store_inbound_message(room, event) -> bool:
    """
    Writes the inbound message to CSV if it's new.
    Returns True if newly written, False if it's a duplicate.

    This ensures we don't reprocess the same message on restart.
    """
    new_record = {
        "room_id": room.room_id,
        "event_id": event.event_id,
        "sender": event.sender,
        "timestamp": event.server_timestamp,
        "body": event.body or ""
    }
    df_new = pd.DataFrame([new_record])

    if not os.path.exists(MESSAGES_CSV):
        # If CSV doesn't exist, create it and return True
        df_new.to_csv(MESSAGES_CSV, index=False)
        logger.info(f"Created {MESSAGES_CSV} with event_id={event.event_id}.")
        return True

    # If CSV does exist, load, merge, drop duplicates
    try:
        existing_df = pd.read_csv(MESSAGES_CSV)
        logger.debug(f"Loaded existing CSV with {len(existing_df)} records.")
    except pd.errors.EmptyDataError:
        existing_df = pd.DataFrame(columns=["room_id", "event_id", "sender", "timestamp", "body"])
        logger.warning(f"{MESSAGES_CSV} was empty. Using fresh columns.")

    before_count = len(existing_df)
    combined_df = pd.concat([existing_df, df_new], ignore_index=True)
    combined_df.drop_duplicates(subset=["room_id", "event_id"], keep="last", inplace=True)
    after_count = len(combined_df)

    if after_count > before_count:
        # We added a new row
        combined_df.to_csv(MESSAGES_CSV, index=False)
        logger.info(f"Appended new inbound record to CSV => event_id={event.event_id}.")
        return True
    else:
        logger.info(f"Detected duplicate inbound event_id={event.event_id}, skipping GPT response.")
        return False

async def store_outbound_message(room_id: str, sender: str, body: str, event_id: str):
    """
    Appends a newly posted GPT message (outbound) to CSV, similarly skipping duplicates.
    If no event_id is available, generate a fallback to keep the row unique.
    """
    if not event_id:
        # If we never got an event_id, make a fallback with a timestamp
        event_id = f"{sender}-{time.time_ns()}"

    new_record = {
        "room_id": room_id,
        "event_id": event_id,
        "sender": sender,
        "timestamp": int(time.time() * 1000),  # local fallback
        "body": body
    }
    df_new = pd.DataFrame([new_record])

    if not os.path.exists(MESSAGES_CSV):
        df_new.to_csv(MESSAGES_CSV, index=False)
        logger.info(
            f"Created {MESSAGES_CSV} and stored outbound event_id={event_id} from sender={sender}."
        )
        return

    # Merge logic
    try:
        existing_df = pd.read_csv(MESSAGES_CSV)
    except pd.errors.EmptyDataError:
        existing_df = pd.DataFrame(columns=["room_id", "event_id", "sender", "timestamp", "body"])
        logger.warning(f"{MESSAGES_CSV} was empty. Using fresh columns.")

    before_count = len(existing_df)
    combined_df = pd.concat([existing_df, df_new], ignore_index=True)
    combined_df.drop_duplicates(subset=["room_id", "event_id"], keep="last", inplace=True)
    after_count = len(combined_df)

    if after_count > before_count:
        combined_df.to_csv(MESSAGES_CSV, index=False)
        logger.info(
            f"Appended outbound GPT message => event_id={event_id}, sender={sender}. "
            f"CSV now has {after_count} rows."
        )
    else:
        logger.info(
            f"Detected duplicate outbound event_id={event_id}, skipping store."
        )

async def handle_private_gpt_response(room, event):
    """
    Called if the room only has 2 participants => we do a straightforward
    GPT response as 'Luna' (the bot user).
    """
    global MAX_USERS_TO_ROUTE
    MAX_USERS_TO_ROUTE += 1

    if MAX_USERS_TO_ROUTE == 10:
        logger.warning("Route count=10 => might stop soon.")
    elif MAX_USERS_TO_ROUTE >= ROUTE_LIMIT:
        logger.warning("Route limit=%d reached => conversation halted.", ROUTE_LIMIT)
        return

    user_text = event.body or ""
    gpt_context = [
        {"role": "system", "content": "You are Luna, a helpful AI assistant."},
        {"role": "user", "content": user_text}
    ]

    try:
        gpt_reply = await get_gpt_response(gpt_context)
        logger.info("GPT REPLY => %s", gpt_reply)

        client = getClient()
        if not client:
            logger.warning("No client => cannot post GPT response.")
            return

        # Send the GPT reply as Luna
        resp = await client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": gpt_reply},
        )
        logger.info("Posted GPT reply to room %s", room.room_id)

        # Attempt to log the outbound message
        if isinstance(resp, RoomSendResponse) and hasattr(resp, "event_id"):
            reply_event_id = resp.event_id
        else:
            reply_event_id = f"{LUNA_USER_ID}-{time.time_ns()}"

        await store_outbound_message(
            room_id=room.room_id,
            sender=LUNA_USER_ID,
            body=gpt_reply,
            event_id=reply_event_id
        )

    except Exception as e:
        logger.exception("Failed to produce or send GPT reply: %s", e)

async def handle_group_mentions(room, event):
    """
    Called if the room has >=3 participants => respond only if the message
    includes mention(s). Each mention triggers a GPT call posted as that mention_id,
    using Synapse admin impersonation (not recommended for real production E2E).
    """
    logger.info("Group chat => mention-based logic.")
    content = event.source.get("content", {})
    mentions_field = content.get("m.mentions", {})
    mentioned_ids = mentions_field.get("user_ids", [])
    logger.debug("on_room_message(): on_room_message(): Mentioned IDs => %s", mentioned_ids)

    if not mentioned_ids:
        logger.info("No mentions => remain silent.")
        return

    # Strip out the sender to avoid re-triggering themselves
    sender_id = event.sender
    filtered_mentions = [m for m in mentioned_ids if m != sender_id]
    if not filtered_mentions:
        logger.info("All mentions were the sender => ignoring.")
        return

    global MAX_USERS_TO_ROUTE
    for mention_id in filtered_mentions:
        MAX_USERS_TO_ROUTE += 1
        if MAX_USERS_TO_ROUTE == 10:
            logger.warning("**Hit MAX_USERS_TO_ROUTE=10 => might stop soon.**")
        elif MAX_USERS_TO_ROUTE >= ROUTE_LIMIT:
            logger.warning("**Route limit (%d) reached => halting.**", ROUTE_LIMIT)
            break

        try:
            # Build a small GPT context
            group_context = [
                {"role": "system", "content": f"You are {mention_id}, a specialized AI assistant in a group chat."},
                {"role": "user", "content": event.body or ""}
            ]
            gpt_reply = await get_gpt_response(group_context)
            logger.info("GPT mention-based REPLY => %s", gpt_reply)

            # --- Admin Impersonation instead of normal room_send ---
            from src.luna_functions import getClient
            admin_token = getClient()
            if not admin_token:
                logger.warning("No admin token => cannot impersonate mention-based GPT response.")
                continue  # Skip this mention

            # We'll need the homeserver URL from your existing global client
            from src.luna_functions import getClient
            client = getClient()
            if not client or not client.homeserver:
                logger.warning("No valid homeserver => cannot impersonate mention-based GPT response.")
                continue

            homeserver_url = client.homeserver

            # # Now call a helper that does the admin API call
            # mention_event_id = await admin_impersonate_send(
            #     homeserver_url=homeserver_url,
            #     admin_token=admin_token,
            #     room_id=room.room_id,
            #     impersonated_sender=mention_id,
            #     body_text=gpt_reply
            # )

            mention_event_id = await admin_impersonate_send_v2(
                homeserver_url=client.homeserver,
                admin_token=admin_token,
                room_id=room.room_id,
                impersonated_sender=mention_id,
                body_text=gpt_reply
            )

            # Store the outgoing message in CSV
            await store_outbound_message(
                room_id=room.room_id,
                sender=mention_id,
                body=gpt_reply,
                event_id=mention_event_id
            )

        except Exception as e:
            logger.exception("Failed mention-based GPT reply: %s", e)

def build_context_for_message(user_message: str, persona: str) -> list[dict]:
    """
    Example function if you'd prefer a single place to define the GPT conversation context.
    """
    system_prompt = f"You are {persona}, a helpful AI assistant. Only speak for that persona."
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message or ""}
    ]


import aiohttp
import time
import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)

async def admin_impersonate_send_v2(
    homeserver_url: str,
    admin_token: str,
    room_id: str,
    impersonated_sender: str,
    body_text: str,
    txn_id: str = None
) -> str:
    """
    Use the older "PUT /_synapse/admin/v1/rooms/{roomId}/send/{eventType}/{txnId}" pattern
    to forge a message from 'impersonated_sender' in 'room_id'.
    """

    if not txn_id:
        txn_id = str(time.time_ns())  # unique fallback

    encoded_room_id = quote(room_id)
    event_type = "m.room.message"
    
    endpoint = (
        f"{homeserver_url}/_synapse/admin/v1/rooms/"
        f"{encoded_room_id}/send/{event_type}/{txn_id}"
    )

    payload = {
        "sender": impersonated_sender,
        "content": {
            "msgtype": "m.text",
            "body": body_text
        }
    }
    headers = {"Authorization": f"Bearer {admin_token}"}

    func_prefix = "[admin_impersonate_send_old]"
    logger.debug(
        "%s Attempting old-style PUT impersonation => endpoint=%s, sender=%s, room_id=%s",
        func_prefix, endpoint, impersonated_sender, room_id
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.put(endpoint, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    event_id = data.get("event_id")
                    if event_id:
                        logger.info(
                            "%s SUCCESS => posted as '%s' in room='%s' event_id=%s",
                            func_prefix, impersonated_sender, room_id, event_id
                        )
                        return event_id
                    else:
                        fallback_id = f"{impersonated_sender}-{time.time_ns()}"
                        logger.warning(
                            "%s No event_id in response => using fallback=%s", 
                            func_prefix, fallback_id
                        )
                        return fallback_id
                else:
                    text = await resp.text()
                    logger.error(
                        "%s HTTP %d => %s (sender='%s', room_id='%s')",
                        func_prefix, resp.status, text, impersonated_sender, room_id
                    )
                    return f"{impersonated_sender}-err-{time.time_ns()}"
    except Exception as e:
        logger.exception("%s EXCEPTION => %s", func_prefix, e)
        return f"{impersonated_sender}-exc-{time.time_ns()}"



async def admin_impersonate_send(
    homeserver_url: str,
    admin_token: str,
    room_id: str,
    impersonated_sender: str,
    body_text: str
) -> str:
    """
    [admin_impersonate_send] 
    Posts a new 'm.room.message' event to 'room_id' while forging 'impersonated_sender'
    as the 'sender'. Returns the event_id or a fallback if none is provided.
    
    Requirements:
      - 'admin_token' must be from a server admin user in Synapse.
      - Bypasses typical auth checks and won't integrate well with E2E encryption.
    """

    function_prefix = "[admin_impersonate_send]"
    endpoint = f"{homeserver_url}/_synapse/admin/v1/rooms/{quote(room_id)}/send_event"  
    payload = {
        "event_type": "m.room.message",
        "sender": impersonated_sender,
        "content": {
            "msgtype": "m.text",
            "body": body_text
        }
    }
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Optional: log minimal debug info about the endpoint/payload:
    logger.debug(
        "%s Attempting impersonation: endpoint=%s, impersonated_sender=%s, room_id=%s",
        function_prefix, endpoint, impersonated_sender, room_id
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    event_id = data.get("event_id")
                    if event_id:
                        logger.info(
                            "%s SUCCESS => posted as '%s' in room='%s' event_id=%s",
                            function_prefix, impersonated_sender, room_id, event_id
                        )
                        return event_id
                    else:
                        fallback_id = f"{impersonated_sender}-{time.time_ns()}"
                        logger.warning(
                            "%s No event_id in 200 OK response => using fallback=%s",
                            function_prefix, fallback_id
                        )
                        return fallback_id
                else:
                    text = await resp.text()
                    logger.error(
                        "%s HTTP %d => %s (sender='%s', room_id='%s')",
                        function_prefix, resp.status, text, impersonated_sender, room_id
                    )
                    return f"{impersonated_sender}-err-{time.time_ns()}"
    except Exception as e:
        logger.exception("%s EXCEPTION => %s", function_prefix, e)
        return f"{impersonated_sender}-exc-{time.time_ns()}"


async def admin_impersonate_send_dep(
    homeserver_url: str,
    admin_token: str,
    room_id: str,
    impersonated_sender: str,
    body_text: str
) -> str:
    """
    Posts a new 'm.room.message' event to 'room_id' while forging 'impersonated_sender'
    as the 'sender'. Returns the event_id or a fallback if none is provided.

    Requirements:
      - 'admin_token' must be from a server admin user in Synapse.
      - Bypasses typical auth checks, won't integrate well with E2E encryption.
    """
    from urllib.parse import quote

    endpoint = f"{homeserver_url}/_synapse/admin/v1/rooms/{quote(room_id)}/send_event"
    payload = {
        "event_type": "m.room.message",
        "sender": impersonated_sender,
        "content": {
            "msgtype": "m.text",
            "body": body_text
        }
    }
    headers = {"Authorization": f"Bearer {admin_token}"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    event_id = data.get("event_id")
                    if event_id:
                        logger.info("Impersonation success => %s posted in %s as event_id=%s",
                                    impersonated_sender, room_id, event_id)
                        return event_id
                    else:
                        fallback_id = f"{impersonated_sender}-{time.time_ns()}"
                        logger.warning("No event_id in response => using fallback=%s", fallback_id)
                        return fallback_id
                else:
                    text = await resp.text()
                    logger.error("Impersonation => HTTP %d => %s", resp.status, text)
                    return f"{impersonated_sender}-err-{time.time_ns()}"
    except Exception as e:
        logger.exception("Exception in admin_impersonate_send: %s", e)
        return f"{impersonated_sender}-exc-{time.time_ns()}"