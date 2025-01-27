# command_helpers.py

import logging
import re
import asyncio
from nio import AsyncClient, RoomSendResponse

logger = logging.getLogger(__name__)

async def _post_in_thread(
    bot_client: AsyncClient,
    room_id: str,
    parent_event_id: str,
    message_text: str,
    is_html: bool = False
) -> None:
    """
    Helper to post partial or final messages in the same “thread” 
    referencing the user’s original event. Using the 'm.in_reply_to' 
    or 'rel_type=m.thread' approach depending on your Element client version.

    For a modern approach: 
      "m.relates_to": {
        "rel_type": "m.thread",
        "event_id": parent_event_id
      }
    """
    # 1) Build content
    content = {}
    if not is_html:
        # Plain text
        content["msgtype"] = "m.text"
        content["body"] = message_text
    else:
        # HTML
        content["msgtype"] = "m.text"
        content["body"] = _strip_html_tags(message_text)
        content["format"] = "org.matrix.custom.html"
        content["formatted_body"] = message_text

    # 2) Add thread relation
    content["m.relates_to"] = {
        "rel_type": "m.thread",
        "event_id": parent_event_id
    }

    # 3) Send
    try:
        resp = await bot_client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content=content
        )
        if isinstance(resp, RoomSendResponse):
            logger.info(f"Posted a message in-thread => event_id={resp.event_id}")
        else:
            logger.warning(f"Could not post in-thread => {resp}")
    except Exception as e:
        logger.exception(f"[command_helpers] Error posting in-thread => {e}")


def _strip_html_tags(text: str) -> str:
    """
    Removes all HTML tags from the given text string.
    """
    return re.sub(r"<[^>]*>", "", text or "").strip()


async def _keep_typing(bot_client: AsyncClient, room_id: str, refresh_interval=3):
    """
    Periodically refresh the typing indicator in 'room_id' every
    'refresh_interval' seconds. Cancel this task to stop the typing
    indicator when done.
    """
    try:
        while True:
            # 'typing=True' with a 30s timeout
            await bot_client.room_typing(
                room_id=room_id,
                typing=True,
                timeout=30000
            )
            logger.info(f"[command_helpers] Set keep typing for {room_id}")
            await asyncio.sleep(refresh_interval)
    except asyncio.CancelledError:
        # Optionally send a final "typing=False" to clear the indicator
        # before exiting.
        try:
            await bot_client.room_typing(
                room_id=room_id,
                typing=False,
                timeout=0
            )
        except Exception:
            pass

async def _set_power_level(bot_client: AsyncClient, room_id: str, user_id: str, power: int):
    """
    Helper to set a user's power level in a given room.
    Copied or adapted from your existing code.
    """
    try:
        state_resp = await bot_client.room_get_state_event(room_id, "m.room.power_levels", "")
        current_content = state_resp.event.source.get("content", {})
        users_dict = current_content.get("users", {})
        users_dict[user_id] = power
        current_content["users"] = users_dict

        await bot_client.room_send_state(
            room_id=room_id,
            event_type="m.room.power_levels",
            state_key="",
            content=current_content,
        )
    except Exception as e:
        logger.warning(f"Could not set power level {power} for {user_id} in {room_id} => {e}")