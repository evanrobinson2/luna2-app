# bot_member_event_handler.py

import logging
from nio import RoomMemberEvent, RoomGetStateEventError, RoomGetStateEventResponse

logger = logging.getLogger(__name__)

EVAN_USER_ID = "@evan:localhost"

async def handle_bot_member_event(bot_client, bot_localpart, room, event):
    """
    Handles membership changes for a single bot (or Luna) in 'room'.
      - If EVAN_USER_ID joins, set him to PL=100.
    """
    if not isinstance(event, RoomMemberEvent):
        return

    joined_user = event.sender
    logger.debug(
        f"[handle_bot_member_event] Bot '{bot_localpart}' sees {joined_user} joined {room.room_id}."
    )

    if joined_user == EVAN_USER_ID:
        logger.info(
            f"[handle_bot_member_event] => {EVAN_USER_ID} joined. Attempting to raise power to 100..."
        )
        try:
            await set_power_level(room.room_id, joined_user, 100, bot_client)
        except Exception as e:
            logger.exception(
                f"[handle_bot_member_event] Could not set PL for {joined_user}: {e}"
            )


async def set_power_level(room_id: str, user_id: str, new_level: int, bot_client):
    resp = await bot_client.room_get_state_event(
        room_id=room_id,
        event_type="m.room.power_levels",
        state_key=""
    )

    if not isinstance(resp, RoomGetStateEventResponse):
        logger.warning(
            f"[set_power_level] Unexpected response type => {type(resp)} : {resp}"
        )
        return

    pl_content = resp.content
    if not isinstance(pl_content, dict):
        logger.error(
            f"[set_power_level] power_levels content is not a dict => {pl_content}"
        )
        return

    logger.debug(f"[set_power_level] Current power_levels content => {pl_content}")

    # Insert / update the user's power level:
    users_dict = pl_content.get("users", {})
    users_dict[user_id] = new_level
    pl_content["users"] = users_dict

    logger.info(f"[set_power_level] Setting {user_id} to PL={new_level} in {room_id}...")

    update_resp = await bot_client.room_put_state(
        room_id=room_id,
        event_type="m.room.power_levels",
        content=pl_content,      # <-- This must be "content"
        state_key=""
    )

    if hasattr(update_resp, "status_code") and update_resp.status_code == 200:
        logger.info(
            f"[set_power_level] Successfully updated PL to {user_id}={new_level} in {room_id}."
        )
    else:
        logger.warning(
            f"[set_power_level] Attempted to set PL => {update_resp}"
        )
