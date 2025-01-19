# chunk_and_summarize.py 

import logging
import asyncio
from luna import ai_functions  # We'll use ai_functions.get_gpt_response
from luna.bot_messages_store import get_messages_for_bot
logger = logging.getLogger(__name__)

async def chunk_and_summarize(
    text: str,
    chunk_size: int = 2000,
    abstraction_level: int = 1,
    model: str = "gpt-4",
    temperature: float = 0.7,
    max_tokens: int = 500,
) -> str:
    """
    A simple chunk+summarize function:
      1) Splits 'text' into ~chunk_size pieces.
      2) Summarizes each piece individually, calling GPT once per chunk.
      3) If abstraction_level > 1, merges partial summaries by repeated GPT calls,
         each time condensing further.

    :param text: The raw text to summarize.
    :param chunk_size: Approx number of characters per chunk (naive approach).
    :param abstraction_level: 1 => single pass summary, 
                             2+ => do extra merges to reach a higher-level summary.
    :param model: e.g. "gpt-4" or "gpt-3.5-turbo"
    :param temperature: GPT generation temperature
    :param max_tokens: GPT max_tokens param for each call.
    :return: Final summarized text.
    """

    # 1) Chunk the text by characters
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end

    # 2) Summarize each chunk with a single GPT call
    partial_summaries = []
    for i, chunk_text in enumerate(chunks):
        prompt = f"Summarize the following text in a concise manner:\n\n{chunk_text}\n"
        # We'll build the GPT messages array:
        messages = [
            {"role": "system", "content": "You are a summarizing assistant."},
            {"role": "user",   "content": prompt},
        ]
        summary_piece = await ai_functions.get_gpt_response(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )
        partial_summaries.append(summary_piece)

    # 3) If multiple passes, unify partial summaries into a final summary
    summary_output = "\n".join(partial_summaries)
    for level in range(2, abstraction_level + 1):
        merge_prompt = (
            f"Merge and further condense these partial summaries (pass={level}):\n"
            f"{summary_output}"
        )
        messages = [
            {"role": "system", "content": "You are a summarizing assistant."},
            {"role": "user",   "content": merge_prompt},
        ]
        summary_output = await ai_functions.get_gpt_response(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )

    return summary_output


async def summarize_room_for_participant(
    room_name: str,
    participant_perspective: str,
    abstraction_level: int = 1,
    chunk_size: int = 2000,
    model: str = "gpt-4",
    temperature: float = 0.7,
    max_tokens: int = 500
) -> str:
    """
    Wrapper for summarizing a Matrix room from the perspective of a specific participant.
    1) Fetch logs from the DB (here we do a naive approach, ignoring real vantage logic).
    2) Convert them into a text block, possibly including the participant's vantage.
    3) Call chunk_and_summarize(...) for the final condensed summary.

    :param room_name: E.g. "!abc123:localhost"
    :param participant_perspective: E.g. "@evan:localhost" or "Some vantage"
    :param abstraction_level: 1 => single pass, 2 => partial merges, etc.
    :param chunk_size: ~ chars per chunk
    :param model: GPT model
    :param temperature: GPT temperature
    :param max_tokens: GPT max tokens per call
    :return: Summarized string
    """

    # 1) Suppose we want all messages from <participant_perspective> in room <room_name>.
    #    Right now, we only have get_messages_for_bot(bot_localpart) in our store, 
    #    so let's do a minimal approach. If we want *all* room messages, 
    #    we might store them under "lunabot" or a generic "loggerbot." 
    #    For demonstration, we do a naive text gather:

    # For demonstration, let's assume participant_perspective is also the "bot_localpart" 
    # in the DB. That might not be exactly how your system is structured, 
    # but we'll do a simple approach:
    all_msgs = get_messages_for_bot(participant_perspective)

    # Filter by the room_name
    room_msgs = [m for m in all_msgs if m["room_id"] == room_name]
    if not room_msgs:
        logger.warning(f"No messages found for participant={participant_perspective} in room={room_name}.")
        return f"(No messages found for {participant_perspective} in {room_name})"

    # Sort them by ascending timestamp
    room_msgs.sort(key=lambda x: x["timestamp"])

    # Build a big text block:
    lines = []
    for msg in room_msgs:
        tstamp = msg["timestamp"]
        sender = msg["sender"]
        body   = msg["body"]
        # If you want to only keep messages from participant_perspective, you could filter out. 
        # But let's keep the entire conversation context:
        line = f"{sender}: {body}"
        lines.append(line)

    conversation_text = "\n".join(lines)

    # 2) We'll add a tiny prefix describing the perspective in the text 
    #    (or we can incorporate it in the chunk summarization prompt).
    text_with_perspective = (
        f"You are summarizing room '{room_name}' from the vantage of '{participant_perspective}'.\n"
        f"Below is the raw text:\n\n{conversation_text}"
    )

    # 3) Now call chunk_and_summarize
    final_summary = await chunk_and_summarize(
        text=text_with_perspective,
        chunk_size=chunk_size,
        abstraction_level=abstraction_level,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens
    )

    return final_summary


# Example usage from a REPL or from a test function:
# 
# async def example_usage():
#     result = await summarize_room_for_participant(
#         room_name="!abc123:localhost",
#         participant_perspective="blended_malt",  # or e.g. "@blended_malt:localhost" if your store uses that
#         abstraction_level=2,
#         chunk_size=1000,
#         model="gpt-4",
#         temperature=0.7,
#         max_tokens=500
#     )
#     print("FINAL SUMMARY =>\n", result)
#
# if __name__ == "__main__":
#     # quick test
#     asyncio.run(example_usage())
