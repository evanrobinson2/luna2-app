import sys
import logging
import asyncio
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import ANSI  # <-- IMPORTANT for colored prompt

from src.cmd_shutdown import SHOULD_SHUT_DOWN
from src.luna_command_extensions.check_synapse_status import checkSynapseStatus

# Assuming console_functions.py is in the same package directory.
from . import console_functions

logger = logging.getLogger(__name__)

# ─── ANSI COLOR CODES ───────────────────────────────────────────────────────────
GREEN = "\x1b[32m"
RED = "\x1b[31m"
YELLOW = "\x1b[33m"
MAGENTA = "\x1b[35m"
CYAN = "\x1b[36m"
RESET = "\x1b[0m"


def console_loop(loop):
    """
    A blocking loop reading console commands in a background thread.
    We'll schedule any async actions on 'loop' via run_coroutine_threadsafe().

    Prompt format:
      [ONLINE] [luna-app] YYYY-MM-DD HH:MM (#X) %
      with color-coded segments.

    If the user presses Enter on an empty line, we nudge them
    to type 'help' or 'exit'.

    We use prompt_toolkit for:
      - Arrow keys (history navigation)
      - Tab completion
    """

    commands = list(console_functions.COMMAND_ROUTER.keys())
    commands_completer = WordCompleter(commands, ignore_case=True)
    session = PromptSession(completer=commands_completer)

    command_count = 0

    while not SHOULD_SHUT_DOWN:

        if command_count == 0:
            console_functions.cmd_clear(None, loop)
            from src.ascii_art import show_ascii_banner
            print("Welcome to LunaBot - where the magic of your imagination can come to life.\n")
            print(show_ascii_banner("LUNA BOT"))
            print("What should we create today?")

        command_count += 1
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

        # ─── GET SYNAPSE STATUS ─────────────────────────────────────────────────
        try:
            future = asyncio.run_coroutine_threadsafe(
                checkSynapseStatus("http://localhost:8008"),
                loop
            )
            # checkSynapseStatus returns an ANSI-colored "[ONLINE]" / "[OFFLINE]" / "[UNKNOWN]"
            synapse_status_str = future.result(timeout=3)
        except Exception as e:
            logger.warning(f"Failed to check Synapse status => {e}")
            # fallback if something goes wrong
            synapse_status_str = f"{YELLOW}[UNKNOWN]{RESET}"

        # ─── BUILD THE PROMPT WITH COLORS ───────────────────────────────────────
        # E.g.   [ONLINE] [luna-app] 2025-01-11 17:25 (#7) %
        #        ^^^^^^^   ^^^^^^^^   ^^^^^        ^^^^^
        #        Green     Magenta    Cyan
        raw_prompt_text = (
            f"{synapse_status_str} "
            f"{MAGENTA}[luna-app]{RESET} "
            f"{CYAN}{now_str}{RESET} "
            f"(#{command_count}) % "
        )

        # Wrap in ANSI(...) so prompt_toolkit interprets the escape codes properly
        prompt_ansi_text = ANSI(raw_prompt_text)

        try:
            cmd_line = session.prompt(prompt_ansi_text)
        except (EOFError, KeyboardInterrupt):
            logger.info("User exited the console.")
            print("\nSYSTEM: Console session ended.")
            break

        if not cmd_line.strip():
            print("SYSTEM: No command entered. Type 'help' or 'exit'.")
            continue

        parts = cmd_line.strip().split(maxsplit=1)
        if not parts:
            continue

        command_name = parts[0].lower()
        argument_string = parts[1] if len(parts) > 1 else ""

        if command_name in console_functions.COMMAND_ROUTER:
            handler_func = console_functions.COMMAND_ROUTER[command_name]
            handler_func(argument_string, loop)
        else:
            print("SYSTEM: Unrecognized command. Type 'help' for a list of commands.")
