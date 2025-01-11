
import logging
from nio import RoomMessageText

logger = logging.getLogger(__name__)

LUNA_USER_ID = "@lunabot:localhost"
ROUTE_LIMIT = 25  # Hard limit on routes
MAX_USERS_TO_ROUTE = 0   # Global or external; in production you'd store this more robustly

async def on_room_message_stub_logonly(room, event):
    """
    A minimal demonstration of your routing algorithm with logging only.
    - Logs that we received a message and 'pretends' to write to CSV.
    - Distinguishes between a 2-participant (auto-respond) channel and a multi-participant (mention-based).
    - Tracks MAX_USERS_TO_ROUTE to emulate infinite-loop prevention (just logs warnings, doesn't enforce).
    """

    # 1) Confirm it's a text event
    if not isinstance(event, RoomMessageText):
        logger.debug("Ignoring non-text event (event_id=%s).", event.event_id)
        return

    # 2) Log the incoming message
    logger.info(
        "Received text event: room_id=%s, event_id=%s, sender=%s, body=%r",
        room.room_id, event.event_id, event.sender, event.body
    )
    logger.debug("Pretending to write this message to CSV... (no real I/O)")

    # 3) Count participants
    #    'room.users' is a dict of user_id -> user_info in Matrix; adjust if your platform differs
    participants = getattr(room, "users", {})
    participant_count = len(participants)
    logger.info("Room %s has %d participants.", room.room_id, participant_count)

    # 4) If exactly 2 participants => auto respond
    if participant_count == 2:
        logger.info("2-participant channel => Luna automatically responds (stub).")

        # Emulate route count increment
        global MAX_USERS_TO_ROUTE
        MAX_USERS_TO_ROUTE += 1
        logger.debug("Incremented MAX_USERS_TO_ROUTE to %d (no enforcement yet).", MAX_USERS_TO_ROUTE)

        # If MAX_USERS_TO_ROUTE hits 10 or 25, log that as well
        if MAX_USERS_TO_ROUTE == 10:
            logger.warning("**Route count is 10 => 'final message' would be posted here in real code.**")
        elif MAX_USERS_TO_ROUTE >= ROUTE_LIMIT:
            logger.warning("**Route limit (%d) reached => conversation halted.**", ROUTE_LIMIT)

        # Log a pretend GPT response
        logger.info("Pretending to generate a GPT-based reply and post it to the channel... Done.")

    else:
        # 5) More than 2 participants => respond only if there's a mention
        logger.info("Multi-participant channel => respond only if @mentioned.")

        # Extract mention info from the event's content
        content = event.source.get("content", {})
        mentions_field = content.get("m.mentions", {})
        mentioned_ids = mentions_field.get("user_ids", [])
        logger.debug("Mentioned IDs => %s", mentioned_ids)

        if not mentioned_ids:
            logger.info("No mentions => Luna (and other bots) remain silent in this group chat.")
            return

        # If we have mentions, pretend to route the message
        logger.info("Detected mentions => routing to each mentioned entity. (Stub)")
        logger.info("All mentions: %s", mentioned_ids)        

        for mention_id in mentioned_ids:
            MAX_USERS_TO_ROUTE += 1
            logger.debug(
                "Pretending to route the message to %s. MAX_USERS_TO_ROUTE=%d",
                mention_id, MAX_USERS_TO_ROUTE
            )

            # Check MAX_USERS_TO_ROUTE for warnings
            if MAX_USERS_TO_ROUTE == 10:
                logger.warning("**Hit MAX_USERS_TO_ROUTE=10 => 'final message' would be posted.**")
            elif MAX_USERS_TO_ROUTE >= ROUTE_LIMIT:
                logger.warning("**Route limit (%d) reached => conversation halted.**", ROUTE_LIMIT)
                # In real code, you'd break or return here if you truly want to stop responding

            # In reality, we might generate a GPT reply as if from mention_id
            logger.info("Pretending to log mention-based response and send it as user %s", mention_id)

    logger.debug("Finished on_room_message_stub_logonly for event_id=%s.", event.event_id)
