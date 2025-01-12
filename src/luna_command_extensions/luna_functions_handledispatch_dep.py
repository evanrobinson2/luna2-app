"""
luna_functions_handledispatch.py

A "positive signal" version of on_room_message to prove the rest
of your mention-handling pipeline fires. It unconditionally logs
that a mention was found, so you can see if your code that runs
AFTER a mention is recognized actually does anything.
"""

LUNA_USER_ID = '@lunabot:localhost'

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

from src.luna_functions import invite_user_to_room, list_rooms
from src.ai_functions import get_gpt_response  # or wherever your GPT integration resides
import pandas as pd
import os
import logging
from nio import RoomMessageText
import pandas as pd
import os
import logging
from nio import RoomMessageText
import pandas as pd
import os
import logging
from nio import RoomMessageText



MESSAGES_CSV = "luna_messages.csv"


# Configure logging to write to 'luna.log' only
logger = logging.getLogger('luna_logger')
logger.setLevel(logging.DEBUG)  # Set to DEBUG to capture all levels of logs

# Create file handler which logs even debug messages
fh = logging.FileHandler('luna.log')
fh.setLevel(logging.DEBUG)

# Create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)

# Add the handlers to the logger
if not logger.hasHandlers():
    logger.addHandler(fh)

# Prevent logs from being propagated to the root logger
logger.propagate = False

MESSAGES_CSV = "luna_messages.csv"

# Import external functions from src.luna_functions
from src.luna_functions import invite_user_to_room, list_rooms, post_gpt_reply
from src.ai_functions import get_gpt_response

async def on_room_message_dep_working_silent_luna_inprivate(room, event):
    """
    Handles incoming room messages by:
    1. Saving them to MESSAGES_CSV without duplicates.
    2. Processing mentions to generate and post GPT responses only for new messages.
    """
    if not isinstance(event, RoomMessageText):
        logger.debug("Ignored non-text message.")
        return  # Ignore non-text messages

    user_message = event.body.strip() if event.body else ""
    message_record = {
        "room_id": room.room_id,
        "event_id": event.event_id,
        "sender": event.sender,
        "timestamp": event.server_timestamp,
        "body": user_message
    }

    is_new_message = False  # Flag to determine if GPT should be invoked

    try:
        if os.path.exists(MESSAGES_CSV):
            try:
                existing_df = pd.read_csv(MESSAGES_CSV)
                logger.debug(f"Loaded existing CSV with {len(existing_df)} records.")
            except pd.errors.EmptyDataError:
                # CSV exists but is empty; initialize with headers
                existing_df = pd.DataFrame(columns=["room_id", "event_id", "sender", "timestamp", "body"])
                logger.warning(f"{MESSAGES_CSV} is empty. Initializing with headers.")

            # Check for duplicate 'event_id'
            if event.event_id not in existing_df['event_id'].values:
                is_new_message = True
                # Append the new message without writing headers
                df_new = pd.DataFrame([message_record])
                df_new.to_csv(MESSAGES_CSV, mode='a', header=False, index=False)
                logger.info(f"Appended new message {event.event_id} to {MESSAGES_CSV}.")
            else:
                logger.info(f"Duplicate message {event.event_id} found. Skipping append and GPT processing.")
        else:
            # CSV doesn't exist; create it with headers and write the first message
            is_new_message = True
            df_new = pd.DataFrame([message_record])
            df_new.to_csv(MESSAGES_CSV, mode='w', header=True, index=False)
            logger.info(f"Created {MESSAGES_CSV} and wrote the first message {event.event_id}.")

    except Exception as e:
        logger.exception(f"Failed to save message {event.event_id}: {e}")
        return  # Exit early if saving fails

    # Proceed to process mentions and GPT only if it's a new message
    if is_new_message:
        logger.info("Processing mentions and preparing to call GPT.")

        content = event.source.get("content", {})
        mentions_field = content.get("m.mentions", {})
        mentioned_ids = mentions_field.get("user_ids", [])

        if not mentioned_ids:
            logger.debug("No user_ids in m.mentions => no mention recognized.")
            return  # No mentions to process

        logger.info(f"Mentioned user_ids => {mentioned_ids}")

        # Example triggers based on message content
        if "invite me" in user_message.lower():
            result = await invite_user_to_room("@somebody:localhost", room.room_id)
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

            await post_gpt_reply(room.room_id, gpt_reply)
    else:
        logger.debug("Message already processed. No further action taken.")

async def on_room_message(room, event):
    """
    Handles incoming room messages by:
    1. Saving them to MESSAGES_CSV without duplicates.
    2. Processing mentions to generate and post GPT responses only for new messages.
    3. Automatically responding if there are no mentions and only one other participant.
    4. Ensuring Luna never replies to her own messages, including self-tags.
    """
    if not isinstance(event, RoomMessageText):
        logger.debug("Ignored non-text message.")
        return  # Ignore non-text messages

    # Prevent Luna from responding to her own messages
    if event.sender == '@lunabot:localhost':
        logger.info(f"Ignored message from Luna herself (event_id={event.event_id}).")
        return

    user_message = event.body.strip() if event.body else ""
    message_record = {
        "room_id": room.room_id,
        "event_id": event.event_id,
        "sender": event.sender,
        "timestamp": event.server_timestamp,
        "body": user_message
    }

    is_new_message = False  # Flag to determine if GPT should be invoked

    try:
        if os.path.exists(MESSAGES_CSV):
            try:
                existing_df = pd.read_csv(MESSAGES_CSV)
                logger.debug(f"Loaded existing CSV with {len(existing_df)} records.")
            except pd.errors.EmptyDataError:
                # CSV exists but is empty; initialize with headers
                existing_df = pd.DataFrame(columns=["room_id", "event_id", "sender", "timestamp", "body"])
                logger.warning(f"{MESSAGES_CSV} is empty. Initializing with headers.")

            # Check for duplicate 'event_id'
            if event.event_id not in existing_df['event_id'].values:
                is_new_message = True
                # Append the new message without writing headers
                df_new = pd.DataFrame([message_record])
                df_new.to_csv(MESSAGES_CSV, mode='a', header=False, index=False)
                logger.info(f"Appended new message {event.event_id} to {MESSAGES_CSV}.")
            else:
                logger.info(f"Duplicate message {event.event_id} found. Skipping append and GPT processing.")
        else:
            # CSV doesn't exist; create it with headers and write the first message
            is_new_message = True
            df_new = pd.DataFrame([message_record])
            df_new.to_csv(MESSAGES_CSV, mode='w', header=True, index=False)
            logger.info(f"Created {MESSAGES_CSV} and wrote the first message {event.event_id}.")

    except Exception as e:
        logger.exception(f"Failed to save message {event.event_id}: {e}")
        return  # Exit early if saving fails

    # Proceed to process mentions and GPT only if it's a new message
    if is_new_message:
        logger.info("Processing mentions and preparing to call GPT.")

        content = event.source.get("content", {})
        mentions_field = content.get("m.mentions", {})
        mentioned_ids = mentions_field.get("user_ids", [])

        if mentioned_ids:
            # Remove Luna's own ID from mentions to prevent self-response
            mentioned_ids = [uid for uid in mentioned_ids if uid != LUNA_USER_ID]
            if not mentioned_ids:
                logger.info("Only Luna was mentioned. No action taken.")
                return

            logger.info(f"Processed mentions (excluding Luna): {mentioned_ids}")

            # Example triggers based on message content
            if "invite me" in user_message.lower():
                result = await invite_user_to_room("@somebody:localhost", room.room_id)
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

                await post_gpt_reply(room.room_id, gpt_reply)
        else:
            # No mentions; check if only one other participant is in the room
            try:
                participants = room.users  # Assuming 'users' is a dict of user_id to user info
                participant_count = len(participants)
                logger.debug(f"Room has {participant_count} participants.")

                if participant_count == 2:
                    # Only Luna and one other participant
                    logger.info("No mentions and only one other participant. Preparing to respond.")

                    gpt_context = [
                        {"role": "system", "content": "You are Luna, a helpful assistant."},
                        {"role": "user", "content": user_message}
                    ]

                    try:
                        gpt_reply = await get_gpt_response(gpt_context)
                        logger.info(f"GPT reply => {gpt_reply}")
                    except Exception as e:
                        logger.exception("Error calling GPT:")
                        gpt_reply = f"[Error: {e}]"

                    await post_gpt_reply(room.room_id, gpt_reply)
                else:
                    logger.debug("More than two participants in the room. No automatic response triggered.")
            except AttributeError:
                logger.error("Room object does not have 'users' attribute.")
            except Exception as e:
                logger.exception(f"Error processing participant count: {e}")

    else:
        logger.debug("Message already processed. No further action taken.")

async def on_room_message_dep_double_responding(room, event):
    """
    Handles incoming room messages by saving them to a CSV file,
    ensuring no duplicate entries based on 'event_id', and processing mentions
    to generate and post GPT responses.
    """
    if not isinstance(event, RoomMessageText):
        return  # Ignore non-text messages

    user_message = event.body or ""

    message_record = {
        "room_id": room.room_id,
        "event_id": event.event_id,
        "sender": event.sender,
        "timestamp": event.server_timestamp,
        "body": user_message
    }

    try:
        if os.path.exists(MESSAGES_CSV):
            try:
                existing_df = pd.read_csv(MESSAGES_CSV)
                logger.debug(f"Loaded existing CSV with {len(existing_df)} records.")
            except pd.errors.EmptyDataError:
                # CSV exists but is empty; initialize with headers
                existing_df = pd.DataFrame(columns=["room_id", "event_id", "sender", "timestamp", "body"])
                logger.warning(f"{MESSAGES_CSV} is empty. Initializing with headers.")

            # Check for duplicate 'event_id'
            if event.event_id not in existing_df['event_id'].values:
                # Append the new message without writing headers
                df_new = pd.DataFrame([message_record])
                df_new.to_csv(MESSAGES_CSV, mode='a', header=False, index=False)
                logger.info(f"Appended new message {event.event_id} to {MESSAGES_CSV}.")
            else:
                logger.info(f"Duplicate message {event.event_id} found. Skipping append.")
        else:
            # CSV doesn't exist; create it with headers and write the first message
            df_new = pd.DataFrame([message_record])
            df_new.to_csv(MESSAGES_CSV, mode='w', header=True, index=False)
            logger.info(f"Created {MESSAGES_CSV} and wrote the first message {event.event_id}.")
    except Exception as e:
        logger.exception(f"Failed to save message {event.event_id}: {e}")

    # --------------------------
    #  Step B: Parse mentions & GPT dispatch
    # --------------------------
    logger.info("Handling on_room_message with multi-mention iteration approach.")

    content = event.source.get("content", {})
    mentions_field = content.get("m.mentions", {})
    logger.debug(f"m.mentions => {mentions_field}")

    mentioned_ids = mentions_field.get("user_ids", [])
    if not mentioned_ids:
        logger.debug("No user_ids in m.mentions => no mention recognized.")
        return

    logger.info(f"Mentioned user_ids => {mentioned_ids}")

    # Example triggers based on message content
    if "invite me" in user_message.lower():
        result = await invite_user_to_room("@somebody:localhost", room.room_id)
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

        await post_gpt_reply(room.room_id, gpt_reply)

async def on_room_message_dep(room, event):
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
    if "!invite me" in user_message.lower():
        result = await invite_user_to_room("@somebody:localhost", room_id)
        logger.info(f"Invite result => {result}")

    if "!rooms" in user_message.lower():
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