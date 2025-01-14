import logging
import time
from nio import RoomMessageText, RoomSendResponse

# from luna import bot_messages_store
from luna import bot_messages_store2

logger = logging.getLogger(__name__)

import logging
import time
from nio import RoomMessageText, RoomSendResponse

logger = logging.getLogger(__name__)

async def handle_bot_room_message(bot_client, bot_localpart, room, event):
    """
    Minimal “mention or DM” logic w/ JSON-based message store:
      1) Skip non-text or self-messages.
      2) Check if event_id was already stored for this bot—if so, skip responding.
      3) Otherwise, store this inbound message (append_message).
      4) If DM or mention => reply.
      5) (Optional) If you want to store the *outbound* message too,
         you can do so after calling `room_send`.
    """

    # 1) Must be text, must not be from ourselves
    if not isinstance(event, RoomMessageText):
        return
    bot_full_id = bot_client.user  # e.g. "@blended_malt:localhost"
    if event.sender == bot_full_id:
        logger.debug(f"Bot '{bot_localpart}' ignoring its own message in {room.room_id}")
        return

    # 2) Check for duplicates by event_id
    existing = bot_messages_store2.get_messages_for_bot(bot_localpart)
    if any(m["event_id"] == event.event_id for m in existing):
        logger.info(
            f"Bot '{bot_localpart}' sees event_id={event.event_id}, "
            "already processed => skipping."
        )
        return

    # 3) Store this inbound message in data/bot_messages.json
    bot_messages_store2.append_message(
        bot_localpart=bot_localpart,
        room_id=room.room_id,
        event_id=event.event_id,
        sender=event.sender,
        timestamp=event.server_timestamp,
        body=event.body or ""
    )
    logger.debug(f"Bot '{bot_localpart}' stored inbound event_id={event.event_id}.")

    # Decide if we should respond: DM => always, or mention => if user ID is in mention_data
    participant_count = len(room.users)
    content = event.source.get("content", {})
    mention_data = content.get("m.mentions", {})
    mentioned_ids = mention_data.get("user_ids", [])

    # If DM => respond, or if mention => respond
    should_respond = False
    if participant_count == 2:
        should_respond = True
    else:
        if bot_full_id in mentioned_ids:
            should_respond = True

    if not should_respond:
        logger.debug(f"Bot '{bot_localpart}' ignoring group message with no mention.")
        return

    # 4) Actually respond
    user_text = event.body or ""
    if participant_count == 2:
        reply_text = (
            f"Hello from '{bot_localpart}' in a direct chat. "
            f"You said: {user_text[:50]}..."
        )
    else:
        reply_text = (
            f"Hello from '{bot_localpart}' in a group chat! "
            f"You mentioned me: {user_text[:50]}..."
        )

    resp = await bot_client.room_send(
        room_id=room.room_id,
        message_type="m.room.message",
        content={"msgtype": "m.text", "body": reply_text},
    )

    # 5) Optional: If you want to record the *outbound* message too,
    #    you could do something like:
    if isinstance(resp, RoomSendResponse) and resp.event_id:
        outbound_eid = resp.event_id
        logger.info(
            f"Bot '{bot_localpart}' posted reply event_id={outbound_eid} to {room.room_id}"
        )
        # If you want to store the outbound message:
        bot_messages_store2.append_message(
            bot_localpart=bot_localpart,
            room_id=room.room_id,
            event_id=outbound_eid,        # the newly assigned event_id
            sender=bot_full_id,           # the bot is the sender
            timestamp=int(time.time()*1000),
            body=reply_text
        )
    else:
        logger.info(
            f"Bot '{bot_localpart}' posted a reply to {room.room_id} (no official event_id)"
        )


async def handle_bot_room_message_dep(bot_client, bot_localpart, room, event):
    """
    Minimal “mention or DM” logic:
      1) Skip non-text or self-messages.
      2) Deduplicate by event_id so we only respond once.
      3) If the room has 2 participants, respond automatically.
      4) Otherwise, respond only if our bot user_id is in the mention list.
    """

    # 1) Must be text, and must not be from ourselves
    if not isinstance(event, RoomMessageText):
        return  # Ignore non-text
    bot_full_id = bot_client.user  # e.g. "@blended_malt:localhost"
    if event.sender == bot_full_id:
        logger.debug(f"Bot '{bot_localpart}' ignoring its own message.")
        return
    
    participant_count = len(room.users)
    content = event.source.get("content", {})
    mention_data = content.get("m.mentions", {})
    mentioned_ids = mention_data.get("user_ids", [])

    # Decide whether to respond
    should_respond = False
    if participant_count == 2:
        should_respond = True  # DM => always respond
    else:
        if bot_full_id in mentioned_ids:
            should_respond = True

    if not should_respond:
        logger.debug(f"Bot '{bot_localpart}' ignoring group message with no mention.")
        return

    # 3) Actually respond
    user_text = event.body or ""
    if participant_count == 2:
        reply_text = (
            f"Hello from '{bot_localpart}' in a direct chat. "
            f"You said: {user_text[:50]}..."
        )
    else:
        reply_text = (
            f"Hello from '{bot_localpart}' in a group chat! "
            f"You mentioned me: {user_text[:50]}..."
        )

    resp = await bot_client.room_send(
        room_id=room.room_id,
        message_type="m.room.message",
        content={"msgtype": "m.text", "body": reply_text},
    )

    if isinstance(resp, RoomSendResponse) and resp.event_id:
        logger.info(
            f"Bot '{bot_localpart}' posted reply event_id={resp.event_id} to {room.room_id}"
        )
    else:
        logger.info(
            f"Bot '{bot_localpart}' posted a reply to {room.room_id} (no official event_id)"
        )
