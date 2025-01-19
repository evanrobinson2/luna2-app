# bot_message_handler.py

import logging
import time
import re
import io
import contextlib

from nio import RoomMessageText, RoomSendResponse

# Adjust these imports to your project’s structure:
from luna import bot_messages_store
import luna.context_helper as context_helper
from luna import ai_functions

# 1) IMPORT your console commands
#    This is wherever you defined `COMMAND_ROUTER = {...}`
#    For example, if it's in a file called console_commands.py:
from luna.console_functions import COMMAND_ROUTER


COMMAND_PREFIX = "!"  # You can change it to suit your needs

def extract_commands_from_text(text: str):
    """
    Return a list of command-argument strings found in 'text',
    each starting after '!' and extending until the next '!' or end of string.

    e.g. "  !help some stuff !create_room fushnikins"
    => ["help some stuff", "create_room fushnikins"]
    """
    # We'll split on '!' but discard empty chunks
    # The first split may be empty if the text starts with space or doesn't contain '!'
    # We only want everything after the '!' marker.
    chunks = text.split(COMMAND_PREFIX)
    # Example:
    #  text = "  !help some stuff !create_room fushnikins"
    #  chunks = ["  ", "help some stuff ", "create_room fushnikins"]
    # We discard chunks[0] because it's before the first '!' or empty
    results = []
    for c in chunks[1:]:
        c = c.strip()
        if c:
            results.append(c)
    return results

def run_command_and_capture_output(command_str: str, event_loop) -> str:
    """
    Given a single chunk like "help some stuff", parse out:
      - cmd_name = "help"
      - args_str = "some stuff"
    Then run it via COMMAND_ROUTER[cmd_name](args_str, event_loop).

    We'll capture stdout (the 'print' statements) and return them as a single string.
    """
    # 1) Split out the first token as command name, remainder as args
    parts = command_str.split(None, 1)  # split on whitespace
    if not parts:
        return "SYSTEM: (empty command)\n"

    cmd_name = parts[0]
    args_str = parts[1] if len(parts) > 1 else ""

    # 2) Find the command function
    cmd_func = COMMAND_ROUTER.get(cmd_name)
    if not cmd_func:
        return f"SYSTEM: Unknown command '{cmd_name}'. Type '!help' for usage.\n"

    # 3) Capture the prints
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            # Many of your command functions expect (args, loop)
            cmd_func(args_str, event_loop)
        except Exception as e:
            logging.exception(f"[run_command_and_capture_output] Error running command '{cmd_name}': {e}")
            print(f"SYSTEM: Error while running '{cmd_name}': {e}")

    output_str = buf.getvalue()
    return output_str if output_str.strip() else "(No output)\n"

def handle_commands_in_text(text: str, event_loop) -> str:
    """
    Parse out all commands in `text`, run them, and return the combined output.
    If no commands are found, return an empty string.
    """
    command_chunks = extract_commands_from_text(text)
    if not command_chunks:
        return ""

    combined_output = []
    for chunk in command_chunks:
        out = run_command_and_capture_output(chunk, event_loop)
        combined_output.append(out)

    # Combine all the command outputs into one string
    return "\n".join(combined_output).strip()
