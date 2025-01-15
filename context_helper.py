"""
context_helper.py

A module to build conversation context for GPT. 
Includes extensive logging to understand how we form the messages array.
"""

import logging
from typing import Dict, Any, List

# Adjust these imports as needed for your project
from luna.luna_personas import get_system_prompt_by_localpart
from luna import bot_messages_store

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def build_context(
    bot_localpart: str,
    room_id: str,
    config: Dict[str, Any] | None = None,
    message_history_length: int = 10
) -> List[Dict[str, str]]:
    """
    Builds a GPT-style conversation array for `bot_localpart` in `room_id`.
    Steps:
      1) Load the system prompt from personalities (if missing, fallback).
      2) Retrieve up to N messages from bot_messages_store for that bot + room.
      3) Convert them to GPT roles: "assistant" if from the bot, "user" otherwise.
      4) Return a list of dicts e.g.:
         [
           {"role": "system", "content": "System instructions..."},
           {"role": "user",   "content": "User said..."},
           {"role": "assistant", "content": "Bot replied..."}
         ]
    With extra-verbose logging so you can see precisely how the context is built.
    """

    logger.info("[build_context] Called for bot_localpart=%r, room_id=%r", bot_localpart, room_id)

    if config is None:
        config = {}
        logger.debug("[build_context] No config provided, using empty dict.")

    max_history = config.get("max_history", message_history_length)
    logger.debug("[build_context] Will fetch up to %d messages from store.", max_history)

    # 1) Grab the system prompt
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

    # 2) Fetch the last N messages from the store for this bot & room
    all_msgs = bot_messages_store.get_messages_for_bot(bot_localpart)
    logger.debug("[build_context] The store returned %d total msgs for bot=%r.", len(all_msgs), bot_localpart)

    # Filter them by room
    relevant_msgs = [m for m in all_msgs if m["room_id"] == room_id]
    logger.debug("[build_context] After filtering by room_id=%r => %d msgs remain.", 
                 room_id, len(relevant_msgs))

    # Sort them ascending by timestamp
    relevant_msgs.sort(key=lambda x: x["timestamp"])
    logger.debug("[build_context] Sorted messages ascending by timestamp.")

    # Truncate
    truncated = relevant_msgs[-max_history:]
    logger.debug("[build_context] Truncated to last %d messages for building context.", len(truncated))

    # 3) Build the GPT conversation
    conversation: List[Dict[str, str]] = []
    # Step A: Add system message
    conversation.append({
        "role": "system",
        "content": system_prompt
    })

    # Step B: For each message, classify as user or assistant
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
