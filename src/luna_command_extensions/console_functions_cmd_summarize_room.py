# console_functions_cmd_summarize_room.py

import shlex
import logging

from src.luna_functions_summarize_channel import summarize_room

logger = logging.getLogger(__name__)

def cmd_summarize_room(args: str, loop) -> None:
    """
    Usage:
      summarize_room <room_id> 
        [--type <summary_type>] 
        [--audience <audience_type>] 
        [--granularity <int>] 
        [--include_personalities] 
        [--exclude_participants <user1,user2,...>] 
        [--output_format <format>] 
        [--chunk_size <int>]

    Examples:
      summarize_room !abc123:localhost
      summarize_room !xyz789:localhost --type highlights --audience executive
      summarize_room !pirateRoom:localhost --granularity 5 --include_personalities
      summarize_room !devRoom:localhost --exclude_participants @bot:localhost,@lurker:localhost

    Description:
      This console command calls `summarize_room(...)` from
      `luna_functions_summarize_channel.py`, which generates a summary of a
      Matrix room's conversation. It parses command-line-like arguments from
      `args` and prints the final summary to the console.

    :param args: A string containing the arguments (room ID, flags, etc.).
    :param loop: The asyncio event loop (not strictly necessary for this command,
                 but we keep it for consistency with other cmd_* functions).
    :return: None (prints the summary to console).
    """

    # 1) Tokenize the 'args' string (e.g. "--type content --audience general")
    tokens = shlex.split(args)

    if not tokens:
        print("SYSTEM: Usage: summarize_room <room_id> [--type ...] [--audience ...]")
        return

    # 2) Parse out the 'room_id' (the first required positional)
    room_id = tokens[0]
    tokens = tokens[1:]  # remaining tokens

    # Set up defaults (these match the function signature defaults)
    summary_type = "content"
    audience = "general"
    granularity = 3
    include_personalities = False
    exclude_participants = None
    output_format = "text"
    chunk_size = 25

    # 3) Parse optional flags
    #    We'll do a simple manual approach here.
    i = 0
    while i < len(tokens):
        token = tokens[i].lower()

        if token == "--type":
            i += 1
            if i < len(tokens):
                summary_type = tokens[i]
        elif token == "--audience":
            i += 1
            if i < len(tokens):
                audience = tokens[i]
        elif token == "--granularity":
            i += 1
            if i < len(tokens):
                try:
                    granularity = int(tokens[i])
                except ValueError:
                    print("SYSTEM: Invalid granularity; must be an integer.")
                    return
        elif token == "--include_personalities":
            include_personalities = True
        elif token == "--exclude_participants":
            i += 1
            if i < len(tokens):
                # e.g. "--exclude_participants @bob:local,@alice:local"
                exclude_participants = tokens[i].split(",")
        elif token == "--output_format":
            i += 1
            if i < len(tokens):
                output_format = tokens[i]
        elif token == "--chunk_size":
            i += 1
            if i < len(tokens):
                try:
                    chunk_size = int(tokens[i])
                except ValueError:
                    print("SYSTEM: Invalid chunk_size; must be an integer.")
                    return
        else:
            # Unrecognized flag or extra argument
            print(f"SYSTEM: Unrecognized argument => {token}")
            print("SYSTEM: Usage: summarize_room <room_id> [--type ...] [--audience ...]")
            return

        i += 1

    # 4) Call the summarize_room function
    logger.debug(f"cmd_summarize_room -> room_id={room_id}, summary_type={summary_type}, "
                 f"audience={audience}, granularity={granularity}, "
                 f"include_personalities={include_personalities}, "
                 f"exclude_participants={exclude_participants}, output_format={output_format}, "
                 f"chunk_size={chunk_size}")

    try:
        summary_result = summarize_room(
            room_id=room_id,
            summary_type=summary_type,
            audience=audience,
            granularity=granularity,
            include_personalities=include_personalities,
            exclude_participants=exclude_participants,
            output_format=output_format,
            chunk_size=chunk_size
        )
    except Exception as e:
        logger.exception("Error in summarize_room")
        print(f"SYSTEM: An error occurred: {e}")
        return

    # 5) Print the result to console
    print(summary_result)