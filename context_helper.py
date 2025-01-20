"""
context_helper.py

This module builds a GPT-style conversation array for a given bot in a given room.

OVERVIEW OF THE ALGORITHM:
--------------------------
1) We load the system prompt for the bot's localpart from the personalities or config.
   - If none is found, we use a fallback "You are a helpful assistant..."

2) For 'lunabot', we optionally append 'luna_context_appendix' (if set) to the system prompt.

3) We then fetch ALL messages from the local DB that were stored under `bot_localpart`
   and filter them to only those in the correct `room_id`.

4) We apply two separate rules for skipping lines:
   - a) If `bot_localpart` is NOT "lunabot", we exclude lines that start with "!" (commands)
       and lines that have `context_cue == "SYSTEM RESPONSE"`.
     Why? Because we only want normal user lines or user mention lines for non-Luna bots.
   - b) If `bot_localpart` == "lunabot", we do NOT skip commands or "SYSTEM RESPONSE" lines,
       because we want Luna herself to see the entire conversation flow (including commands).
     (You can further refine logic if you want Luna to skip her own lines, etc.)

5) We sort the remaining lines by ascending timestamp and then truncate to the last N 
   (default 20) lines to avoid token bloat.

6) Finally, we build a conversation array for GPT:
   - The first entry is a system-level instruction from the persona’s system_prompt.
   - Each subsequent message is either role="assistant" if it’s from the bot itself,
     or role="user" if it’s from someone else.

7) We return that array for the caller to send to GPT.

CODE NOTES:
----------
- `bot_messages_store.get_messages_for_bot(bot_localpart)` just returns the rows that 
  were appended with that `bot_localpart`. Because the message handler typically 
  appends everything the bot sees under that localpart, we might be storing multiple 
  copies if multiple bots are in the same channel.

- The logic that differentiates “skip” vs. “include” is entirely in this builder function,
  based on the new fields: `body.startswith("!")` or `record.get("context_cue") == "SYSTEM RESPONSE"`.

- If you want to skip the bot’s own lines, you can add a check 
  `(m["sender"] == f"@{bot_localpart}:localhost")`, etc.

- If you want to unify the logic for commands or system responses, you can 
  adjust the if-conditions accordingly.

"""

import logging
from typing import Dict, Any, List

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
      1) Load system prompt from persona or config for localpart.
      2) If localpart == 'lunabot', optionally append 'luna_context_appendix'.
      3) Retrieve all messages from the DB for (bot_localpart, room_id).
      4) Filtering rules:
         - If bot_localpart == 'lunabot', skip nothing (include commands & system responses).
         - Else skip lines that:
           a) start with '!'  (commands)
           b) have context_cue == 'SYSTEM RESPONSE'
      5) Sort ascending by timestamp.
      6) Keep last N (default=20).
      7) Build final conversation array:
         - The first item is {"role": "system", "content": system_prompt}.
         - Then each item is either {"role": "assistant", "content": ...}
           or {"role": "user", "content": ...} depending on who sent it.
      8) Return the array.
    """

    logger.info("[build_context] Called for bot_localpart=%r, room_id=%r", bot_localpart, room_id)

    # 0) If user didn't pass a config, create an empty one
    if config is None:
        config = {}
        logger.debug("[build_context] No config provided; using empty dict.")

    max_history = config.get("max_history", message_history_length)
    logger.debug("[build_context] Will fetch up to %d messages from store.", max_history)

    # 1) Grab the base system prompt for this bot
    system_prompt = get_system_prompt_by_localpart(bot_localpart)
    if not system_prompt:
        # Fallback if no persona or config found
        system_prompt = (
            "You are a helpful assistant. "
            "No personalized system prompt found for this bot, so please be friendly!"
        )
        logger.warning("[build_context] No persona found for %r; using fallback prompt.", bot_localpart)
    else:
        logger.debug("[build_context] Found system_prompt for %r (length=%d).",
                     bot_localpart, len(system_prompt))

    # 2) If lunabot, optionally append 'luna_context_appendix'
    from luna.luna_command_extensions.command_router import GLOBAL_PARAMS  # or wherever GLOBAL_PARAMS is stored

    if bot_localpart == "lunabot":
        extra_context = GLOBAL_PARAMS.get("luna_context_appendix", "").strip()
        if extra_context:
            logger.debug("[build_context] Appending luna_context_appendix (length=%d) to system prompt.",
                         len(extra_context))
            system_prompt += "\n\n" + extra_context

    # 3) Fetch messages for (bot_localpart, room_id)
    all_msgs = bot_messages_store.get_messages_for_bot(bot_localpart)
    logger.debug("[build_context] The store returned %d total msgs for bot=%r.",
                 len(all_msgs), bot_localpart)

    # 4) Filter to room_id
    relevant_msgs = [m for m in all_msgs if m["room_id"] == room_id]
    logger.debug("[build_context] Filtered by room_id => %d msgs remain.", len(relevant_msgs))

    # 4a) If NOT 'lunabot', also skip lines that are commands or system responses
    #     We do a minimal check for the '!' prefix, and we also check context_cue.
    #     If localpart == 'lunabot', we do NOT skip anything.
    if bot_localpart != "lunabot":
        filtered_msgs = []
        for msg in relevant_msgs:
            # Extract the text from "body"
            body_str = msg.get("body", "")
            # We may also have custom fields in the event content, but let's
            # assume we put "context_cue" in a separate DB column or appended to body if we had to.
            # If you stored 'context_cue' in the DB, you can do: msg.get("context_cue").
            # If you just store it in body, you'd parse. This example assumes it's in content.

            # If your table doesn't store context_cue explicitly, you might 
            # have to do some logic or store it in another table.
            # But for the sake of demonstration, let's assume we have it:
            context_cue = None   # default
            # If you haven't actually stored context_cue, skip it or check if your 
            # code sets content["context_cue"] => not shown in this snippet.

            # e.g. if we had a separate DB column or JSON field:
            # context_cue = msg.get("context_cue", None)

            # We'll do a minimal approach: if "system response" 
            # was appended to the body or something:
            # This is a placeholder for your actual approach
            # For demonstration, let's skip any line that starts with special prefix:
            # e.g. "context_cue=SYSTEM RESPONSE" (faked)
            # In real usage, store context_cue properly in the DB as a separate column.

            # We'll just do a naive demonstration:
            if "context_cue\": \"SYSTEM RESPONSE" in body_str:
                context_cue = "SYSTEM RESPONSE"

            if body_str.startswith("!"):
                # skip commands
                continue
            if context_cue == "SYSTEM RESPONSE":
                # skip system responses
                continue

            # If not matched skip logic, we include
            filtered_msgs.append(msg)

        relevant_msgs = filtered_msgs
        logger.debug("[build_context] After skipping commands/SYSTEM RESPONSE => %d msgs remain.",
                     len(relevant_msgs))

    # Sort ascending by timestamp
    relevant_msgs.sort(key=lambda x: x["timestamp"])

    # 5) Truncate to max_history
    truncated = relevant_msgs[-max_history:]
    logger.debug("[build_context] Truncated to last %d messages for building context.", len(truncated))

    # 6) Build the GPT conversation
    conversation: List[Dict[str, str]] = []

    # Step A: Add the system prompt as the first item
    conversation.append({
        "role": "system",
        "content": system_prompt
    })

    # Step B: For each truncated message, decide if it's user or assistant
    bot_full_id = f"@{bot_localpart}:localhost"
    for msg in truncated:
        sender_id = msg["sender"]
        body_str = msg["body"]

        if sender_id == bot_full_id:
            # The bot itself => role=assistant
            conversation.append({
                "role": "assistant",
                "content": body_str
            })
        else:
            # Another user => role=user
            conversation.append({
                "role": "user",
                "content": body_str
            })

    # Logging for debug
    logger.debug("[build_context] Final conversation array length=%d", len(conversation))
    for i, c in enumerate(conversation):
        logger.debug("   [%d] role=%r, content=(%d chars) %r",
                     i, c["role"], len(c["content"]), c["content"][:50])

    logger.info("[build_context] Completed building GPT context (total=%d items).", len(conversation))
    return conversation
