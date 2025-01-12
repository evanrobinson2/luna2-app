import logging
import os
import pandas as pd
from nio import RoomMessageText
from src.ai_functions import get_gpt_response
from src.luna_functions import getClient  # We'll retrieve the Matrix client as needed.

logger = logging.getLogger(__name__)

LUNA_USER_ID = "@lunabot:localhost"
ROUTE_LIMIT = 25
MAX_USERS_TO_ROUTE = 0
MESSAGES_CSV = "data/luna_messages.csv"

async def on_room_message_stub_logonly(room, event):
    """
    Production-ready version that:
      - Stores new messages in MESSAGES_CSV (skip duplicates).
      - Skips all GPT logic if the message is a duplicate.
      - If participant_count == 2 => do an actual GPT response for new messages.
      - In groups >= 3 => respond only if mentioned (still stub, but also only on new messages).
      - Strips self-mentions.
      - Uses route-limit checks for ping-pong.
    """

    # 1) Confirm it's a text event
    if not isinstance(event, RoomMessageText):
        logger.debug("Ignoring non-text event (event_id=%s).", event.event_id)
        return

    # 2) Ignore if the sender is the bot itself
    if event.sender == LUNA_USER_ID:
        logger.info("Ignoring self-message from the bot. event_id=%s", event.event_id)
        return

    # 3) Log the incoming message
    logger.info(
        "Received text event: room_id=%s, event_id=%s, sender=%s, body=%r",
        room.room_id, event.event_id, event.sender, event.body
    )

    # 4) Prepare one-row DataFrame for this event
    new_record = {
        "room_id": room.room_id,
        "event_id": event.event_id,
        "sender": event.sender,
        "timestamp": event.server_timestamp,
        "body": event.body or ""
    }
    df_new = pd.DataFrame([new_record])

    # 5) Check if MESSAGES_CSV exists, then load/merge
    is_new_message = False
    if os.path.exists(MESSAGES_CSV):
        try:
            existing_df = pd.read_csv(MESSAGES_CSV)
            logger.debug(f"Loaded existing CSV with {len(existing_df)} records.")
        except pd.errors.EmptyDataError:
            existing_df = pd.DataFrame(columns=["room_id", "event_id", "sender", "timestamp", "body"])
            logger.warning(f"{MESSAGES_CSV} was empty. Using fresh columns.")
        initial_count = len(existing_df)

        combined_df = pd.concat([existing_df, df_new], ignore_index=True)
        combined_df.drop_duplicates(subset=["room_id", "event_id"], keep="last", inplace=True)
        final_count = len(combined_df)

        # If the final count is larger, we truly added a new record
        if final_count > initial_count:
            is_new_message = True
            combined_df.to_csv(MESSAGES_CSV, index=False)
            logger.info(
                f"Appended new record (event_id={event.event_id}). "
                f"Total messages in {MESSAGES_CSV}: {final_count}"
            )
        else:
            logger.info(
                f"Duplicate message (event_id={event.event_id}); skipping GPT and mention logic."
            )
    else:
        # CSV doesn't exist yet, so this is definitely new.
        df_new.to_csv(MESSAGES_CSV, index=False)
        is_new_message = True
        logger.info(
            f"Created {MESSAGES_CSV} with initial message (event_id={event.event_id})."
        )

    # 6) If it's NOT new, we skip all further logic
    if not is_new_message:
        return

    # 7) Count participants
    participants = getattr(room, "users", {})
    participant_count = len(participants)
    logger.info("Room %s has %d participants.", room.room_id, participant_count)

    # 8) If exactly 2 participants => GPT respond
    if participant_count == 2:
        logger.info("2-participant channel => generating a GPT response.")
        global MAX_USERS_TO_ROUTE
        MAX_USERS_TO_ROUTE += 1
        logger.debug("Incremented MAX_USERS_TO_ROUTE to %d.", MAX_USERS_TO_ROUTE)

        if MAX_USERS_TO_ROUTE == 10:
            logger.warning("**Route count is 10 => in real code, might stop soon.**")
        elif MAX_USERS_TO_ROUTE >= ROUTE_LIMIT:
            logger.warning("**Route limit (%d) reached => conversation halted.**", ROUTE_LIMIT)
            return

        # Actual GPT call
        try:
            gpt_context = [
                {"role": "system", "content": "You are a helpful AI assistant named Luna."},
                {"role": "user", "content": event.body or ""}
            ]
            gpt_reply = await get_gpt_response(gpt_context)
            logger.info("GPT REPLY => %s", gpt_reply)

            client = getClient()
            if client:
                await client.room_send(
                    room_id=room.room_id,
                    message_type="m.room.message",
                    content={"msgtype": "m.text", "body": gpt_reply},
                )
                logger.info("Posted GPT reply to private room %s", room.room_id)
            else:
                logger.warning("No client available to send GPT response.")

        except Exception as e:
            logger.exception("Failed to get or post GPT reply: %s", e)

    else:
        # 9) In a group (>=3 participants), respond only if mentioned (stub logic)
        logger.info("Multi-participant channel => respond only if mentioned.")
        content = event.source.get("content", {})
        mentions_field = content.get("m.mentions", {})
        mentioned_ids = mentions_field.get("user_ids", [])
        logger.debug("Mentioned IDs => %s", mentioned_ids)

        if not mentioned_ids:
            logger.info("No mentions => remaining silent in this group chat.")
            return

        filtered_mentions = [m for m in mentioned_ids if m != event.sender]
        if not filtered_mentions:
            logger.info("All mentions were the sender; ignoring.")
            return

        logger.info("Detected mentions => routing to each mentioned entity. (Stub)")
        logger.info("Final mention list (post-filter): %s", filtered_mentions)

        for mention_id in filtered_mentions:
            MAX_USERS_TO_ROUTE += 1
            logger.debug(
                "Pretending to route the message to %s. MAX_USERS_TO_ROUTE=%d",
                mention_id, MAX_USERS_TO_ROUTE
            )

            if MAX_USERS_TO_ROUTE == 10:
                logger.warning("**Hit MAX_USERS_TO_ROUTE=10 => 'final message' would be posted.**")
            elif MAX_USERS_TO_ROUTE >= ROUTE_LIMIT:
                logger.warning("**Route limit (%d) reached => conversation halted.**", ROUTE_LIMIT)
                break

            logger.info("Pretending to log mention-based response and send it as user %s", mention_id)

    logger.debug("Finished on_room_message_stub_logonly for event_id=%s.", event.event_id)
