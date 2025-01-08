"""
luna_functions_handledispatch.py

A "positive signal" version of on_room_message to prove the rest
of your mention-handling pipeline fires. It unconditionally logs
that a mention was found, so you can see if your code that runs
AFTER a mention is recognized actually does anything.
"""

import logging
logger = logging.getLogger(__name__)

# (No need to worry about membership or mention parsing for now.)

from src.luna_functions import invite_user_to_room, list_rooms

import logging
logger = logging.getLogger(__name__)

from src.luna_functions import (
    invite_user_to_room,
    list_rooms,
    post_gpt_reply,
)

import logging
logger = logging.getLogger(__name__)

from src.luna_functions import invite_user_to_room, list_rooms, DIRECTOR_CLIENT
from src.ai_functions import get_gpt_response  # or wherever your GPT integration resides

async def on_room_message(room, event):
    """
    Mention-based dispatch that calls GPT once per user ID
    in m.mentions["user_ids"], then posts each GPT reply by calling
    'post_gpt_reply' from luna_functions.py (which knows DIRECTOR_CLIENT).
    """
    from nio import RoomMessageText
    if not isinstance(event, RoomMessageText):
        return  # ignore non-text events

    logger.info("Handling on_room_message with multi-mention iteration approach.")

    user_message = event.body or ""
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

    # Example user triggers
    if "invite me" in user_message.lower():
        result = await invite_user_to_room("@somebody:localhost", room_id)
        logger.info(f"Invite result => {result}")

    if "rooms?" in user_message.lower():
        rooms_data = await list_rooms()
        logger.info(f"Rooms => {rooms_data}")

    # For each mention, do a GPT call & post the result
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

        # Instead of calling DIRECTOR_CLIENT here, we call 'post_gpt_reply' helper
        await post_gpt_reply(room_id, gpt_reply)