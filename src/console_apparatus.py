import sys
import logging
import asyncio
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter

# Assuming console_functions.py is in the same package directory.
from . import console_functions

logger = logging.getLogger(__name__)


def console_loop(loop):
    """
    A blocking loop reading console commands in a background thread.
    We'll schedule any async actions on 'loop' via run_coroutine_threadsafe().

    Prompt format:
      [luna] 2025-01-05 14:56 (#1) %

    If the user presses Enter on an empty line, we nudge them
    to type 'help' or 'exit'.

    We use prompt_toolkit for:
      - Arrow keys (history navigation)
      - Tab completion
    """

    # 1) Build a list of known commands for tab-completion
    commands = list(console_functions.COMMAND_ROUTER.keys())

    # 2) Create a WordCompleter from prompt_toolkit
    #    This will do simple prefix matching against our known commands
    commands_completer = WordCompleter(commands, ignore_case=True)

    # 3) Create a PromptSession with that completer
    session = PromptSession(completer=commands_completer)

    command_count = 0

    while True:
        command_count += 1

        # Build a short date/time string
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

        # Our custom prompt: e.g. [luna] 2025-01-05 14:56 (#3) %
        prompt_text = f"\n[luna-app] {now_str} (#{command_count}) % "

        try:
            # 4) Read user input using PromptSession
            cmd_line = session.prompt(prompt_text)
        except (EOFError, KeyboardInterrupt):
            # EOFError => user pressed Ctrl+D
            # KeyboardInterrupt => user pressed Ctrl+C
            logger.info("User exited the console (EOF or KeyboardInterrupt).")
            print("\nSYSTEM: Console session ended.")
            break

        # If the user pressed Enter on an empty line
        if not cmd_line.strip():
            print("SYSTEM: No command entered. Type 'help' or 'exit'.")
            continue

        # Split into command + argument_string
        parts = cmd_line.strip().split(maxsplit=1)
        if not parts:
            continue  # extremely rare if cmd_line was just whitespace

        command_name = parts[0].lower()
        argument_string = parts[1] if len(parts) > 1 else ""

        # Check if the command exists in our router
        if command_name in console_functions.COMMAND_ROUTER:
            handler_func = console_functions.COMMAND_ROUTER[command_name]
            handler_func(argument_string, loop)
        else:
            print("SYSTEM: Unrecognized command. Type 'help' for a list of commands.")
