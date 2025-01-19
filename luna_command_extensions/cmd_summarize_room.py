import logging
import asyncio
import shlex

# For BBS-like coloring, we can define a few ANSI color codes:
ANSI_BLUE = "\x1b[34m"
ANSI_CYAN = "\x1b[36m"
ANSI_GREEN = "\x1b[32m"
ANSI_MAGENTA = "\x1b[35m"
ANSI_RED = "\x1b[31m"
ANSI_YELLOW = "\x1b[33m"
ANSI_WHITE = "\x1b[37m"
ANSI_RESET = "\x1b[0m"

from luna.luna_command_extensions.summarize_room_for_participant import summarize_room_for_participant

logger = logging.getLogger(__name__)

def cmd_summarize_room(args, loop):
    """
    Usage: summarize_room <room_name> <participant_name> [--level N] [--chunk M]

    Example:
      summarize_room !abc123:localhost userA --level 2 --chunk 1000

    Summarizes the conversation in room_name from the vantage of participant_name
    using 'summarize_room_for_participant(...)'.

    Optional flags:
      --level N   => abstraction_level (default 1)
      --chunk M   => chunk_size in characters (default 2000)

    The result is printed to the console.
    """

    logger.debug(f"[cmd_summarize_room] Entered function with raw args => {args!r}")

    # 1) Parse arguments
    logger.debug("[cmd_summarize_room] Parsing arguments via shlex...")
    parts = shlex.split(args.strip())
    logger.debug(f"[cmd_summarize_room] Tokenized parts => {parts!r}")

    if len(parts) < 2:
        logger.warning("[cmd_summarize_room] Not enough arguments => %r", parts)
        print(
            f"{ANSI_YELLOW}SYSTEM:{ANSI_RESET} Usage: summarize_room <room_name> "
            f"<participant_name> [--level N] [--chunk M]"
        )
        return

    room_name = parts[0]
    participant = parts[1]
    logger.debug(f"[cmd_summarize_room] Room => {room_name!r}, Participant => {participant!r}")

    # Optional flags
    abstraction_level = 1
    chunk_size = 2000

    # Parse leftover tokens for --level and --chunk
    leftover = parts[2:]
    logger.debug(f"[cmd_summarize_room] Leftover tokens => {leftover!r}")

    i = 0
    while i < len(leftover):
        token = leftover[i].lower()
        logger.debug(f"[cmd_summarize_room] Inspecting leftover token => {token!r}")

        if token == "--level" and (i + 1) < len(leftover):
            try:
                abstraction_level = int(leftover[i + 1])
                logger.debug(f"[cmd_summarize_room] abstraction_level set => {abstraction_level}")
                i += 2
                continue
            except ValueError:
                logger.error("[cmd_summarize_room] Invalid number after '--level': %r", leftover[i+1])
                print(f"{ANSI_RED}SYSTEM:{ANSI_RESET} Invalid number after '--level'.")
        elif token == "--chunk" and (i + 1) < len(leftover):
            try:
                chunk_size = int(leftover[i + 1])
                logger.debug(f"[cmd_summarize_room] chunk_size set => {chunk_size}")
                i += 2
                continue
            except ValueError:
                logger.error("[cmd_summarize_room] Invalid number after '--chunk': %r", leftover[i+1])
                print(f"{ANSI_RED}SYSTEM:{ANSI_RESET} Invalid number after '--chunk'.")
        i += 1

    # 2) Wrap the summarization call in an async function for run_coroutine_threadsafe
    async def do_summarize():
        logger.info(
            "[cmd_summarize_room] Summarizing room=%r from participant=%r, "
            "level=%d, chunk_size=%d",
            room_name, participant, abstraction_level, chunk_size
        )
        try:
            # Print a little 1990s BBS–style header
            print(
                f"{ANSI_MAGENTA}\n"
                f"============================================\n"
                f" Summarizing ROOM: {room_name} \n"
                f" Participant: {participant} \n"
                f" Level: {abstraction_level} | Chunk: {chunk_size}\n"
                f"============================================{ANSI_RESET}"
            )
            summary = await summarize_room_for_participant(
                room_name=room_name,
                participant_perspective=participant,
                abstraction_level=abstraction_level,
                chunk_size=chunk_size
            )
            logger.debug("[cmd_summarize_room] Summarize function returned => %r", summary[:120] + "...")
            return summary
        except Exception as e:
            logger.exception("[cmd_summarize_room] Exception in do_summarize => %s", e)
            raise

    logger.debug("[cmd_summarize_room] Scheduling do_summarize() on the event loop.")
    future = asyncio.run_coroutine_threadsafe(do_summarize(), loop)

    try:
        logger.debug("[cmd_summarize_room] Blocking on future.result() for summary.")
        result = future.result()
        # 4) Print the summary with BBS style
        logger.debug("[cmd_summarize_room] Received summary result => %r", result[:120] + "...")
        print(
            f"{ANSI_BLUE}\n-----------[ FINAL SUMMARY ]-----------{ANSI_RESET}\n"
        )
        # We can color the final summary in a bright color for readability
        print(f"{ANSI_CYAN}{result}{ANSI_RESET}\n")
        print(f"{ANSI_BLUE}----------------------------------------{ANSI_RESET}")
    except Exception as e:
        logger.exception("[cmd_summarize_room] Caught top-level exception => %s", e)
        print(f"{ANSI_RED}SYSTEM:{ANSI_RESET} Error summarizing room => {e}")
    else:
        logger.debug("[cmd_summarize_room] Finished successfully.\n")
        print(f"{ANSI_GREEN}SYSTEM:{ANSI_RESET} Summarization complete.\n")
