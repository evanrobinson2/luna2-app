"""
context_helper.py

A module to build conversation context for GPT,
now including all messages in the channel (both user and bot),
but EXCLUDING command lines that start with '!'.
Sets a larger default history size (e.g., 20).
"""

import logging
from typing import Dict, Any, List

from luna.luna_personas import get_system_prompt_by_localpart
from luna import bot_messages_store
from luna.luna_command_extensions.command_router import GLOBAL_PARAMS  # or wherever GLOBAL_PARAMS is stored

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def build_context(
    bot_localpart: str,
    room_id: str,
    config: Dict[str, Any] | None = None,
    message_history_length: int = 20
) -> List[Dict[str, str]]:
    """
    Builds a GPT-style conversation array for `bot_localpart` in `room_id`.
    Steps:
      1) Load the base system prompt from personalities (if missing, fallback).
      2) Append any 'luna_context_appendix' param (if set) to the system prompt.
      3) Retrieve up to N (default=20) messages from bot_messages_store for that bot + room.
         *We skip any that start with '!' (command messages).*
      4) Convert them to GPT roles: "assistant" if from the bot, "user" otherwise.
      5) Return a list of dicts e.g.:
         [
           {"role": "system", "content": "System instructions..."},
           {"role": "user", "content": "..."},
           {"role": "assistant", "content": "..."}
         ]
    """

    logger.info("[build_context] Called for bot_localpart=%r, room_id=%r", bot_localpart, room_id)

    if config is None:
        config = {}
        logger.debug("[build_context] No config provided, using empty dict.")

    max_history = config.get("max_history", message_history_length)
    logger.debug("[build_context] Will fetch up to %d messages from store.", max_history)

    # 1) Grab the base system prompt
    system_prompt = get_system_prompt_by_localpart(bot_localpart)
    if not system_prompt:
        system_prompt = (
            "You are a helpful assistant. "
            "No personalized system prompt found for this bot, so please be friendly!"
        )
        logger.warning("[build_context] No persona found for %r; using fallback prompt.", bot_localpart)
    else:
        logger.debug("[build_context] Found system_prompt for %r (length=%d).",
                     bot_localpart, len(system_prompt))

    if bot_localpart == 'lunabot':
        # 2) Append the 'luna_context_appendix' if present
        extra_context = GLOBAL_PARAMS.get("luna_context_appendix", "").strip()
        if extra_context:
            logger.debug("[build_context] Appending luna_context_appendix (length=%d) to system prompt.",
                        len(extra_context))
            system_prompt = f"{system_prompt}\n\n{extra_context}"

    # 3) Fetch messages from the store for (bot_localpart, room_id)
    all_msgs = bot_messages_store.get_messages_for_bot(bot_localpart)
    logger.debug("[build_context] The store returned %d total msgs for bot=%r.", len(all_msgs), bot_localpart)

    # Filter by room_id and skip messages starting with '!'
    relevant_msgs = []
    for m in all_msgs:
        if m["room_id"] == room_id:
            body = m["body"].lstrip() if m["body"] else ""
            if not body.startswith("!"):  # skip commands
                relevant_msgs.append(m)
    logger.debug("[build_context] After filtering by room_id=%r and skipping commands => %d msgs remain.",
                 room_id, len(relevant_msgs))

    # Sort ascending by timestamp
    relevant_msgs.sort(key=lambda x: x["timestamp"])
    logger.debug("[build_context] Sorted messages ascending by timestamp.")

    # Truncate to max_history (20 by default)
    truncated = relevant_msgs[-max_history:]
    logger.debug("[build_context] Truncated to last %d messages for building context.", len(truncated))

    # 4) Build the GPT conversation
    conversation: List[Dict[str, str]] = []
    # Add system message first
    conversation.append({
        "role": "system",
        "content": system_prompt
    })

    # Convert each truncated message to a user/assistant role
    bot_full_id = f"@{bot_localpart}:localhost"

    for msg in truncated:
        if msg["sender"] == bot_full_id:
            conversation.append({
                "role": "assistant",
                "content": msg["body"]
            })
        else:
            conversation.append({
                "role": "user",
                "content": msg["body"]
            })

    logger.debug("[build_context] Final conversation array length=%d", len(conversation))
    for i, c in enumerate(conversation):
        logger.debug("   [%d] role=%r, content=(%d chars) %r",
                     i, c["role"], len(c["content"]), c["content"][:50])

    logger.info("[build_context] Completed building GPT context (total=%d items).", len(conversation))
    return conversation
