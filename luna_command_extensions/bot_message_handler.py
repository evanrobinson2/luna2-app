# bot_message_handler.py

import logging
import time
import re
# import urllib.parse  # We won’t use URL-encoding for now
from nio import RoomMessageText, RoomSendResponse

# Adjust these imports to your project’s structure:
from luna import bot_messages_store         # or wherever you store your messages
import luna.context_helper as context_helper # your GPT context builder
from luna import ai_functions                # your GPT API logic

logger = logging.getLogger(__name__)
BOT_START_TIME = time.time() * 1000
# Regex to capture Matrix-style user mentions like "@username:domain"
MENTION_REGEX = re.compile(r"(@[A-Za-z0-9_\-\.]+:[A-Za-z0-9_\-\.]+)")

def build_mention_content(original_text: str) -> dict:
    """
    Scans the GPT reply for mentions like '@helpfulharry:localhost' and
    adds an <a href="matrix.to/#/@helpfulharry:localhost"> link in 'formatted_body'.
    Also populates 'm.mentions' with user_ids for explicit mention detection.
    
    We are NOT URL-encoding @ or underscores here—just a simple replacement.
    """

    # Find all mention strings (user IDs)
    matches = MENTION_REGEX.findall(original_text)
    html_text = original_text

    # We'll collect user IDs for 'm.mentions' here
    user_ids = []

    for mention in matches:
        user_ids.append(mention)
        # Example mention: "@helpful_harry:localhost"
        # We'll make a link like: <a href="https://matrix.to/#/@helpful_harry:localhost">@helpful_harry:localhost</a>
        url = f"https://matrix.to/#/{mention}"

        # The link text remains the original mention (with '@')
        html_link = f'<a href="{url}">{mention}</a>'

        # Replace plain mention with the linked mention in the HTML text
        html_text = html_text.replace(mention, html_link)

    # Construct the final content dict
    content = {
        "msgtype": "m.text",
        "body": original_text,             # plain-text fallback
        "format": "org.matrix.custom.html",
        "formatted_body": html_text
    }

    # If we found any mentions, add them to 'm.mentions'
    if user_ids:
        content["m.mentions"] = {"user_ids": user_ids}

    return content

async def handle_bot_room_message(bot_client, bot_localpart, room, event):
    """
    A “mention or DM” style message handler with GPT-based replies + message store.
    """
    # do not respond to messages from the past, under any circumstances
    if event.server_timestamp < BOT_START_TIME:
        logger.debug("Skipping old event => %s", event.event_id)
        return

    # 1) Must be a text event, and must not be from ourselves
    if not isinstance(event, RoomMessageText):
        return
    bot_full_id = bot_client.user  # e.g. "@blended_malt:localhost"
    if event.sender == bot_full_id:
        logger.debug(f"Bot '{bot_localpart}' ignoring its own message in {room.room_id}.")
        return

    # 2) Check for duplicates by event_id
    existing_msgs = bot_messages_store.get_messages_for_bot(bot_localpart)
    if any(m["event_id"] == event.event_id for m in existing_msgs):
        logger.info(
            f"[handle_bot_room_message] Bot '{bot_localpart}' sees event_id={event.event_id} "
            "already stored => skipping."
        )
        return

    # 3) Store the inbound text message
    bot_messages_store.append_message(
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
        await bot_client.room_typing(room.room_id, True, timeout=30000)
    except Exception as e:
        logger.warning(f"Could not send 'typing start' indicator => {e}")

    # 5) Build GPT context (the last N messages, plus a system prompt if you want)
    config = {"max_history": 20}  # adjust as needed
    gpt_context = context_helper.build_context(bot_localpart, room.room_id, config)

    # 6) Call GPT
    gpt_reply = await ai_functions.get_gpt_response(
        messages=gpt_context,
        model="gpt-4",
        temperature=0.7,
        max_tokens=300
    )

    # 7) Convert GPT reply => mention-aware content (including m.mentions)
    reply_content = build_mention_content(gpt_reply)

    # 8) Post GPT reply
    resp = await bot_client.room_send(
        room_id=room.room_id,
        message_type="m.room.message",
        content=reply_content,
    )

    # -- BOT INDICATES TYPING STOP --
    try:
        await bot_client.room_typing(room.room_id, False)
    except Exception as e:
        logger.warning(f"Could not send 'typing stop' indicator => {e}")

    # 9) Store outbound
    if isinstance(resp, RoomSendResponse) and resp.event_id:
        outbound_eid = resp.event_id
        logger.info(
            f"Bot '{bot_localpart}' posted a GPT reply event_id={outbound_eid} in {room.room_id}."
        )
        bot_messages_store.append_message(
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
