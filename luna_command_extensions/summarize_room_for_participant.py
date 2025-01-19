import logging
from luna.bot_messages_store import get_messages_for_room
from luna.luna_command_extensions.chunk_and_summarize import chunk_and_summarize

logger = logging.getLogger(__name__)

async def summarize_room_for_participant(
    room_name: str,
    participant_perspective: str,
    abstraction_level: int = 1,
    chunk_size: int = 2000
) -> str:
    """
    Summarizes the entire conversation in 'room_name' so that
    'participant_perspective' can see what's going on. In other words,
    we do not filter by localpart, but return *all* messages from the DB.

    :param room_name: e.g. "!abc123:localhost"
    :param participant_perspective: e.g. "someUser", but we won't filter by them.
    :param abstraction_level: 1 => single pass, 2 => do merges, etc.
    :param chunk_size: approx. chars per chunk
    :return: Summarized text for the entire channel
    """

    logger.info(
        "[summarize_room_for_participant] Summarizing entire channel => %r, perspective=%r",
        room_name, participant_perspective
    )

    # 1) Get all messages from the DB for room_name
    all_msgs = get_messages_for_room(room_name)
    if not all_msgs:
        logger.warning("[summarize_room_for_participant] No messages found for %r", room_name)
        return f"No messages found in {room_name}."

    # 2) Build a big text block
    lines = []
    for msg in all_msgs:
        timestamp = msg["timestamp"]
        sender    = msg["sender"]
        body      = msg["body"]
        lines.append(f"{sender}: {body}")

    big_text = "\n".join(lines)

    # 3) Optionally incorporate participant perspective into the text or prompt:
    #    e.g. "You are summarizing the entire conversation from the vantage
    #    of {participant_perspective}..."
    #    We'll do it in the final prompt by passing the vantage into chunk_and_summarize.

    vantage_intro = (
        f"You are summarizing the entire conversation in {room_name}, "
        f"providing an overview for participant '{participant_perspective}'.\n"
        "Below is the full transcript:\n"
    )

    # 4) Summarize using a chunk_and_summarize function
    #    If you’re storing the vantage in the text, we can just prepend vantage_intro
    text_for_summarization = f"{vantage_intro}{big_text}"

    final_summary = await chunk_and_summarize(
        text=text_for_summarization,
        chunk_size=chunk_size,
        abstraction_level=abstraction_level
    )
    return final_summary
