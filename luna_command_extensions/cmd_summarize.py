import logging
from nio import AsyncClient
from typing import Optional

logger = logging.getLogger(__name__)

async def cmd_summarize(bot_client: AsyncClient, room_id: str, raw_args: str) -> str:
    """
    Usage: !summarize <prompt>

    Summarizes the conversation with a single prompt (possibly multi-word).
    No flags. 
    If the user typed:
      !summarize "Some multi-word prompt"
    we join the leftover tokens => raw_args => "\"Some multi-word prompt\""
    then we strip leading/trailing quotes/spaces => "Some multi-word prompt"

    If user typed no prompt, we show usage.
    """

    limit = 50
    # 1) Strip leading/trailing quotes & whitespace
    prompt = raw_args.strip().strip('"\'')
    if not prompt:
        return "Usage: !summarize <prompt>"

    # 2) Retrieve last N messages from room (hardcode or pick a default)
    from luna.bot_messages_store import get_messages_for_bot
    from luna.ai_functions import get_gpt_response

    bot_localpart = "lunabot"  # or adapt
    all_msgs = get_messages_for_bot(bot_localpart)
    # Filter to the room
    relevant = [m for m in all_msgs if m["room_id"] == room_id]
    # Just pick last 50
    snippet = relevant[-limit:]

    # Build conversation text
    lines = []
    for msg in snippet:
        lines.append(f"{msg['sender']}: {msg['body']}")
    conversation_text = "\n".join(lines)

    # 3) Build a minimal GPT system + user message
    system_msg = "You are an assistant that summarizes the conversation logs."
    user_msg = (
        f"Below is the last {len(snippet)} messages. Please summarize them.\n"
        f"Prompt from user:\n\n{prompt}\n\n"
        f"Conversation logs:\n\n{conversation_text}"
    )

    gpt_messages = [
        {"role": "system", "content": system_msg},
        {"role": "user",   "content": user_msg}
    ]

    # 4) Call GPT
    try:
        summary = await get_gpt_response(
            messages=gpt_messages,
            model="gpt-4",
            temperature=0.7,
            max_tokens=2000
        )
        return summary
    except Exception as e:
        logger.exception("[cmd_summarize] Error =>")
        return f"SYSTEM: Summarize error => {e}"
