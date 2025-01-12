import logging
import os
import pandas as pd
from nio import RoomMessageText

# Assume you have these defined somewhere:
LUNA_USER_ID = "@lunabot:localhost"  
ROUTE_LIMIT = 25
MAX_USERS_TO_ROUTE = 0
MESSAGES_CSV = "data/luna_messages.csv"  # same as in fetch_all_messages_once
logger = logging.getLogger(__name__)

async def on_room_message_stub_logonly(room, event):
    """
    A minimal demonstration of your routing algorithm with logging only:
      - Now *actually* writes new messages to MESSAGES_CSV (checking duplicates).
      - Distinguishes between a 2-participant (auto-respond) channel and multi-participant (mention-based).
      - Strips self-mentions (sender won't re-trigger themselves).
      - Tracks a global route count to emulate infinite-loop prevention (just logs warnings).
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

    # 4) Write message to CSV, skipping duplicates
    new_record = {
        "room_id": room.room_id,
        "event_id": event.event_id,
        "sender": event.sender,
        "timestamp": event.server_timestamp,
        "body": event.body or ""
    }
    df_new = pd.DataFrame([new_record])  # single-row DataFrame

    if os.path.exists(MESSAGES_CSV):
        try:
            existing_df = pd.read_csv(MESSAGES_CSV)
            logger.debug(f"Loaded existing CSV with {len(existing_df)} records.")
        except pd.errors.EmptyDataError:
            # CSV exists but is empty
            existing_df = pd.DataFrame(columns=["room_id", "event_id", "sender", "timestamp", "body"])
            logger.warning(f"{MESSAGES_CSV} was empty. Using fresh columns.")

        # Combine, drop duplicates, write back
        combined_df = pd.concat([existing_df, df_new], ignore_index=True)
        combined_df.drop_duplicates(subset=["room_id", "event_id"], keep="last", inplace=True)
        combined_df.to_csv(MESSAGES_CSV, index=False)
        logger.info(
            f"Wrote new record (event_id={event.event_id}). "
            f"Total messages in {MESSAGES_CSV}: {len(combined_df)}"
        )
    else:
        # If CSV doesn't exist, create it with the new record
        df_new.to_csv(MESSAGES_CSV, index=False)
        logger.info(f"Created {MESSAGES_CSV} with initial message (event_id={event.event_id}).")

    # 5) Count participants
    participants = getattr(room, "users", {})
    participant_count = len(participants)
    logger.info("Room %s has %d participants.", room.room_id, participant_count)

    # 6) If exactly 2 participants => auto-respond
    if participant_count == 2:
        logger.info("2-participant channel => Luna automatically responds (stub).")

        global MAX_USERS_TO_ROUTE
        MAX_USERS_TO_ROUTE += 1
        logger.debug("Incremented MAX_USERS_TO_ROUTE to %d (no enforcement yet).", MAX_USERS_TO_ROUTE)

        if MAX_USERS_TO_ROUTE == 10:
            logger.warning("**Route count is 10 => 'final message' would be posted in real code.**")
        elif MAX_USERS_TO_ROUTE >= ROUTE_LIMIT:
            logger.warning("**Route limit (%d) reached => conversation halted.**", ROUTE_LIMIT)

        # Stub GPT response
        logger.info("Pretending to generate a GPT-based reply and post it to the channel... Done.")

    else:
        # 7) In a group (>=3 participants), respond only if mentioned
        logger.info("Multi-participant channel => respond only if mentioned.")
        content = event.source.get("content", {})
        mentions_field = content.get("m.mentions", {})
        mentioned_ids = mentions_field.get("user_ids", [])
        logger.debug("Mentioned IDs => %s", mentioned_ids)

        if not mentioned_ids:
            logger.info("No mentions => remaining silent in this group chat.")
            return

        # 8) Strip out the event sender from mention list
        filtered_mentions = [m for m in mentioned_ids if m != event.sender]
        if not filtered_mentions:
            logger.info("All mentions were the sender; ignoring.")
            return

        # 9) Pretend to route the message for each mention
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
                # In real code, we might break here to stop further responses
                break

            logger.info("Pretending to log mention-based response and send it as user %s", mention_id)

    logger.debug("Finished on_room_message_stub_logonly for event_id=%s.", event.event_id)
