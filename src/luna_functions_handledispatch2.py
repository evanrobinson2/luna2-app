# luna_functions_handledispatch.py

import asyncio
import logging
import os
import pandas as pd

# From your Matrix/Chat library
from nio import RoomMessageText

# From your own code; adjust paths to match your project:
#   - 'invite_user_to_room', 'list_rooms', and 'post_gpt_reply' are found in src/luna_functions.py
#   - 'get_gpt_response' is found in src/ai_functions.py
#   - 'MESSAGES_CSV' is either defined in src/luna_functions or placed here
from src.luna_functions import invite_user_to_room, list_rooms, post_gpt_reply, MESSAGES_CSV
from src.ai_functions import get_gpt_response

# Setup logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# If you have a separate file handler, set it up here, e.g.:
fh = logging.FileHandler('luna.log')
fh.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
if not logger.hasHandlers():
    logger.addHandler(fh)
logger.propagate = False

# Luna’s Matrix user ID
LUNA_USER_ID = '@lunabot:localhost'


async def on_room_message(room, event):
    """
    Revised dispatch logic:
      1. If the sender is Luna, do nothing (no self-response).
      2. If sender != Luna and participant_count == 1, Luna responds.
      3. If sender != Luna and participant_count > 1:
         - If Luna is tagged, Luna responds.
         - Otherwise, Luna does not respond.
      4. Regardless of whether Luna responds or not, always route the 
         message through other GPT personas.
    """
    if not isinstance(event, RoomMessageText):
        logger.debug("Ignored non-text message.")
        return  # Ignore non-text messages

    # 1) No self-replies
    if event.sender == LUNA_USER_ID:
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

    is_new_message = False

    # ------------------------------
    # STEP A: Save to CSV if new
    # ------------------------------
    try:
        if os.path.exists(MESSAGES_CSV):
            try:
                existing_df = pd.read_csv(MESSAGES_CSV)
                logger.debug(f"Loaded existing CSV with {len(existing_df)} records.")
            except pd.errors.EmptyDataError:
                existing_df = pd.DataFrame(columns=["room_id", "event_id", "sender", "timestamp", "body"])
                logger.warning(f"{MESSAGES_CSV} is empty. Initializing with headers.")

            if event.event_id not in existing_df['event_id'].values:
                is_new_message = True
                df_new = pd.DataFrame([message_record])
                df_new.to_csv(MESSAGES_CSV, mode='a', header=False, index=False)
                logger.info(f"Appended new message {event.event_id} to {MESSAGES_CSV}.")
            else:
                logger.info(f"Duplicate message {event.event_id}; skipping GPT processing.")
        else:
            is_new_message = True
            df_new = pd.DataFrame([message_record])
            df_new.to_csv(MESSAGES_CSV, mode='w', header=True, index=False)
            logger.info(f"Created {MESSAGES_CSV} and wrote the first message {event.event_id}.")
    except Exception as e:
        logger.exception(f"Failed to save message {event.event_id}: {e}")
        return  # If we fail to save, do not proceed

    if not is_new_message:
        logger.debug("Message already processed. No further action taken.")
        return

    logger.info("Processing new message for GPT/response logic.")

    # ------------------------------
    # STEP B: Check triggers, mentions, and participant count
    # ------------------------------
    content = event.source.get("content", {})
    mentions_field = content.get("m.mentions", {})
    mentioned_ids = mentions_field.get("user_ids", [])
    luna_tagged = (LUNA_USER_ID in mentioned_ids)

    # Example triggers
    if "invite me" in user_message.lower():
        result = await invite_user_to_room("@somebody:localhost", room.room_id)
        logger.info(f"Invite result => {result}")

    if "rooms?" in user_message.lower():
        rooms_data = await list_rooms()
        logger.info(f"Rooms => {rooms_data}")

    # Check how many participants in the room
    try:
        participants = room.users  # Usually a dict: user_id -> user object
        participant_count = len(participants)
        logger.debug(f"Room has {participant_count} participants.")
    except AttributeError:
        logger.error("Room object does not have 'users' attribute; skipping participant logic.")
        return
    except Exception as e:
        logger.exception(f"Error reading participant count: {e}")
        return

    # ------------------------------
    # STEP C: Apply the dispatch table
    # ------------------------------

    # 1. participant_count == 2 -> Luna responds
    if participant_count == 2:
        await respond_as_luna(room.room_id, user_message)
        # Always route message to other GPT personas
        await route_message_through_other_gpts(room.room_id, user_message)

    else:  # participant_count > 2 (or possibly 1, but 1 is unusual for multi-user chat)
        if participant_count > 2:
            if luna_tagged:
                # Luna responds
                await respond_as_luna(room.room_id, user_message)
            else:
                logger.info("Room has >2 participants, and Luna not tagged => no direct Luna response.")

            # In all cases, route to other GPT
            await route_message_through_other_gpts(room.room_id, user_message)

        else:
            # If participant_count == 1, that means it's literally the sender alone?
            # Some servers might never let that happen. But if it does:
            logger.info("participant_count=1 => Strange edge case. We'll let Luna respond anyway.")
            await respond_as_luna(room.room_id, user_message)
            await route_message_through_other_gpts(room.room_id, user_message)


async def respond_as_luna(room_id: str, user_message: str):
    """
    Minimal helper function for Luna to produce a GPT-based reply.
    """
    logger.info("Preparing GPT reply on behalf of Luna.")
    gpt_context = [
        {"role": "system", "content": "You are Luna, a helpful assistant."},
        {"role": "user", "content": user_message},
    ]
    try:
        gpt_reply = await get_gpt_response(gpt_context)
        logger.info(f"Luna responding => {gpt_reply}")
    except Exception as e:
        logger.exception("Error calling GPT for Luna’s response:")
        gpt_reply = f"[Error: {e}]"

    await post_gpt_reply(room_id, gpt_reply)


async def route_message_through_other_gpts(room_id: str, user_message: str):
    """
    If you have multiple personas or specialized bots, route the user's message
    to each so they can respond. For now, a stub that logs what would happen.
    """
    logger.info(f"Routing message to other GPT personas in room {room_id}...")
    # Example logic here: 
    #   for persona_id in get_all_personas_in_room(room_id):
    #       persona_context = build_context_for_persona(persona_id, user_message)
    #       persona_reply = await get_gpt_response(persona_context)
    #       await post_gpt_reply(room_id, persona_reply)
    #
    # For now, just logging:
    logger.info("Simulated multi-persona logic (not implemented).")
