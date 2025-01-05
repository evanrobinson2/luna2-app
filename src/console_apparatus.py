import sys
import logging
import asyncio
from datetime import datetime

# Assuming console_functions.py is in the same package directory (with an __init__.py present).
# Use a relative import if they are side-by-side in the same package:
from . import console_functions

logger = logging.getLogger(__name__)

def console_loop(loop):
    """
    A blocking loop reading console commands in a background thread.
    We'll schedule any async actions on 'loop' via run_coroutine_threadsafe().

    Prompt format:
      [luna] 2025-01-05 14:56 (#1) %

    Also, if the user presses Enter on an empty line, we'll nudge them
    to type 'help' or 'exit'.
    """
    command_count = 0
    while True:
        command_count += 1

        # Build a short date/time string
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

        # Our custom prompt: [luna] 2025-01-05 14:56 (#3) %
        prompt = f"\n[luna] {now_str} (#{command_count}) % "

        cmd_line = input(prompt)
        if not cmd_line.strip():
            print("SYSTEM: No command entered. Type 'help' or 'exit'.")
            continue

        # Split into command + argument_string
        parts = cmd_line.strip().split(maxsplit=1)
        if not parts:
            continue  # extremely rare if cmd_line was just whitespace

        command_name = parts[0].lower()  # e.g. "create", "send", "who"
        argument_string = parts[1] if len(parts) > 1 else ""

        # Check if the command exists in our router
        if command_name in console_functions.COMMAND_ROUTER:
            handler_func = console_functions.COMMAND_ROUTER[command_name]
            handler_func(argument_string, loop)
        else:
            print("SYSTEM: Unrecognized command. Type 'help' for a list of commands.")
