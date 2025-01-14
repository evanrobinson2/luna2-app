# bot_message_handler.py

import logging
import time
from nio import RoomMessageText, RoomSendResponse

# Adjust to your project’s structure:
from luna import bot_messages_store2         # or wherever you store your messages
import luna.context_helper as context_helper # your GPT context builder
from luna import ai_functions                # your GPT API logic

logger = logging.getLogger(__name__)

async def handle_bot_room_message(bot_client, bot_localpart, room, event):
    """
    A “mention or DM” style message handler with GPT-based replies + message store.

    Steps:
      1) Skip non-text or self-messages.
      2) Check if we have already stored this event_id => avoid duplicates.
      3) Store inbound message in 'bot_messages_store2'.
      4) If DM or mention => build GPT context, call GPT, post reply.
      5) Store outbound GPT reply as well.
    """

    # 1) Must be a text event, and must not be from ourselves
    if not isinstance(event, RoomMessageText):
        return
    bot_full_id = bot_client.user  # e.g. "@blended_malt:localhost"
    if event.sender == bot_full_id:
        logger.debug(f"Bot '{bot_localpart}' ignoring its own message in {room.room_id}.")
        return

    # 2) Check for duplicates by event_id
    existing_msgs = bot_messages_store2.get_messages_for_bot(bot_localpart)
    if any(m["event_id"] == event.event_id for m in existing_msgs):
        logger.info(
            f"[handle_bot_room_message] Bot '{bot_localpart}' sees event_id={event.event_id} "
            "already stored => skipping."
        )
        return

    # 3) Store the inbound text message
    bot_messages_store2.append_message(
        bot_localpart=bot_localpart,
        room_id=room.room_id,
        event_id=event.event_id,
        sender=event.sender,
        timestamp=event.server_timestamp,
        body=event.body or ""
    )
    logger.debug(
        f"[handle_bot_room_message] Bot '{bot_localpart}' stored inbound event_id={event.event_id}."
    )

    # 4) Determine if we should respond (DM => always, group => only if mentioned)
    participant_count = len(room.users)
    content = event.source.get("content", {})
    mention_data = content.get("m.mentions", {})
    mentioned_ids = mention_data.get("user_ids", [])
    should_respond = False

    if participant_count == 2:
        # A 1-on-1 “direct chat” => always respond
        should_respond = True
    else:
        # If 3+ participants => respond only if we are mentioned
        if bot_full_id in mentioned_ids:
            should_respond = True

    if not should_respond:
        logger.debug(
            f"Bot '{bot_localpart}' ignoring group message with no mention. (room={room.room_id})"
        )
        return

    # -- BOT INDICATES TYPING START --
    try:
        # Indicate that we (the bot) are typing for up to 30 seconds
        await bot_client.room_typing(room.room_id, True, timeout=30000)
    except Exception as e:
        logger.warning(f"Could not send 'typing start' indicator => {e}")

    # 5) Build GPT context (the last N messages, plus a system prompt if you want)
    config = {"max_history": 10}  # adjust as needed
    gpt_context = context_helper.build_context(bot_localpart, room.room_id, config)

    # 6) Call GPT
    gpt_reply = await ai_functions.get_gpt_response(
        messages=gpt_context,
        model="gpt-4",
        temperature=0.7,
        max_tokens=300
    )

    # 7) Post GPT reply
    resp = await bot_client.room_send(
        room_id=room.room_id,
        message_type="m.room.message",
        content={"msgtype": "m.text", "body": gpt_reply},
    )

    # -- BOT INDICATES TYPING STOP --
    try:
        await bot_client.room_typing(room.room_id, False)
    except Exception as e:
        logger.warning(f"Could not send 'typing stop' indicator => {e}")

    # 8) Store outbound
    if isinstance(resp, RoomSendResponse) and resp.event_id:
        outbound_eid = resp.event_id
        logger.info(
            f"Bot '{bot_localpart}' posted a GPT reply event_id={outbound_eid} in {room.room_id}."
        )
        bot_messages_store2.append_message(
            bot_localpart=bot_localpart,
            room_id=room.room_id,
            event_id=outbound_eid,
            sender=bot_full_id,
            timestamp=int(time.time() * 1000),
            body=gpt_reply
        )
    else:
        logger.warning(
            f"Bot '{bot_localpart}' posted GPT reply but got no official event_id (room={room.room_id})."
        )
