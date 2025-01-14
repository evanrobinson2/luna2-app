# bot_invite_handler.py

import logging
from nio import LocalProtocolError, InviteMemberEvent
# from src.luna_personas import read_bot  # (uncomment if you want to load bot persona data)

logger = logging.getLogger(__name__)

async def handle_bot_invite(bot_client, bot_localpart, room, event):
    """
    Handles invite events for a single bot.

    :param bot_client: The AsyncClient belonging to this bot.
    :param bot_localpart: A string like "inky" or "clownsavior" (the localpart).
    :param room: The room object from matrix-nio.
    :param event: An InviteMemberEvent indicating an invitation.

    Example usage:
      bot_client.add_event_callback(
          lambda r, e: handle_bot_invite(bot_client, "inky", r, e),
          InviteMemberEvent
      )

    Optionally, you can load a persona (from disk, etc.) to see if autojoin is allowed:
      persona_data = read_bot(f"@{bot_localpart}:localhost")
      autojoin = persona_data.get("autojoin", True)
      if not autojoin:
          logger.info(f"Bot '{bot_localpart}' is configured not to join invites.")
          return
    """

    if not bot_client:
        logger.warning(
            f"[handle_bot_invite] No bot_client available for '{bot_localpart}'. Cannot handle invites."
        )
        return

    logger.info(
        f"[handle_bot_invite] Bot '{bot_localpart}' invited to {room.room_id}; attempting to join..."
    )

    try:
        await bot_client.join(room.room_id)
        logger.info(f"[handle_bot_invite] '{bot_localpart}' successfully joined {room.room_id}")
    except LocalProtocolError as e:
        logger.error(f"[handle_bot_invite] Error joining room {room.room_id}: {e}")
