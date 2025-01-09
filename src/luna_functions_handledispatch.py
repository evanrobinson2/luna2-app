"""
luna_functions_handledispatch.py

A "positive signal" version of on_room_message to prove the rest
of your mention-handling pipeline fires. It unconditionally logs
that a mention was found, so you can see if your code that runs
AFTER a mention is recognized actually does anything.
"""

import logging
logger = logging.getLogger(__name__)

import os
import pandas as pd
import logging
from src.luna_functions import invite_user_to_room, list_rooms



from src.luna_functions import (
    invite_user_to_room,
    list_rooms,
    post_gpt_reply,
    MESSAGES_CSV 
)

import logging
logger = logging.getLogger(__name__)

from src.luna_functions import invite_user_to_room, list_rooms, DIRECTOR_CLIENT
from src.ai_functions import get_gpt_response  # or wherever your GPT integration resides

async def on_room_message(room, event):
    """
    1) Saves the new message to `luna_messages.csv`, ensuring no duplicates.
    2) Checks mentions in m.mentions["user_ids"] and, if present,
       calls GPT once per user ID, posting replies to the room.
    """

    from nio import RoomMessageText
    if not isinstance(event, RoomMessageText):
        return  # ignore non-text events

    # --------------------------
    #  Step A: Write to local datastore
    # --------------------------
    user_message = event.body or ""
    new_record = [{
        "room_id": room.room_id,
        "event_id": event.event_id,
        "sender": event.sender,
        "timestamp": event.server_timestamp,
        "body": user_message
    }]

    df_new = pd.DataFrame(new_record, columns=["room_id", "event_id", "sender", "timestamp", "body"])

    try:
        if os.path.exists(MESSAGES_CSV):
            existing_df = pd.read_csv(MESSAGES_CSV)
            before_count = len(existing_df)

            combined_df = pd.concat([existing_df, df_new], ignore_index=True)
            # Drop duplicates on (room_id, event_id) to avoid duplicates
            combined_df.drop_duplicates(subset=["room_id", "event_id"], keep="last", inplace=True)
            after_count = len(combined_df)

            combined_df.to_csv(MESSAGES_CSV, index=False)

            if after_count == before_count:
                logger.info(
                    f"Duplicate message detected (event_id={event.event_id}), "
                    "no new row appended to luna_messages.csv."
                )
            else:
                logger.debug(
                    f"Added {after_count - before_count} new message(s) to {MESSAGES_CSV}. "
                    f"New total: {after_count}"
                )
        else:
            df_new.to_csv(MESSAGES_CSV, index=False)
            logger.debug(
                f"No existing CSV found; created {MESSAGES_CSV} with 1 record (event_id={event.event_id})."
            )
    except Exception as e:
        logger.exception(f"Failed to write message (event_id={event.event_id}) to {MESSAGES_CSV}: {e}")

    # --------------------------
    #  Step B: Parse mentions & GPT dispatch
    # --------------------------
    logger.info("Handling on_room_message with multi-mention iteration approach.")

    room_id = room.room_id
    logger.debug(f"User message => '{user_message}' (room_id={room_id})")

    content = event.source.get("content", {})
    mentions_field = content.get("m.mentions", {})
    logger.debug(f"m.mentions => {mentions_field}")

    mentioned_ids = mentions_field.get("user_ids", [])
    if not mentioned_ids:
        logger.debug("No user_ids in m.mentions => no mention recognized.")
        return

    logger.info(f"Mentioned user_ids => {mentioned_ids}")

    # Example triggers
    if "invite me" in user_message.lower():
        result = await invite_user_to_room("@somebody:localhost", room_id)
        logger.info(f"Invite result => {result}")

    if "rooms?" in user_message.lower():
        rooms_data = await list_rooms()
        logger.info(f"Rooms => {rooms_data}")

    # GPT reply per mention
    for mention_id in mentioned_ids:
        logger.info(f"Processing mention for user => {mention_id}")

        gpt_context = [
            {"role": "system", "content": f"You are a helpful bot responding to a mention of {mention_id}."},
            {"role": "user", "content": user_message}
        ]

        try:
            gpt_reply = await get_gpt_response(gpt_context)
            logger.info(f"GPT reply (for mention {mention_id}) => {gpt_reply}")
        except Exception as e:
            logger.exception("Error calling GPT:")
            gpt_reply = f"[Error: {e}]"

        await post_gpt_reply(room_id, gpt_reply)