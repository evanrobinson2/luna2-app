=== __init__.py ===

=== ai_functions.py ===
"""
ai_functions.py

Provides an interface for sending prompts to the OpenAI API
and receiving responses. Now with extra-verbose logging to help debug
context input, response output, and timings.
"""

import os
import logging
import openai
import time
from nio import AsyncClient, UploadResponse
import requests
from dotenv import load_dotenv
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)
# You can adjust to DEBUG or more granular if you prefer:
logger.setLevel(logging.DEBUG)

# Optionally, if you want to see every single detail from openai or matrix-nio:
# logging.getLogger("openai").setLevel(logging.DEBUG)
logging.getLogger("nio.responses").setLevel(logging.CRITICAL)  # Usually keep quiet

# Load environment variables from a .env file (if present)
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
openai.api_key = OPENAI_API_KEY
if not OPENAI_API_KEY:
    logger.warning("[ai_functions] No OPENAI_API_KEY found in env variables.")

# We typically create an AsyncOpenAI client if using the async approach:
try:
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
except Exception as e:
    logger.exception("[ai_functions] Could not instantiate AsyncOpenAI client => %s", e)
    client = None


async def get_gpt_response(
    messages: list,
    model: str = "gpt-4o", # @TODO: make this a configuration based parameter, settable in luna-element command console
    temperature: float = 0.7,
    max_tokens: int = 1000
) -> str:
    """
    Sends `messages` (a conversation array) to GPT and returns the text
    from the first choice. We log everything at DEBUG level:
      - The final messages array
      - The model, temperature, max_tokens
      - Any errors or exceptions
      - The entire GPT response JSON (only if you want full debugging).
    """

    logger.debug("[get_gpt_response] Starting call to GPT with the following parameters:")
    logger.debug("   model=%s, temperature=%.2f, max_tokens=%d", model, temperature, max_tokens)
    logger.debug("   messages (length=%d): %s", len(messages), messages)

    if not client:
        err_msg = "[get_gpt_response] No AsyncOpenAI client is available!"
        logger.error(err_msg)
        return "I'm sorry, but my AI backend is not available right now."

    t0 = time.time()
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        elapsed = time.time() - t0

        # If you'd like, log the entire response object. CAUTION: can be huge.
        logger.debug("[get_gpt_response] Raw GPT response (truncated or full): %s", response)

        choice = response.choices[0]
        text = choice.message.content
        logger.debug("[get_gpt_response] Received GPT reply (%.3fs). Text length=%d",
                     elapsed, len(text))

        return text

    except openai.error.APIConnectionError as e:
        logger.exception("[get_gpt_response] Network problem connecting to OpenAI => %s", e)
        return (
            "I'm sorry, but I'm having network troubles at the moment. "
            "Could you check your internet connection and try again soon?"
        )

    except openai.error.RateLimitError as e:
        logger.exception("[get_gpt_response] OpenAI rate limit error => %s", e)
        return (
            "I'm sorry, I'm a bit overwhelmed right now and have hit my usage limits. "
            "Please try again in a little while!"
        )

    except Exception as e:
        # This catches any other error type
        logger.exception("[get_gpt_response] Unhandled exception calling GPT => %s", e)
        return (
            "I'm sorry, something went wrong on my end. "
            "Could you try again later?"
        )
    
logger = logging.getLogger(__name__)

def generate_image(prompt: str, size: str = "1024x1024") -> str:
    """
    Generates an image using OpenAI's API and returns the URL of the generated image.
    """
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    if not OPENAI_API_KEY:
        logger.error("OpenAI API key not found.")
        raise ValueError("Missing OpenAI API key.")

    # -----------------------------------------------------------------
    # 1) Merge the global style with the user's prompt
    # -----------------------------------------------------------------
    from luna.luna_command_extensions.command_router import GLOBAL_PARAMS
    style = GLOBAL_PARAMS.get("global_draw_prompt_appendix", "").strip()
    if style:
        final_prompt = f"{prompt.strip()}. {style}"
    else:
        final_prompt = prompt.strip()

    try:
        url = "https://api.openai.com/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": "dall-e-3",
            "prompt": final_prompt,
            "n": 1,
            "size": size,
        }

        logger.debug("Sending request to OpenAI: %s", data)
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        image_url = response.json()["data"][0]["url"]
        logger.info("Generated image URL: %s", image_url)
        return image_url
    except Exception as e:
        logger.exception("Failed to generate image.")
        raise e

async def generate_image_save_and_post(
    prompt: str,
    client: AsyncClient,
    evan_room_id: str,
    size: str = "1024x179"
) -> None:
    """
    1) Generates an image using OpenAI's newer /v1/images/generations endpoint.
    2) Saves the image to disk in data/images/.
    3) Uploads the image to Matrix and sends it to Evan's room (evan_room_id).
    """

    # Fetch API Key from environment
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    if not OPENAI_API_KEY:
        logger.warning("[ai_functions] No OPENAI_API_KEY found in env variables.")
        return

    # -----------------------------------------------------------------
    # 1) Merge the global style with the user's prompt
    # -----------------------------------------------------------------
    from luna.luna_command_extensions.command_router import GLOBAL_PARAMS
    style = GLOBAL_PARAMS.get("global_draw_prompt_appendix", "").strip()
    if style:
        final_prompt = f"{prompt.strip()}. {style}"
    else:
        final_prompt = prompt.strip()

    # 1) Generate image from prompt
    try:
        url = "https://api.openai.com/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": "dall-e-3",
            "prompt": final_prompt,
            "n": 1,
            "size": size
        }

        # Make the request to OpenAI
        resp = requests.post(url, headers=headers, json=data)
        resp.raise_for_status()      # Raises an HTTPError if the request failed
        response_data = resp.json()

        # Extract the URL for the generated image
        image_url = response_data["data"][0]["url"]

    except Exception as e:
        logger.exception("Error generating image: %s", e)
        return

    # 2) Save image to disk
    try:
        os.makedirs("data/images", exist_ok=True)
        timestamp = int(time.time())
        filename = f"data/images/image_{timestamp}.jpg"
        dl_resp = requests.get(image_url)
        if dl_resp.status_code == 200:
            with open(filename, "wb") as file:
                file.write(dl_resp.content)
            logger.info("Image saved to %s", filename)
        else:
            logger.error("Failed to download image from %s (HTTP %d)",
                         image_url, dl_resp.status_code)
            return
    except Exception as e:
        logger.exception("Error saving image to disk: %s", e)
        return

    # 3) Upload image to Matrix
    try:
        with open(filename, "rb") as file:
            upload_resp = await client.upload(file, content_type="image/jpeg")
            if not isinstance(upload_resp, UploadResponse):
                logger.error("Error uploading image to Matrix: %s", upload_resp)
                return
            mxc_uri = upload_resp.content_uri
    except Exception as e:
        logger.exception("Error uploading image to Matrix: %s", e)
        return

    # 4) Send the image to Evan's chat room
    content = {
        "msgtype": "m.image",
        "body": os.path.basename(filename),
        "url": mxc_uri,
        "info": {
            "mimetype": "image/jpeg",
            "size": os.path.getsize(filename),
        },
    }

    try:
        send_resp = await client.room_send(
            room_id=evan_room_id,
            message_type="m.room.message",
            content=content
        )
        if send_resp and hasattr(send_resp, "event_id"):
            logger.info("Image posted to Evan's room => event_id=%s", send_resp.event_id)
        else:
            logger.error("Failed to post image to Evan's room.")
    except Exception as e:
        logger.exception("Error sending the image message to Matrix: %s", e)
        
=== bot_messages_store.py ===
#!/usr/bin/env python3
"""
bot_messages_store.py

Drop-in replacement for the original JSON-based message store.
Instead of reading/writing a .json file, we store messages in an SQLite DB.
We keep the same 4 main functions:
    load_messages()
    save_messages()
    append_message(bot_localpart, room_id, event_id, sender, timestamp, body)
    get_messages_for_bot(bot_localpart)

Internally, we rely on a table named "bot_messages" with columns:
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_localpart TEXT,
    room_id      TEXT,
    event_id     TEXT,
    sender       TEXT,
    timestamp    INTEGER,
    body         TEXT

Notes:
  - We replicate the old behavior, so load_messages() and save_messages() still exist
    but are partially no-ops. We don't need to load everything into memory,
    but we do so for completeness. In real usage, you might prefer direct SELECT calls.
  - The interface is intentionally minimal to mimic the prior JSON store.
"""

import os
import logging
import sqlite3
from typing import List, Dict

logger = logging.getLogger(__name__)

# Adjust if desired
BOT_MESSAGES_DB = "data/bot_messages.db"

# In-memory cache (optional, to mimic the old JSON approach).
# If you prefer to query the DB on each call, you can skip this.
_in_memory_list: List[Dict] = []


def load_messages() -> None:
    """
    Sets up the SQLite DB (creating the table if needed), then loads all rows
    into the global _in_memory_list to mimic the old JSON behavior.
    """
    global _in_memory_list
    logger.info("[load_messages] Setting up the DB & loading messages into memory.")

    # Ensure data folder if needed
    os.makedirs(os.path.dirname(BOT_MESSAGES_DB), exist_ok=True)

    # 1) Create table if not exist
    create_sql = """
    CREATE TABLE IF NOT EXISTS bot_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_localpart TEXT,
        room_id TEXT,
        event_id TEXT,
        sender TEXT,
        timestamp INTEGER,
        body TEXT
    )"""
    try:
        conn = sqlite3.connect(BOT_MESSAGES_DB)
        c = conn.cursor()
        c.execute(create_sql)
        conn.commit()
        # 2) Load all messages into _in_memory_list
        rows = c.execute("SELECT bot_localpart, room_id, event_id, sender, timestamp, body FROM bot_messages").fetchall()

        _in_memory_list.clear()
        for row in rows:
            record = {
                "bot_localpart": row[0],
                "room_id": row[1],
                "event_id": row[2],
                "sender": row[3],
                "timestamp": row[4],
                "body": row[5],
            }
            _in_memory_list.append(record)

        conn.close()
        logger.info(f"[load_messages] Loaded {_in_memory_list.__len__()} rows from DB into memory.")
    except Exception as e:
        logger.exception(f"[load_messages] Failed to set up DB or load messages: {e}")
        _in_memory_list = []


def save_messages() -> None:
    """
    We keep this function to match the previous interface.
    In an SQLite approach, appends are typically committed immediately.
    So this is effectively a no-op, or can re-sync memory with the DB if needed.
    """
    logger.info("[save_messages] No-op in SQLite approach (data is committed on append).")


def append_message(
    bot_localpart: str,
    room_id: str,
    event_id: str,
    sender: str,
    timestamp: int,
    body: str
) -> None:
    """
    Inserts a single new row into the "bot_messages" table,
    and also updates the in-memory list if you prefer to keep that synchronized.

    :param bot_localpart: e.g. "lunabot"
    :param room_id: e.g. "!abc123:localhost"
    :param event_id: e.g. "$someUniqueEventId"
    :param sender: e.g. "@someuser:localhost"
    :param timestamp: e.g. 1736651234567
    :param body: message text
    """
    global _in_memory_list
    try:
        conn = sqlite3.connect(BOT_MESSAGES_DB)
        c = conn.cursor()

        insert_sql = """
        INSERT INTO bot_messages (bot_localpart, room_id, event_id, sender, timestamp, body)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        c.execute(insert_sql, (bot_localpart, room_id, event_id, sender, timestamp, body))
        conn.commit()
        conn.close()

        # Optionally keep our in-memory list in sync
        record = {
            "bot_localpart": bot_localpart,
            "room_id": room_id,
            "event_id": event_id,
            "sender": sender,
            "timestamp": timestamp,
            "body": body
        }
        _in_memory_list.append(record)

        logger.info(f"[append_message] Inserted event_id={event_id} for bot={bot_localpart} into DB.")
    except Exception as e:
        logger.exception(f"[append_message] Error inserting message => {e}")


def get_messages_for_bot(bot_localpart: str) -> List[Dict]:
    """
    Returns a list of messages from the DB for the given bot, sorted by timestamp ascending.
    We can either:
      - Query in-memory if you prefer the old approach
      - or do a direct SELECT with an ORDER BY.

    Here, we do a direct SELECT to be robust.
    """

    try:
        conn = sqlite3.connect(BOT_MESSAGES_DB)
        c = conn.cursor()
        select_sql = """
        SELECT bot_localpart, room_id, event_id, sender, timestamp, body
        FROM bot_messages
        WHERE bot_localpart = ?
        ORDER BY timestamp ASC
        """
        rows = c.execute(select_sql, (bot_localpart,)).fetchall()
        conn.close()

        results = []
        for row in rows:
            record = {
                "bot_localpart": row[0],
                "room_id": row[1],
                "event_id": row[2],
                "sender": row[3],
                "timestamp": row[4],
                "body": row[5],
            }
            results.append(record)

        logger.info(f"[get_messages_for_bot] Found {len(results)} messages for '{bot_localpart}'.")
        return results

    except Exception as e:
        logger.exception(f"[get_messages_for_bot] Error selecting messages => {e}")
        return []


=== console_apparatus.py ===
import sys
import logging
import asyncio
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import ANSI  # <-- IMPORTANT for colored prompt
from luna.luna_command_extensions.cmd_shutdown import SHOULD_SHUT_DOWN
from luna.luna_command_extensions.check_synapse_status import checkSynapseStatus
from luna.luna_command_extensions.ascii_art import show_ascii_banner

# Assuming console_functions.py is in the same package directory.
from luna import console_functions

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

=== console_functions.py ===
import os
import sys
import logging
import subprocess
import shlex
import asyncio
import textwrap
import json
import aiohttp
from datetime import datetime
from nio import AsyncClient
from asyncio import CancelledError
import json
from luna import luna_personas
from luna import luna_functions
from nio.api import RoomVisibility
from luna.luna_functions import DIRECTOR_CLIENT
import asyncio
from luna.luna_command_extensions.create_room import create_room
from luna.luna_command_extensions.cmd_remove_room import cmd_remove_room
from luna.luna_personas import get_system_prompt_by_localpart, set_system_prompt_by_localpart
from luna.luna_command_extensions.cmd_shutdown import request_shutdown
from luna.luna_command_extensions.ascii_art import show_ascii_banner
from luna.luna_command_extensions.cmd_generate_image import cmd_generate_image


logger = logging.getLogger(__name__)

########################################################
# 1) COMMAND HANDLER FUNCTIONS
########################################################
def cmd_banner(args, loop):
    print ("\n" + show_ascii_banner("Luna Bot"))

def cmd_help(args, loop):
    """
    Usage: help

    Show usage for all known commands in a more readable multi-line format.
    """
    logger.debug("Showing help to user.")
    print("SYSTEM: Available commands:\n")

    # A small utility to wrap text nicely at ~70 characters, for readability.
    wrapper = textwrap.TextWrapper(width=70, subsequent_indent="    ")

    for cmd_name, cmd_func in COMMAND_ROUTER.items():
        doc = (cmd_func.__doc__ or "").strip()
        if not doc:
            usage_line = f"(No usage info for `{cmd_name}`)"
            description = ""
        else:
            # Split docstring lines
            lines = doc.splitlines()
            usage_line = ""
            description = ""

            # We assume first line is "Usage:", subsequent lines are description
            if lines:
                first_line = lines[0].strip()
                if first_line.startswith("Usage:"):
                    usage_line = first_line
                    # Join the rest as the description
                    if len(lines) > 1:
                        description = " ".join(l.strip() for l in lines[1:] if l.strip())
                else:
                    # If we didn't find "Usage:" up front, treat everything as description
                    usage_line = "(No usage line found.)"
                    description = " ".join(l.strip() for l in lines if l.strip())

        # Wrap the usage and description
        usage_line_wrapped = wrapper.fill(usage_line)
        description_wrapped = wrapper.fill(description)

        print(f"{cmd_name}\n  {usage_line_wrapped}")
        if description_wrapped:
            print(f"  {description_wrapped}")
        print()  # blank line after each command

def cmd_exit(args, loop):
    """
    Usage: exit

    Gracefully shuts down Luna by setting the shutdown flag
    and stopping the main loop.
    """
    logger.info("Console received 'exit' command; requesting shutdown.")
    print("SYSTEM: Shutting down Luna gracefully...")    
    request_shutdown()



def cmd_restart(args, loop):
    """
    Usage: restart

    Kills and relaunches the process with the same arguments.
    """
    logger.info("Console received 'restart' command; restarting now.")
    print("SYSTEM: Attempting to restart the entire process...")

    python_executable = sys.executable
    script = sys.argv[0]
    extra_args = sys.argv[1:]

    # This call does not return if successful
    os.execl(python_executable, python_executable, script, *extra_args)

def cmd_log(args, loop):
    """
    Usage: log

    Displays the log file path by inspecting the logging configuration
    to find a FileHandler. If found, we print that file’s path; if not,
    we mention that no file-based logging is detected.
    """
    logger = logging.getLogger()  # The root logger
    file_handler_found = False

    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            log_path = getattr(handler, "baseFilename", None)
            if log_path:
                print(f"SYSTEM: Log file is located at: {log_path}")
                file_handler_found = True
                break
    
    if not file_handler_found:
        print("SYSTEM: No file-based logger was found. Logs may be console-only.")

def cmd_who(args, loop):
    """
    Usage: who

    Shows the current director's user ID if any.
    """
    # Typically you'd do something like:
    # from src.luna_functions import get_director
    # director = get_director()
    # but let's pretend we do that inline for demonstration:

    # Mock example:
    from luna_functions import DIRECTOR_CLIENT
    if DIRECTOR_CLIENT:
        print(f"SYSTEM: Director is => {DIRECTOR_CLIENT.user}")
    else:
        print("SYSTEM: No Director Found")

def cmd_clear(args, loop):
    """
    Usage: clear

    Clears the console screen.
    """
    if os.name == 'nt':
        os.system('cls')
    else:
        os.system('clear')
    logger.info("Console screen cleared.")

def cmd_rotate_logs(args, loop):
    """
    Usage: rotate_logs

    Renames 'server.log' to a timestamped file (e.g. server-20250105-193045.log),
    then reinitializes the logger so new logs go into a fresh file.
    """
    logger.info("Rotating logs...")

    from datetime import datetime
    import os
    import logging

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    log_file = "data/logs/server.log"
    archive_dir = "data/logs/archive"
    rotated_file = f"{archive_dir}/server-{timestamp}.log"

    # 1) Ensure the archive directory exists
    try:
        os.makedirs(archive_dir, exist_ok=True)
    except Exception as e:
        print(f"SYSTEM: Error creating archive directory '{archive_dir}': {e}")
        return

    # 2) Rotate the current file
    if os.path.exists(log_file):
        try:
            os.rename(log_file, rotated_file)
            print(f"SYSTEM: Rotated {log_file} -> {rotated_file}")
        except Exception as e:
            print(f"SYSTEM: Error rotating logs: {e}")
            return
    else:
        print("SYSTEM: No server.log found to rotate.")

    # 3) Create a fresh server.log
    try:
        with open(log_file, "w") as f:
            pass
        print("SYSTEM: New server.log created.")
    except Exception as e:
        print(f"SYSTEM: Error creating new server.log: {e}")

    # 4) Re-init logging so future logs go into the new file
    #    (Close the old handler, create a new FileHandler, attach it, etc.)
    root_logger = logging.getLogger()

    # Remove old file handlers
    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)
            handler.close()

    # Create a new file handler for "server.log"
    new_handler = logging.FileHandler(log_file)
    new_handler.setLevel(logging.DEBUG)  # adjust as preferred
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    new_handler.setFormatter(formatter)
    root_logger.addHandler(new_handler)

    logger.info(f"Log rotation complete. Logging to {log_file} again.")
    print(f"SYSTEM: Logging has been reinitialized to {log_file}.")

def cmd_purge_and_seed(args, loop):
    """
    Usage: purge_and_seed

    This is a destructive operation. Press any key to continue.
    """
    print ("SYSTEM> DOES NOTHING NOW. 'rm /Users/evanrobinson/Documents/Luna2/matrix/homeserver.db'")
    print ("STOP THE SERVER FIRST")

########################################################
# NEW COMMAND HANDLER
########################################################
def cmd_check_limit(args, loop):
    """
    Usage: check-limit

    Makes a single short sync request to see if we get rate-limited (HTTP 429).
    Blocks until the request completes, then prints the result.
    """
    logger.info("Console received 'check-limit' command. Blocking until result is returned...")

    try:
        # run_coroutine_threadsafe returns a Future, then .result() blocks
        # this background thread (the console thread) until the coroutine finishes.
        result_msg = asyncio.run_coroutine_threadsafe(
            luna_functions.check_rate_limit(),
            loop
        ).result()

        # Now we have the final string from check_rate_limit()
        print(f"SYSTEM: {result_msg}")

    except Exception as e:
        logger.exception(f"Error in check-limit: {e}")
        print(f"SYSTEM: Error in check-limit: {e}")



def cmd_check_limit_dep(args, loop):
    """
    Usage: check-matrix

    Makes a single request to the Matrix server to see if we get rate-limited (HTTP 429).
    If it returns 200, you're good. If 429, you're being throttled. Otherwise, see logs.
    """
    logger.info("Console received 'check-limit' command. Checking for rate-limit...")

    future = asyncio.run_coroutine_threadsafe(
        luna_functions.check_rate_limit(),
        loop
    )

    def on_done(fut):
        try:
            result_msg = fut.result()
            print(f"SYSTEM: {result_msg}")
        except Exception as e:
            logger.exception(f"Error in check-limit: {e}")
            print(f"SYSTEM: Error in check-limit: {e}")

    future.add_done_callback(on_done)

def cmd_fetch_all(args, loop):
    """
    Usage: fetch_all

    Fetch all historical messages from all joined rooms in pages, 
    storing them in a CSV. This might take a while if rooms are large.

    This version BLOCKS the console thread until the fetch completes.
    """
    logger.info("Console received 'fetch_all' command. Blocking until done...")

    future = asyncio.run_coroutine_threadsafe(
        luna_functions.fetch_all_messages_once(
            luna_functions.DIRECTOR_CLIENT,
            room_ids=None,       # or specify a list of specific room IDs
            page_size=100
        ),
        loop
    )

    try:
        # BLOCK until the fetch completes
        future.result()  # you could pass a timeout here if desired
        print("SYSTEM: Successfully fetched all historical messages.")
    except Exception as e:
        logger.exception(f"Error in fetch_all: {e}")
        print(f"SYSTEM: Error in fetch_all: {e}")

    def on_done(fut):
        try:
            fut.result()
            print("SYSTEM: Successfully fetched new messages.")
        except Exception as e:
            logger.exception(f"Error in fetch_new: {e}")
            print(f"SYSTEM: Error in fetch_new: {e}")

    future.add_done_callback(on_done)


def cmd_create_user(args, loop):
    """
    Usage: create_user <username> <password> [--admin]

    Example:
      create_user alice supersecret
      create_user bob mypass --admin

    Parses console arguments, then calls create_and_login_bot(...).
    This ensures the new user is created on Synapse and ephemeral-logged into BOTS.
    """
    import logging
    from luna.luna_command_extensions.create_and_login_bot import create_and_login_bot

    logger = logging.getLogger(__name__)

    parts = args.strip().split()
    if len(parts) < 2:
        print("Usage: create_user <username> <password> [--admin]")
        return

    username, password = parts[:2]
    is_admin = False
    if len(parts) > 2 and parts[2].lower() == "--admin":
        is_admin = True

    # Wrap in an async function so we can run it on the event loop:
    async def create_and_login():
        return await create_and_login_bot(username, password, is_admin)

    future = asyncio.run_coroutine_threadsafe(create_and_login(), loop)

    def on_done(fut):
        try:
            result = fut.result()
            # For example: "Successfully created & logged in bot => @alice:localhost"
            print(f"SYSTEM: {result}")
        except Exception as e:
            print(f"Error while creating user '{username}': {e}")
            logger.exception("Exception in cmd_create_user callback.")

    future.add_done_callback(on_done)
    print(f"SYSTEM: Creating & logging in user '{username}' (admin={is_admin})...")


def cmd_show_shutdown(args, loop):
    """
    Usage: show_shutdown

    Prints the current value of SHOULD_SHUT_DOWN (a boolean).
    """
    from luna_command_extensions.cmd_shutdown import SHOULD_SHUT_DOWN
    print(f"SYSTEM: SHOULD_SHUT_DOWN is currently set to {SHOULD_SHUT_DOWN}.")


def cmd_list_rooms(args, loop):
    """
    Usage: list_rooms [--json]

    Fetches a list of rooms (name, ID, participant count, etc.) from the director client.
    If you provide '--json', it will print the output as JSON instead of a table.
    """
    # 1) Check if the user wants JSON output
    parts = args.strip().split()
    json_flag = ("--json" in parts)

    # 2) Schedule the async call to list_rooms and wait for its result
    try:
        rooms_info = asyncio.run_coroutine_threadsafe(
            luna_functions.list_rooms(),
            loop
        ).result()  # <-- This will block until the coroutine completes

        if not rooms_info:
            print("SYSTEM: No rooms found or DIRECTOR_CLIENT is not ready.")
            return

        # 3) Output the result
        if json_flag:
            # Print as JSON
            print(json.dumps(rooms_info, indent=2))
        else:
            # Print a formatted table
            _print_rooms_table(rooms_info)

    except Exception as e:
        logger.exception(f"Exception in cmd_list_rooms: {e}")
        print(f"SYSTEM: Error listing rooms: {e}")

def _print_rooms_table(rooms_info: list[dict]):
    """
    Helper function to print a nice table of rooms:
      NAME (up to ~30 chars)  | ROOM ID (up to ~35 chars) | COUNT (5 chars) | PARTICIPANTS
    """
    # Build a header line with fixed-width columns
    header = f"{'NAME':30} | {'ROOM ID':35} | {'COUNT':5} | PARTICIPANTS"
    print(header)
    print("-" * 105)  # or 90, depending on how wide you like

    for room in rooms_info:
        name = (room['name'] or "(unnamed)")[:30]
        room_id = room['room_id']
        count = room['joined_members_count']
        participants_str = ", ".join(room['participants'])

        # Format each row to match the header widths
        row = f"{name:30} | {room_id:35} | {count:5} | {participants_str}"
        print(row)

def cmd_list_users(args, loop):
    """
    Usage: list_users [--json]

    Fetches a list of users from the Synapse server,
    prints them in a table or JSON, then returns control to the console.
    """
    parts = args.strip().split()
    json_flag = ("--json" in parts)

    try:
        # Directly block the console thread until the future completes
        users_info = asyncio.run_coroutine_threadsafe(
            luna_functions.list_users(), loop
        ).result(timeout=10)  # optional timeout in seconds

        if not users_info:
            print("SYSTEM: No users found or we failed to query the server.")
            return

        if json_flag:
            # Print as JSON
            print(json.dumps(users_info, indent=2))
        else:
            _print_users_table(users_info)

    except Exception as e:
        logger.exception(f"Exception in cmd_list_users: {e}")
        print(f"SYSTEM: Error listing users: {e}")


def _print_users_table(users_info: list[dict]):
    """
    Helper function to print a table of user data:
      USER ID (up to ~25 chars) | ADMIN | DEACT | DISPLAYNAME
    """
    header = f"{'USER ID':25} | {'ADMIN':5} | {'DEACT'} | DISPLAYNAME"
    print(header)
    print("-" * 70)

    for user in users_info:
        user_id = (user['user_id'] or "")[:25]
        admin_str = "Yes" if user.get("admin") else "No"
        deact_str = "Yes" if user.get("deactivated") else "No"
        display = user.get("displayname") or ""

        row = f"{user_id:25} | {admin_str:5} | {deact_str:5} | {display}"
        print(row)

def cmd_invite_user(args, loop):
    """
    Usage: invite_user <user_id> <room_id_or_alias>

    Example:
      invite_user @bob:localhost !testRoom:localhost
      invite_user @spyclops:localhost #mychannel:localhost

    Sends a normal invite to the specified user_id, so they can accept
    and join the given room or room alias. This requires that the user
    executing this command (Luna's director) has sufficient power level
    in the room to invite new participants.
    """

    parts = args.strip().split()
    if len(parts) < 2:
        print("SYSTEM: Usage: invite_user <user_id> <room_id_or_alias>")
        return

    user_id = parts[0]
    room_id_or_alias = parts[1]

import logging
import asyncio
import aiohttp
import time
from luna import luna_functions

logger = logging.getLogger(__name__)

async def do_invite_user(user: str, room: str) -> str:
    """
    Asynchronous subroutine to invite 'user' to 'room' (which might be
    a raw room ID like "!abc123:localhost" or possibly a name or alias).
    1) Forces a short sync to ensure the client sees the correct power levels.
    2) Invokes client.room_invite(...).
    3) If M_FORBIDDEN occurs, we provide a more detailed message.
    """

    client = luna_functions.getClient()
    if not client:
        return "Error: No DIRECTOR_CLIENT set."

    # 1) Force a short sync so our client state is up-to-date:
    try:
        # Run a blocking sync in the current thread
        sync_future = asyncio.run_coroutine_threadsafe(
            client.sync(timeout=1000),  # 1-second sync
            luna_functions.MAIN_LOOP  # or your existing loop reference
        )
        sync_future.result()
        logger.debug("[do_invite_user] Sync completed before invite.")
    except Exception as sync_e:
        logger.exception("Sync error before inviting user:")
        return f"Error syncing before invite => {sync_e}"
    try:
        resp = await client.room_invite(room, user)
        logger.debug(f"[do_invite_user] room_invite returned => {resp}")

        if resp and hasattr(resp, "status_code"):
            code = resp.status_code
            if code in (200, 202):
                return f"Invited {user} to {room}."
            else:
                # If we see 403 or 401, typically it's M_FORBIDDEN or not enough power
                if code == 403:  
                    return (
                        f"Error inviting {user} => M_FORBIDDEN. "
                        "Possible cause: insufficient power level or not recognized in the room. "
                        "Ensure you (the inviter) are joined & have the right power level."
                    )
                return f"Error inviting {user} => {code} (Check logs for details.)"
        else:
            # If resp is None or not recognized
            return "Invite returned an unexpected or null response."
    except Exception as e:
        logger.exception("[do_invite_user] Exception in room_invite:")
        # If e is a matrix-nio error (e.g., RoomInviteError), we can handle it specifically
        return f"Exception inviting user => {e}" 

def cmd_delete_bot(args, loop):
    """
    Usage: delete_bot <bot_localpart>

    Example:
      delete_bot jamiebot

    Steps:
    1) Remove the local persona entry from personalities.json.
    2) Delete the Matrix user @jamiebot:localhost from the server via admin API.
    """

    parts = args.strip().split()
    if len(parts) < 1:
        print("SYSTEM: Usage: delete_bot <bot_localpart>")
        return

    localpart = parts[0].lower()
    bot_id = f"@{localpart}:localhost"

    # Step A: Delete local persona from personalities.json
    try:
        from luna_functions import delete_bot_persona
        delete_bot_persona(bot_id)  
        print(f"SYSTEM: Successfully removed persona record for {bot_id}")
    except FileNotFoundError:
        print("SYSTEM: personalities.json not found; skipping local removal.")
    except KeyError as ke:
        print(f"SYSTEM: {ke}")
    except Exception as e:
        print(f"SYSTEM: Unexpected error removing {bot_id} from local store: {e}")
        return

    # Step B: Delete user from Synapse
    from luna_functions import delete_matrix_user
    future = asyncio.run_coroutine_threadsafe(
        delete_matrix_user(localpart),
        loop
    )

    def on_done(fut):
        try:
            result_msg = fut.result()
            print(f"SYSTEM: {result_msg}")
        except Exception as e:
            print(f"SYSTEM: Error deleting Matrix user {bot_id}: {e}")

    future.add_done_callback(on_done)
    
def cmd_create_room(args, loop):
    """
    Usage: create_room "<roomName>" [--private]

    Example:
      create_room "My Room With Spaces" --private

    We'll pass the entire 'args' to create_room(...) so it can parse
    out the room name and flags with shlex.
    """

    future = asyncio.run_coroutine_threadsafe(
        create_room(args),  # <== note: just 'args'
        loop
    )

    def on_done(fut):
        try:
            result_msg = fut.result()
            print(f"SYSTEM: {result_msg}")
        except Exception as e:
            print(f"SYSTEM: Error creating room => {e}")

    future.add_done_callback(on_done)

def cmd_get_bot_system_prompt(args, loop):
    """
    Usage: get_bot_sp <bot_localpart>

    Example:
      get_bot_sp inky

    Retrieves the current system_prompt for a bot with the given localpart,
    e.g. "inky" => bot ID "@inky:localhost".
    Prints it to the console or a warning if not found.
    """
    parts = args.strip().split()
    if len(parts) < 1:
        print("Usage: get_bot_sp <bot_localpart>")
        return

    localpart = parts[0]

    # Just call get_system_prompt_by_localpart right away
    system_prompt = get_system_prompt_by_localpart(localpart)
    if system_prompt is None:
        print(f"SYSTEM: No bot found for localpart='{localpart}'.")
    else:
        print(f"SYSTEM: The system_prompt for '{localpart}' =>\n\n{system_prompt}")

def cmd_set_bot_system_prompt(args, loop):
    """
    Usage: set_bot_sp <bot_localpart> "<new system prompt>"

    Example:
      set_bot_sp inky "You are Inky, the fastest ghost in Pac-Man!"

    Sets (overwrites) the system_prompt for the given localpart.
    Must wrap the new prompt in quotes if it contains spaces.
    """
    # We'll parse args with shlex so we can capture quoted text properly
    try:
        tokens = shlex.split(args.strip())
    except ValueError as e:
        print(f"SYSTEM: Error parsing arguments => {e}")
        return

    if len(tokens) < 2:
        print("Usage: set_bot_sp <bot_localpart> \"<new system prompt>\"")
        return

    localpart = tokens[0]
    new_prompt = tokens[1]  # This might be already unquoted by shlex

    # If there's leftover beyond tokens[1], we might want to re-join them,
    # or your usage pattern might always require quotes around new_prompt.
    # For a minimal approach, assume the user has put the entire prompt in quotes:
    #   set_bot_sp inky "Hello world, I'm your ghost"
    # then tokens should be ["inky", "Hello world, I'm your ghost"].

    updated_persona = set_system_prompt_by_localpart(localpart, new_prompt)
    if updated_persona is None:
        print(f"SYSTEM: No bot found for localpart='{localpart}'.")
    else:
        # Confirm success
        print(f"SYSTEM: Updated system_prompt for '{localpart}' =>\n\n{new_prompt}")

def cmd_who_is(args, loop):
    """
    Usage: who_is <localpart>

    Retrieves and displays persona info from personalities.json for
    the bot with that <localpart>, in a table with wrapped text for
    each field's value.

    Example:
      who_is inky
    """

    parts = args.strip().split()
    if len(parts) < 1:
        print("Usage: who_is <localpart>")
        return

    localpart = parts[0]
    full_user_id = f"@{localpart}:localhost"

    # Attempt to read the persona from personalities.json
    persona = luna_personas.read_bot(full_user_id)
    if not persona:
        print(f"SYSTEM: No persona found for '{full_user_id}' in personalities.json.")
        return

    # Print header
    print(f"\nSYSTEM: Persona for bot => {full_user_id}\n")

    # Determine how wide the left (key) column should be
    # so everything lines up neatly
    max_key_len = max(len(k) for k in persona.keys())

    # Choose a wrapping width for values
    wrap_width = 60

    # Print each key-value pair in a nicely formatted table
    for key, raw_value in persona.items():
        # If the value is a dict or list, JSON-serialize for display
        if isinstance(raw_value, (dict, list)):
            value_str = json.dumps(raw_value, indent=2)
        else:
            # Otherwise, just convert to string
            value_str = str(raw_value)

        # Wrap the text at wrap_width characters
        lines = textwrap.wrap(value_str, width=wrap_width) or ["(empty)"]

        # Print the first line with the key
        print(f"{key.ljust(max_key_len)} : {lines[0]}")
        
        # For any additional lines, align them under the value column
        for line in lines[1:]:
            print(" " * (max_key_len + 3) + line)

    print()

def cmd_summon_long_prompt(args, loop):
    """
    Usage: summon_long_prompt "<giant blueprint text>"

    We'll feed that blueprint to GPT with a small system instruction telling
    it to create a well-formed persona definition, which we then parse + spawn.
    """

    import shlex
    tokens = shlex.split(args, posix=True)
    if not tokens:
        print("Usage: summon_long_prompt \"<blueprint text>\"")
        return

    blueprint_text = tokens[0]  # Or re-join tokens if you allow multiple quoted sections

    async def do_summon():
        from luna.ai_functions import get_gpt_response  # or your new GPT call
        # 1) Build the short instruction
        system_inst = (
            "You will receive a 'blueprint' text that describes how a new persona should behave.\n"
            "You must return a JSON object with the following keys:\n"
            "  localpart (string), displayname (string), system_prompt (string), traits (object)\n"
            "No extra keys, no markdown.\n"
            "If user does not specify a localpart, create one from the blueprint.\n"
            "If user does not specify a displayname, guess it or do something generic.\n"
            "Be as versose and dirctive as possible in your creation of the system prompt.\n"
            "Instruct the bot to be absolutely willing to talk about prior messages and conversation history.\n"
        )

        # 2) GPT conversation array
        conversation = [
            {"role": "system", "content": system_inst},
            {
                "role": "user",
                "content": (
                    f"Below is the blueprint. Please parse it and produce your JSON:\n\n"
                    f"{blueprint_text}"
                ),
            },
        ]

        # 3) Make GPT call
        gpt_reply = await get_gpt_response(
            messages=conversation,
            model="gpt-4",
            temperature=0.7,
            max_tokens=500
        )

        # 4) Parse JSON, handle errors
        import json
        try:
            persona_data = json.loads(gpt_reply)
        except json.JSONDecodeError as e:
            return f"GPT returned invalid JSON => {e}\n\n{gpt_reply}"

        # 5) Validate required keys
        for needed in ["localpart", "displayname", "system_prompt", "traits"]:
            if needed not in persona_data:
                return f"Missing required field '{needed}' in GPT output => {persona_data}"

        # 6) Summon the bot
        from luna.luna_command_extensions.create_and_login_bot import create_and_login_bot
        new_bot_id = f"@{persona_data['localpart']}:localhost"
        password = "somePassword123"  # or randomly generate

        result_msg = await create_and_login_bot(
            bot_id=new_bot_id,
            password=password,
            displayname=persona_data["displayname"],
            system_prompt=persona_data["system_prompt"],
            traits=persona_data["traits"]
        )
        return result_msg

    future = asyncio.run_coroutine_threadsafe(do_summon(), loop)

    def on_done(fut):
        try:
            outcome = fut.result()
            print(f"SYSTEM: {outcome}")
        except Exception as e:
            print(f"SYSTEM: Summon error => {e}")

    future.add_done_callback(on_done)
    print("SYSTEM: Summoning a bot from your blueprint... please wait.")

def cmd_spawn_squad(args, loop):
    """
    Usage: spawn <numBots> "<theme or style>"

    Example:
      spawn_squad 3 "A jazzy trio of improvisational bots"
    """
    # Import inside the function to avoid circular imports or to keep it minimal:
    from luna.luna_command_extensions.spawner import cmd_spawn_squad as spawner_impl

    # Just delegate all logic:
    spawner_impl(args, loop)

def cmd_run_json_script(args, loop):
    """
    Usage: run_script <script_file>

    Reads a JSON-based script from <script_file>, then parses and executes it.
    The script can contain actions like:
      - create_room
      - create_user
      - add_user_to_channel
      ... etc.

    Example:
      run_script my_script.json

    The command will load 'my_script.json' from disk, parse it,
    then execute the actions in order, printing logs along the way.
    """
    import os
    import logging
    import json
    from luna.luna_command_extensions.parse_and_execute import parse_and_execute

    logger = logging.getLogger(__name__)
    logger.debug("[cmd_run_json_script] Called with args='%s'", args)

    # 1) Parse console arguments
    parts = args.strip().split()
    if len(parts) < 1:
        print("Usage: run_script <script_file>")
        return

    script_file = parts[0]
    logger.debug("User provided script_file='%s'", script_file)

    # 2) Check if the file exists
    if not os.path.exists(script_file):
        msg = f"[cmd_run_json_script] File not found: {script_file}"
        logger.error(msg)
        print(f"SYSTEM: {msg}")
        return

    # 3) Read the file contents
    try:
        with open(script_file, "r", encoding="utf-8") as f:
            script_str = f.read()
        logger.debug("[cmd_run_json_script] Successfully read %d bytes from '%s'.",
                     len(script_str), script_file)
    except Exception as e:
        logger.exception("[cmd_run_json_script] Failed to read file '%s': %s", script_file, e)
        print(f"SYSTEM: Error reading file '{script_file}': {e}")
        return

    # 4) Execute the script
    print(f"SYSTEM: Executing script from '{script_file}'...")
    logger.debug("[cmd_run_json_script] Invoking parse_and_execute(...)")
    try:
        parse_and_execute(script_str, loop)
        logger.debug("[cmd_run_json_script] parse_and_execute completed.")
    except Exception as e:
        logger.exception("[cmd_run_json_script] parse_and_execute threw an exception: %s", e)
        print(f"SYSTEM: Error executing script: {e}")
        return

    # 5) Confirm success
    print("SYSTEM: Script execution command finished.")

########################################################
# THE COMMAND ROUTER DICTIONARY
########################################################

COMMAND_ROUTER = {
    # System or meta-commands
    "help": cmd_help,
    "restart": cmd_restart,
    "exit": cmd_exit,
    
    "logfile": cmd_log,
    "rotate_logs": cmd_rotate_logs,
    
    "clear": cmd_clear,
    "purge_and_seed": cmd_purge_and_seed, # stub-only
    
    "create_room": cmd_create_room,
    "remove_room" : cmd_remove_room,
    "list_rooms": cmd_list_rooms,
    "fetch_all": cmd_fetch_all,

    "list_users": cmd_list_users,
    "whois":cmd_who_is,
    "whois_director": cmd_who,
    "get_system_prompt_for": cmd_get_bot_system_prompt,
    "set_system_prompt_for": cmd_set_bot_system_prompt,

    "invite": cmd_invite_user,
    "spawn": cmd_spawn_squad,
    "run_script": cmd_run_json_script,
    "generate_image" : cmd_generate_image
}
=== context_helper.py ===
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

=== core.py ===
"""
core.py

Houses everything that was in luna.py plus your main logic,
login routines, references to other pieces (handlers, console, etc.).
"""

import asyncio
import sys
import json
import os
import logging
import sqlite3
import threading
from nio import (
    RoomMessageText,
    InviteMemberEvent,
    RoomMemberEvent,
    AsyncClient
)

from luna.luna_command_extensions.command_router import GLOBAL_PARAMS
from luna.luna_command_extensions.command_router import load_config  # or wherever you keep load_config()

# If these handlers are in separate files, adjust imports accordingly:
from luna.luna_command_extensions.bot_message_handler import handle_bot_room_message
from luna.luna_command_extensions.bot_invite_handler import handle_bot_invite
from luna.luna_command_extensions.bot_member_event_handler import handle_bot_member_event

from luna.luna_command_extensions.luna_message_handler4 import handle_luna_message4

from luna.bot_messages_store import load_messages

from luna.console_apparatus import console_loop # Our console apparatus & shutdown signals
from luna.luna_command_extensions.cmd_shutdown import init_shutdown, SHOULD_SHUT_DOWN
from luna.luna_functions import load_or_login_client, load_or_login_client_v2 # The “director” login + ephemeral bot login functions

logger = logging.getLogger(__name__)

# Global containers
BOTS = {}        # localpart -> AsyncClient (for bots)
BOT_TASKS = []   # list of asyncio Tasks for each bot’s sync loop
MAIN_LOOP = None # The main event loop
DATABASE_PATH = "data/bot_messages.db"

# core.py
import logging
from luna.luna_command_extensions.command_router import GLOBAL_PARAMS
from luna.luna_command_extensions.command_router import load_config

logger = logging.getLogger(__name__)

def init_globals():
    """
    Loads the config.yaml file at startup and populates GLOBAL_PARAMS
    with any keys found under 'globals:'. 
    This ensures your in-memory parameters are up-to-date before the bot runs.
    """
    logger.info("Initializing global parameters from config.yaml...")
    cfg = load_config()
    globals_section = cfg.get("globals", {})
    for key, value in globals_section.items():
        GLOBAL_PARAMS[key] = value
        logger.debug("Loaded global param %r => %r", key, value)
    logger.info("Global parameters initialized: %d params loaded.", len(globals_section))


def configure_logging():
    """
    Configure Python logging to show debug in console
    and store everything in 'data/logs/server.log'.
    """
    global logger
    logger = logging.getLogger(__name__)
    logging.getLogger("nio.responses").setLevel(logging.CRITICAL)
    logger.debug("Entering configure_logging function...")

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Overall log level
    logger.debug("Set root logger level to DEBUG.")

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.debug("Formatter for logs created.")

    os.makedirs("data/logs", exist_ok=True)
    log_file_path = "data/logs/server.log"
    file_handler = logging.FileHandler(log_file_path, mode="a")  # append
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    logger.debug(
        f"Added file handler to root logger. Logging to '{log_file_path}' at DEBUG level."
    )
    logger.debug("Exiting configure_logging function.")

def start_console_thread(loop: asyncio.AbstractEventLoop):
    """
    Launch the console input loop in a background thread,
    so user commands (e.g. create_user) can be processed
    while the main event loop runs.
    """
    logger.debug("Entering start_console_thread function.")
    try:
        thread = threading.Thread(
            target=lambda: console_loop(loop),
            daemon=True
        )
        thread.start()
        logger.info("Console thread started successfully.")
    except Exception as e:
        logger.exception(f"Failed to start console thread: {e}")
    logger.debug("Exiting start_console_thread function.")

async def login_bots():
    """
    Reads 'data/luna_personalities.json', ephemeral-logs each bot,
    and stores the resulting AsyncClient in global BOTS dict.

    Does NOT attach event callbacks or start sync tasks here—
    that happens in main_logic.
    """
    personalities_file = "data/luna_personalities.json"
    if not os.path.exists(personalities_file):
        logger.error(f"[login_bots] No {personalities_file} found.")
        return

    with open(personalities_file, "r", encoding="utf-8") as f:
        personalities_data = json.load(f)

    homeserver_url = "http://localhost:8008"
    for user_id, persona in personalities_data.items():
        localpart = user_id.split(":")[0].replace("@", "")
        password = persona.get("password", "")
        if not password:
            logger.warning(f"[login_bots] Skipping {user_id} => no password found.")
            continue

        try:
            logger.info(f"[login_bots] Logging in bot => {user_id} (localpart={localpart})")
            client = await load_or_login_client_v2(
                homeserver_url=homeserver_url,
                user_id=user_id,
                password=password,
                device_name=f"{localpart}_device"
            )
            BOTS[localpart] = client
        except Exception as e:
            logger.exception(f"[login_bots] Failed to login bot '{user_id}': {e}")

    logger.info(f"[login_bots] Completed ephemeral login for {len(BOTS)} bot(s).")

async def run_bot_sync(bot_client: AsyncClient, localpart: str):
    """
    Simple sync loop for each bot, runs until SHOULD_SHUT_DOWN is True.
    """
    while not SHOULD_SHUT_DOWN:
        try:
            await bot_client.sync(timeout=5000)
        except Exception as e:
            logger.exception(
                f"[run_bot_sync] Bot '{localpart}' had sync error: {e}"
            )
            await asyncio.sleep(2)  # brief backoff
        else:
            # If no error, give control to other tasks
            await asyncio.sleep(0)

# ------------------------------------------------------------------
# HELPER CALLBACK FUNCTIONS
# ------------------------------------------------------------------

def make_message_callback(bot_client, localpart):
    """
    Returns a function that references exactly these arguments,
    intended for handling normal room messages for a non-Luna bot.
    """
    async def on_message(room, event):
        await handle_bot_room_message(bot_client, localpart, room, event)
    return on_message

def make_invite_callback(bot_client, localpart):
    """
    Returns a function to handle invites for a non-Luna bot.
    """
    async def on_invite(room, event):
        await handle_bot_invite(bot_client, localpart, room, event)
    return on_invite

def make_member_callback(bot_client, localpart):
    """
    Returns a function to handle membership changes for a non-Luna bot.
    """
    async def on_member(room, event):
        await handle_bot_member_event(bot_client, localpart, room, event)
    return on_member

async def main_logic():
    """
    The main async function:
      1) Login Luna (director).
      2) Login all bot personas from disk.
      3) Attach event callbacks for each bot, spawn each sync loop.
      4) Luna's short sync loop runs until SHOULD_SHUT_DOWN.
    """
    logger.debug("Starting main_logic...")
    
    init_globals()
    
    # A) Log in Luna (the "director" user)
    luna_client = await load_or_login_client(
        homeserver_url="http://localhost:8008",
        username="lunabot",
        password="12345"
    )
    logger.info("Luna client login complete.")

    # -- 1) Attach Luna's event callbacks --
    # For messages:
    luna_client.add_event_callback(
        #lambda room, event: handle_luna_message(luna_client, "lunabot", room, event),
        lambda room, event: handle_luna_message4(luna_client, "lunabot", room, event),
        RoomMessageText
    )

    # For invites (the same invite handler you'd use for normal bots, or a specialized one):
    luna_client.add_event_callback(
        lambda room, event: handle_bot_invite(luna_client, "lunabot", room, event),
        InviteMemberEvent
    )

    # For membership changes (same or specialized):
    luna_client.add_event_callback(
        lambda room, event: handle_bot_member_event(luna_client, "lunabot", room, event),
        RoomMemberEvent
    )

    # B) Log in existing bots from disk
    await login_bots()
    logger.debug(f"BOTS loaded => {list(BOTS.keys())}")

    # -- 2) For each loaded bot, attach event callbacks and start a sync loop
    bot_tasks = []
    for localpart, bot_client in BOTS.items():
        try:
            # Register each callback via a distinct helper
            bot_client.add_event_callback(
                make_message_callback(bot_client, localpart),
                RoomMessageText
            )
            bot_client.add_event_callback(
                make_invite_callback(bot_client, localpart),
                InviteMemberEvent
            )
            bot_client.add_event_callback(
                make_member_callback(bot_client, localpart),
                RoomMemberEvent
            )

            # Start its sync loop
            task = asyncio.create_task(run_bot_sync(bot_client, localpart))
            bot_tasks.append(task)

            logger.info(f"Set up bot '{localpart}' successfully.")

        except Exception as e:
            logger.exception(f"Error setting up bot '{localpart}': {e}")

    # C) Luna's own short sync loop until shutdown
    logger.debug("Entering Luna's main sync loop.")
    while not SHOULD_SHUT_DOWN:
        try:
            await luna_client.sync(timeout=5000)
        except Exception as e:
            logger.exception(f"Luna encountered sync error => {e}")

    # D) Cleanup
    logger.info("Shutting down. Closing Luna's client...")
    await luna_client.close()
    logger.debug("Luna client closed.")

    # Cancel each bot's sync task
    for t in bot_tasks:
        t.cancel()

    logger.debug("main_logic done, returning.")

def luna_main():
    """
    Replaces the old 'luna()' function.
    Sets up logging, creates an event loop,
    starts the console in a thread, then runs main_logic.
    """
    configure_logging()
    logger.debug("Logging configured. Creating event loop.")

    # Load stored messages from disk (optional part of your code)
    load_messages()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    logger.debug("New event loop set as default.")

    # Init the shutdown mechanism
    init_shutdown(loop)

    global MAIN_LOOP
    MAIN_LOOP = loop

    # Start the console
    start_console_thread(loop)

    # Run main logic
    try:
        logger.info("Starting main_logic until shutdown.")
        loop.run_until_complete(main_logic())
    except KeyboardInterrupt:
        logger.warning("KeyboardInterrupt => shutting down.")
    except Exception as e:
        logger.exception(f"Unexpected error in main_logic => {e}")
    finally:
        logger.debug("Preparing to close the loop.")
        loop.close()
        logger.info("Loop closed. Exiting.")

def get_bots() -> dict:
    """
    Returns the global dictionary of BOTS.
    Useful for other modules that need to inspect or manipulate
    the dictionary without directly importing 'BOTS'.
    """
    return BOTS

def load_system_prompt():
    """
    (Optional) If you need to load a special system prompt for Luna from file.
    """
    with open("data/luna_system_prompt.md", "r", encoding="utf-8") as f:
        return f.read()

=== get_all_messages_standalone.py ===
#!/usr/bin/env python3

import os
import csv
import sqlite3
from datetime import datetime

# Adjust if your DB or table is in a different location/name:
DB_PATH = "../data/bot_messages.db"
TABLE_NAME = "bot_messages"

def main():
    # Create output directory if needed
    out_dir = "exports"
    os.makedirs(out_dir, exist_ok=True)

    # Build a timestamped filename
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_filename = f"all_messages_{timestamp_str}.csv"
    out_path = os.path.join(out_dir, out_filename)

    try:
        # Connect to the SQLite DB
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Query all messages from the table (sorted by timestamp ascending)
        query = f"""
            SELECT 
                id,
                bot_localpart,
                room_id,
                event_id,
                sender,
                timestamp,
                body
            FROM {TABLE_NAME}
            ORDER BY timestamp ASC
        """
        rows = cursor.execute(query).fetchall()
        
        # Write rows to CSV
        with open(out_path, mode="w", encoding="utf-8", newline="") as csv_file:
            writer = csv.writer(csv_file)
            # Write a header row:
            writer.writerow(["id", 
                             "bot_localpart", 
                             "room_id", 
                             "event_id", 
                             "sender", 
                             "timestamp", 
                             "body"])
            # Write all data rows
            for row in rows:
                writer.writerow(row)
        
        print(f"Exported {len(rows)} messages to '{out_path}'.")
    
    except Exception as e:
        print(f"Error exporting messages: {e}")
    
    finally:
        # Always close the DB connection
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main()

=== issues.md ===
#### ISSUES

Need to be able to remove users.
Need to be able to list users.
Need to be able to review a specific user's profile.
Global system prompt?
Improved context formulation that uses summaries instead of pure history

Technical minutae / Housekeeping:
1. Lunabot is the admin, it's hardcoded in multiple files
2. Multiple files declare globals and constants, those should move to a config file of some kind
3. Keys like the director key should be stored in environment variables, not on disk
4. In Luna Functions, sometimes we use the API to make changes, sometimes we call functions from matrix-nio, it's inconsistent
6. shut-down not graceful:?
2025-01-12 15:33:28,560 [ERROR] __main__: An unexpected exception occurred in main_logic: Event loop stopped before Future completed.
Traceback (most recent call last):
  File "/Users/evanrobinson/Documents/Luna2/luna/luna.py", line 152, in luna
    loop.run_until_complete(main_logic())
    ~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^
  File "/opt/homebrew/Cellar/python@3.13/3.13.1/Frameworks/Python.framework/Versions/3.13/lib/python3.13/asyncio/base_events.py", line 718, in run_until_complete
    raise RuntimeError('Event loop stopped before Future completed.')
RuntimeError: Event loop stopped before Future completed.
2025-01-12 15:33:28,561 [DEBUG] __main__: Preparing to close the event loop.
2025-01-12 15:33:28,561 [INFO] __main__: Event loop closed. Exiting main function.
2025-01-12 15:33:28,595 [ERROR] asyncio: Unclosed connector
connections: ['deque([(<aiohttp.client_proto.ResponseHandler object at 0x11de93f50>, 42509.1350415)])']
connector: <aiohttp.connector.TCPConnector object at 0x11de76350>
=== luna_command_extensions/__init__.py ===

=== luna_command_extensions/ascii_art.py ===
#!/usr/bin/env python3

import pyfiglet
import random

def show_ascii_banner(text: str):
    """
    Pick a random figlet font and print the given text in that font.
    """
    all_fonts = pyfiglet.FigletFont.getFonts()
    chosen_font = random.choice(all_fonts)
    ascii_art = pyfiglet.figlet_format(text, font=chosen_font)
    return(ascii_art)

def main():
    # 1) Show a big, randomly-fonted "LunaBot" banner
    print(show_ascii_banner("LUNABOT"))
    print(show_ascii_banner("LUNABOT"))
    print(show_ascii_banner("LUNABOT"))
    print(show_ascii_banner("LUNABOT"))
    print(show_ascii_banner("LUNABOT"))

if __name__ == "__main__":
    main()

=== luna_command_extensions/bot_invite_handler.py ===
# bot_invite_handler.py

import logging
from nio import LocalProtocolError, InviteMemberEvent
# from src.luna_personas import read_bot  # (uncomment if you want to load bot persona data)

logger = logging.getLogger(__name__)

async def handle_bot_invite(bot_client, bot_localpart, room, event):
    """
    Handles invite events for a single bot.

    :param bot_client: The AsyncClient belonging to this bot.
    :param bot_localpart: A string like "inky" or "clownsavior" (the localpart).
    :param room: The room object from matrix-nio.
    :param event: An InviteMemberEvent indicating an invitation.

    Example usage:
      bot_client.add_event_callback(
          lambda r, e: handle_bot_invite(bot_client, "inky", r, e),
          InviteMemberEvent
      )

    Optionally, you can load a persona (from disk, etc.) to see if autojoin is allowed:
      persona_data = read_bot(f"@{bot_localpart}:localhost")
      autojoin = persona_data.get("autojoin", True)
      if not autojoin:
          logger.info(f"Bot '{bot_localpart}' is configured not to join invites.")
          return
    """

    if not bot_client:
        logger.warning(
            f"[handle_bot_invite] No bot_client available for '{bot_localpart}'. Cannot handle invites."
        )
        return

    logger.info(
        f"[handle_bot_invite] Bot '{bot_localpart}' invited to {room.room_id}; attempting to join..."
    )

    try:
        await bot_client.join(room.room_id)
        logger.info(f"[handle_bot_invite] '{bot_localpart}' successfully joined {room.room_id}")
    except LocalProtocolError as e:
        logger.error(f"[handle_bot_invite] Error joining room {room.room_id}: {e}")

=== luna_command_extensions/bot_member_event_handler.py ===
# bot_member_event_handler.py

import logging
from nio import RoomMemberEvent, RoomGetStateEventError, RoomGetStateEventResponse

logger = logging.getLogger(__name__)

EVAN_USER_ID = "@evan:localhost"

async def handle_bot_member_event(bot_client, bot_localpart, room, event):
    """
    Handles membership changes for a single bot (or Luna) in 'room'.
      - If EVAN_USER_ID joins, set him to PL=100.
    """
    if not isinstance(event, RoomMemberEvent):
        return

    joined_user = event.sender
    logger.debug(
        f"[handle_bot_member_event] Bot '{bot_localpart}' sees {joined_user} joined {room.room_id}."
    )

    if joined_user == EVAN_USER_ID:
        logger.info(
            f"[handle_bot_member_event] => {EVAN_USER_ID} joined. Attempting to raise power to 100..."
        )
        try:
            await set_power_level(room.room_id, joined_user, 100, bot_client)
        except Exception as e:
            logger.exception(
                f"[handle_bot_member_event] Could not set PL for {joined_user}: {e}"
            )


async def set_power_level(room_id: str, user_id: str, new_level: int, bot_client):
    resp = await bot_client.room_get_state_event(
        room_id=room_id,
        event_type="m.room.power_levels",
        state_key=""
    )

    if not isinstance(resp, RoomGetStateEventResponse):
        logger.warning(
            f"[set_power_level] Unexpected response type => {type(resp)} : {resp}"
        )
        return

    pl_content = resp.content
    if not isinstance(pl_content, dict):
        logger.error(
            f"[set_power_level] power_levels content is not a dict => {pl_content}"
        )
        return

    logger.debug(f"[set_power_level] Current power_levels content => {pl_content}")

    # Insert / update the user's power level:
    users_dict = pl_content.get("users", {})
    users_dict[user_id] = new_level
    pl_content["users"] = users_dict

    logger.info(f"[set_power_level] Setting {user_id} to PL={new_level} in {room_id}...")

    update_resp = await bot_client.room_put_state(
        room_id=room_id,
        event_type="m.room.power_levels",
        content=pl_content,      # <-- This must be "content"
        state_key=""
    )

    if hasattr(update_resp, "status_code") and update_resp.status_code == 200:
        logger.info(
            f"[set_power_level] Successfully updated PL to {user_id}={new_level} in {room_id}."
        )
    else:
        logger.warning(
            f"[set_power_level] Attempted to set PL => {update_resp}"
        )

=== luna_command_extensions/bot_message_handler.py ===
# bot_message_handler.py

import logging
import time
import re
# import urllib.parse  # We won’t use URL-encoding for now
from nio import RoomMessageText, RoomSendResponse

# Adjust these imports to your project’s structure:
from luna import bot_messages_store         # or wherever you store your messages
import luna.context_helper as context_helper # your GPT context builder
from luna import ai_functions                # your GPT API logic

logger = logging.getLogger(__name__)
BOT_START_TIME = time.time() * 1000
# Regex to capture Matrix-style user mentions like "@username:domain"
MENTION_REGEX = re.compile(r"(@[A-Za-z0-9_\-\.]+:[A-Za-z0-9_\-\.]+)")

def build_mention_content(original_text: str) -> dict:
    """
    Scans the GPT reply for mentions like '@helpfulharry:localhost' and
    adds an <a href="matrix.to/#/@helpfulharry:localhost"> link in 'formatted_body'.
    Also populates 'm.mentions' with user_ids for explicit mention detection.
    
    We are NOT URL-encoding @ or underscores here—just a simple replacement.
    """

    # Find all mention strings (user IDs)
    matches = MENTION_REGEX.findall(original_text)
    html_text = original_text

    # We'll collect user IDs for 'm.mentions' here
    user_ids = []

    for mention in matches:
        user_ids.append(mention)
        # Example mention: "@helpful_harry:localhost"
        # We'll make a link like: <a href="https://matrix.to/#/@helpful_harry:localhost">@helpful_harry:localhost</a>
        url = f"https://matrix.to/#/{mention}"

        # The link text remains the original mention (with '@')
        html_link = f'<a href="{url}">{mention}</a>'

        # Replace plain mention with the linked mention in the HTML text
        html_text = html_text.replace(mention, html_link)

    # Construct the final content dict
    content = {
        "msgtype": "m.text",
        "body": original_text,             # plain-text fallback
        "format": "org.matrix.custom.html",
        "formatted_body": html_text
    }

    # If we found any mentions, add them to 'm.mentions'
    if user_ids:
        content["m.mentions"] = {"user_ids": user_ids}

    return content

async def handle_bot_room_message(bot_client, bot_localpart, room, event):
    """
    A “mention or DM” style message handler with GPT-based replies + message store.
    """
    # do not respond to messages from the past, under any circumstances
    if event.server_timestamp < BOT_START_TIME:
        logger.debug("Skipping old event => %s", event.event_id)
        return

    # 1) Must be a text event, and must not be from ourselves
    if not isinstance(event, RoomMessageText):
        return
    bot_full_id = bot_client.user  # e.g. "@blended_malt:localhost"
    if event.sender == bot_full_id:
        logger.debug(f"Bot '{bot_localpart}' ignoring its own message in {room.room_id}.")
        return

    # 2) Check for duplicates by event_id
    existing_msgs = bot_messages_store.get_messages_for_bot(bot_localpart)
    if any(m["event_id"] == event.event_id for m in existing_msgs):
        logger.info(
            f"[handle_bot_room_message] Bot '{bot_localpart}' sees event_id={event.event_id} "
            "already stored => skipping."
        )
        return

    # 3) Store the inbound text message
    bot_messages_store.append_message(
        bot_localpart=bot_localpart,
        room_id=room.room_id,
        event_id=event.event_id,
        sender=event.sender,
        timestamp=event.server_timestamp,
        body=event.body or ""
    )
    logger.debug(
        f"[handle_bot_room_message] Bot '{bot_localpart}' stored inbound event_id={event.event_id}."
    )

    # 4) Determine if we should respond (DM => always, group => only if mentioned)
    participant_count = len(room.users)
    content = event.source.get("content", {})
    mention_data = content.get("m.mentions", {})
    mentioned_ids = mention_data.get("user_ids", [])
    should_respond = False

    if participant_count == 2:
        # A 1-on-1 “direct chat” => always respond
        should_respond = True
    else:
        # If 3+ participants => respond only if we are mentioned
        if bot_full_id in mentioned_ids:
            should_respond = True

    if not should_respond:
        logger.debug(
            f"Bot '{bot_localpart}' ignoring group message with no mention. (room={room.room_id})"
        )
        return

    # -- BOT INDICATES TYPING START --
    try:
        await bot_client.room_typing(room.room_id, True, timeout=30000)
    except Exception as e:
        logger.warning(f"Could not send 'typing start' indicator => {e}")

    # 5) Build GPT context (the last N messages, plus a system prompt if you want)
    config = {"max_history": 20}  # adjust as needed
    gpt_context = context_helper.build_context(bot_localpart, room.room_id, config)

    # 6) Call GPT
    gpt_reply = await ai_functions.get_gpt_response(
        messages=gpt_context,
        model="gpt-4",
        temperature=0.7
    )

    # 7) Convert GPT reply => mention-aware content (including m.mentions)
    reply_content = build_mention_content(gpt_reply)

    # 8) Post GPT reply
    resp = await bot_client.room_send(
        room_id=room.room_id,
        message_type="m.room.message",
        content=reply_content,
    )

    # -- BOT INDICATES TYPING STOP --
    try:
        await bot_client.room_typing(room.room_id, False)
    except Exception as e:
        logger.warning(f"Could not send 'typing stop' indicator => {e}")

    # 9) Store outbound
    if isinstance(resp, RoomSendResponse) and resp.event_id:
        outbound_eid = resp.event_id
        logger.info(
            f"Bot '{bot_localpart}' posted a GPT reply event_id={outbound_eid} in {room.room_id}."
        )
        bot_messages_store.append_message(
            bot_localpart=bot_localpart,
            room_id=room.room_id,
            event_id=outbound_eid,
            sender=bot_full_id,
            timestamp=int(time.time() * 1000),
            body=gpt_reply
        )
    else:
        logger.warning(
            f"Bot '{bot_localpart}' posted GPT reply but got no official event_id (room={room.room_id})."
        )

=== luna_command_extensions/check_synapse_status.py ===
# src/luna_command_extensions/check_synapse_status.py

import aiohttp
import logging

logger = logging.getLogger(__name__)

# ANSI color codes
GREEN = "\x1b[32m"
RED = "\x1b[31m"
YELLOW = "\x1b[33m"
RESET = "\x1b[0m"

async def checkSynapseStatus(homeserver_url: str = "http://localhost:8008") -> str:
    """
    Checks if the Synapse server at 'homeserver_url' is online.
    Returns a color-coded status string: e.g. "[ONLINE]", "[OFFLINE]", or "[UNKNOWN]".
    """
    # Default to UNKNOWN if something unexpected happens
    status_str = f"{YELLOW}[UNKNOWN]{RESET}"
    try:
        # We'll just try a simple GET on the root
        async with aiohttp.ClientSession() as session:
            async with session.get(homeserver_url, timeout=2) as resp:
                if resp.status == 200:
                    logger.debug("Synapse server responded with 200 OK.")
                    status_str = f"{GREEN}[ONLINE]{RESET}"
                else:
                    logger.debug(f"Synapse server responded with status={resp.status}.")
                    status_str = f"{RED}[OFFLINE]{RESET}"
    except Exception as e:
        logger.warning(f"checkSynapseStatus: Could not connect to Synapse => {e}")
        status_str = f"{RED}[OFFLINE]{RESET}"

    return status_str

=== luna_command_extensions/chunk_and_summarize.py ===
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

=== luna_command_extensions/cmd_banner.py ===
# cmd_banner.py
import logging
from luna_command_extensions.ascii_art import show_ascii_banner
logger = logging.getLogger(__name__)


########################################################
# 1) COMMAND HANDLER FUNCTIONS
########################################################
def cmd_banner(args, loop):
    print ("\n" + show_ascii_banner("Luna Bot"))

=== luna_command_extensions/cmd_exit.py ===
from luna_command_extensions.cmd_shutdown import request_shutdown
import logging

logger = logging.getLogger(__name__)


def cmd_exit(args, loop):
    """
    Usage: exit

    Gracefully shuts down Luna by setting the shutdown flag
    and stopping the main loop.
    """
    logger.info("Console received 'exit' command; requesting shutdown.")
    print("SYSTEM: Shutting down Luna gracefully...")    
    request_shutdown()

=== luna_command_extensions/cmd_generate_image.py ===
import asyncio
import shlex
import logging
from luna.ai_functions import generate_image_save_and_post
from luna.luna_functions import getClient

logger = logging.getLogger(__name__)

def cmd_generate_image(args, loop):
    """
    Usage: generate_image "<prompt text>" [--size 512x512] [--room !roomid:localhost]

    Example:
      generate_image "A Starship Aurora in deep space" --size 512x512 --room !abc123:localhost

    This console command:
      1) Parses a text prompt and optional size/room arguments.
      2) Calls 'generate_image_save_and_post' on the event loop.
      3) Saves the image locally and sends it to the specified room (defaults to Evan's DM).
    """

    # Default values
    default_room_id = "!someRoomEvanAndLunaShare:localhost"  # Replace with Evan's actual room ID
    default_size = "1024x1024"

    # Parse arguments with shlex to handle quoted prompts
    try:
        tokens = shlex.split(args)
    except ValueError as e:
        print(f"SYSTEM: Error parsing arguments => {e}")
        return

    if not tokens:
        print("Usage: generate_image \"<prompt>\" [--size 512x512] [--room !roomid:localhost]")
        return

    # The prompt is assumed to be the first token unless preceded by flags
    prompt = None
    room_id = default_room_id
    size = default_size

    # We'll iterate over tokens and look for flags
    # e.g.  "A Starship Aurora in deep space" --size 512x512 --room !abc123:localhost
    # tokens might be: ["A Starship Aurora in deep space", "--size", "512x512", "--room", "!abc123:localhost"]

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == "--size":
            i += 1
            if i < len(tokens):
                size = tokens[i]
        elif token == "--room":
            i += 1
            if i < len(tokens):
                room_id = tokens[i]
        else:
            # If prompt is not yet set, assume this token is the prompt
            # (In many cases, the entire first token is the prompt if it's quoted.)
            # If you want to allow multi-token prompts without quotes, you'll need more parsing logic.
            if prompt is None:
                prompt = token
            else:
                # If there's already a prompt, append with space
                prompt += f" {token}"
        i += 1

    if not prompt:
        print("SYSTEM: No prompt text found. Usage: generate_image \"<prompt>\" [--size 512x512] [--room !roomid:localhost]")
        return

    # Grab the client
    client = getClient()
    if not client:
        print("SYSTEM: No DIRECTOR_CLIENT available, cannot proceed.")
        return

    def do_generate():
        # We call the async function in a thread-safe manner
        try:
            # Schedule the coroutine and wait for result
            future = asyncio.run_coroutine_threadsafe(
                generate_image_save_and_post(prompt, client, room_id, size=size),
                loop
            )
            future.result()  # blocks until complete
            print("SYSTEM: Image generation process completed.")
        except Exception as e:
            logger.exception("Error in do_generate while calling generate_image_save_and_post:")
            print(f"SYSTEM: Exception => {e}")

    do_generate()
    print("SYSTEM: Finished cmd_generate_image command.")
=== luna_command_extensions/cmd_help.py ===
from console_functions import COMMAND_ROUTER
import logging
import textwrap
logger = logging.getLogger(__name__)

def cmd_help(args, loop):
    """
    Usage: help

    Show usage for all known commands in a more readable multi-line format.
    """
    logger.debug("Showing help to user.")
    print("SYSTEM: Available commands:\n")

    # A small utility to wrap text nicely at ~70 characters, for readability.
    wrapper = textwrap.TextWrapper(width=70, subsequent_indent="    ")

    for cmd_name, cmd_func in COMMAND_ROUTER.items():
        doc = (cmd_func.__doc__ or "").strip()
        if not doc:
            usage_line = f"(No usage info for `{cmd_name}`)"
            description = ""
        else:
            # Split docstring lines
            lines = doc.splitlines()
            usage_line = ""
            description = ""

            # We assume first line is "Usage:", subsequent lines are description
            if lines:
                first_line = lines[0].strip()
                if first_line.startswith("Usage:"):
                    usage_line = first_line
                    # Join the rest as the description
                    if len(lines) > 1:
                        description = " ".join(l.strip() for l in lines[1:] if l.strip())
                else:
                    # If we didn't find "Usage:" up front, treat everything as description
                    usage_line = "(No usage line found.)"
                    description = " ".join(l.strip() for l in lines if l.strip())

        # Wrap the usage and description
        usage_line_wrapped = wrapper.fill(usage_line)
        description_wrapped = wrapper.fill(description)

        print(f"{cmd_name}\n  {usage_line_wrapped}")
        if description_wrapped:
            print(f"  {description_wrapped}")
        print()  # blank line after each command
=== luna_command_extensions/cmd_remove_room.py ===
import logging
import asyncio
import aiohttp
from luna import luna_functions

logger = logging.getLogger(__name__)

def cmd_remove_room(args, loop):
    """
    Usage: remove_room <room_id>

    Example:
      remove_room !abc123:localhost

    This console command removes the room from the homeserver
    entirely using the Synapse Admin API:
      DELETE /_synapse/admin/v2/rooms/<roomID>

    Must be an admin user. This does not remove messages in a graceful
    manner—those events become orphaned. But the room
    is fully deleted from Synapse’s perspective, and future attempts
    to join or invite this room ID will fail.

    If you want to only forget the room from your perspective,
    do a normal "forget" in a Matrix client. This command is destructive.
    """

    parts = args.strip().split()
    if len(parts) < 1:
        print("SYSTEM: Usage: remove_room <room_id>")
        return

    room_id = parts[0]

    # The asynchronous subroutine:
    async def _do_remove_room(rid: str) -> str:
        """
        Actually calls the DELETE /_synapse/admin/v2/rooms/{roomId} endpoint.
        Must have admin privileges. 
        Sends an empty JSON body with Content-Type: application/json to avoid
        "Content not JSON" errors.
        """
        client = luna_functions.getClient()
        if not client:
            return "[Error] No DIRECTOR_CLIENT set or not logged in."

        admin_token = client.access_token
        if not admin_token:
            return "[Error] No admin token in DIRECTOR_CLIENT (need to be a Synapse admin)."

        homeserver_url = client.homeserver
        endpoint = f"{homeserver_url}/_synapse/admin/v2/rooms/{rid}"

        headers = {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json"
        }

        logger.debug(f"[_do_remove_room] Attempting to DELETE room => {endpoint}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(endpoint, headers=headers, json={}) as resp:
                    if resp.status in (200, 202):
                        return f"Successfully removed room => {rid}"
                    else:
                        text = await resp.text()
                        return f"Error removing room {rid}: {resp.status} => {text}"
        except Exception as e:
            logger.exception("[_do_remove_room] Exception calling admin API:")
            return f"Exception removing room => {e}"

    # The blocking wrapper:
    def do_remove_room_sync(rid: str) -> str:
        """
        Schedules _do_remove_room(...) on the event loop, then blocks until
        it finishes by calling future.result().
        """
        future = asyncio.run_coroutine_threadsafe(_do_remove_room(rid), loop)
        return future.result()

    print(f"SYSTEM: Removing room '{room_id}' from server (blocking)... Please wait.")
    # Actually run the removal, blocking until it's done
    result_msg = do_remove_room_sync(room_id)
    print(f"SYSTEM: {result_msg}")

=== luna_command_extensions/cmd_shutdown.py ===
# shutdown_helper.py

import asyncio

SHOULD_SHUT_DOWN = False
MAIN_LOOP: asyncio.AbstractEventLoop | None = None

def init_shutdown(loop: asyncio.AbstractEventLoop) -> None:
    """
    Store the given event loop in our local global variable.
    Call this once in luna.py after creating the event loop.
    """
    global MAIN_LOOP
    MAIN_LOOP = loop

def request_shutdown() -> None:
    """
    Sets the SHOULD_SHUT_DOWN flag to True and stops the MAIN_LOOP if it's running.
    """
    global SHOULD_SHUT_DOWN
    SHOULD_SHUT_DOWN = True

    if MAIN_LOOP and MAIN_LOOP.is_running():
        MAIN_LOOP.call_soon_threadsafe(MAIN_LOOP.stop)

=== luna_command_extensions/cmd_summarize_room.py ===
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

=== luna_command_extensions/command_router.py ===
"""
command_router.py

Defines:
  - Command functions (create_room, invite_user, etc.) each with docstrings.
  - A help command that builds an HTML table from these docstrings.
  - A router that maps command strings to their respective functions.
  - The handle_console_command() dispatcher that interprets and calls them.
"""

import logging
import asyncio
import inspect
import shlex
import os
import time
import requests
from nio import AsyncClient, RoomSendResponse
import yaml
import os
from luna.luna_command_extensions.image_helpers import direct_upload_image
from luna.luna_command_extensions.spawn_persona import cmd_spawn
from luna.luna_personas import read_bot, update_bot

CONFIG_PATH = "data/config/config.yaml"

# Import your existing 'generate_image' function
from luna.ai_functions import generate_image
# If you have a direct_upload_image helper, import it too:

logger = logging.getLogger(__name__)

# -------------------------------------------------------------
# GLOBAL PARAM STORE (for set_param / get_param)
# -------------------------------------------------------------
GLOBAL_PARAMS = {}

# -------------------------------------------------------------
# COMMAND FUNCTIONS
# -------------------------------------------------------------

async def create_room(
    bot_client: AsyncClient,
    sender: str,
    localpart: str,
    topic: str = None,
    is_public: bool = True,
) -> str:
    """
    Usage:
      !create_room <localpart> [topic="..."] [public|private]

    Create a new room using the given localpart (e.g. '#myroom').
    Invites the sender with power level 100, sets optional topic,
    and sets visibility (public or private).
    """
    domain = "localhost"
    full_alias = f"{localpart}:{domain}"
    visibility = "public" if is_public else "private"

    try:
        logger.info(f"[create_room] Creating room alias={full_alias}, topic={topic}, visibility={visibility}")
        resp = await bot_client.room_create(
            visibility=visibility,
            alias=full_alias,
            name=localpart.strip("#"),  # display name
            topic=topic,
        )
        if not resp.room_id:
            return f"Error: Could not create room {full_alias} => {resp}"
        room_id = resp.room_id

        # Invite the user who issued the command
        invite_resp = await bot_client.room_invite(room_id, sender)
        if not (invite_resp and invite_resp.transport_response.ok):
            return f"Warning: Could not invite {sender} => {invite_resp}"

        # Elevate them to PL100
        await _set_power_level(bot_client, room_id, sender, 100)
        return f"Room created: {full_alias} (ID: {room_id}), invited {sender} with PL100."
    except Exception as e:
        logger.exception("[create_room] Error =>")
        return f"Error creating room => {e}"


async def _set_power_level(bot_client: AsyncClient, room_id: str, user_id: str, power: int):
    """Helper to set a user's power level in a given room."""
    state_resp = await bot_client.room_get_state_event(room_id, "m.room.power_levels", "")
    current_content = state_resp.event.source.get("content", {})

    users_dict = current_content.get("users", {})
    users_dict[user_id] = power
    current_content["users"] = users_dict

    await bot_client.room_send_state(
        room_id=room_id,
        event_type="m.room.power_levels",
        state_key="",
        content=current_content,
    )


async def invite_user(bot_client: AsyncClient, user_id: str, room_localpart: str) -> str:
    """
    Usage:
      !invite_user <user_id> <room_localpart>

    Invite the given user to the specified room localpart
    (e.g. '#observation_deck').
    """
    domain = "localhost"
    full_alias = f"{room_localpart}:{domain}"

    try:
        resolve_resp = await bot_client.room_resolve_alias(full_alias)
        if not resolve_resp.room_id:
            return f"Error: Could not resolve alias => {full_alias}"
        room_id = resolve_resp.room_id

        invite_resp = await bot_client.room_invite(room_id, user_id)
        if invite_resp and invite_resp.transport_response.ok:
            return f"Invited {user_id} to {full_alias} (ID: {room_id})."
        else:
            return f"Error: Could not invite => {invite_resp}"
    except Exception as e:
        logger.exception("[invite_user] Error =>")
        return f"Error => {e}"


async def list_rooms(bot_client: AsyncClient) -> str:
    """
    Usage:
      !list_rooms

    Return a list of rooms the bot is currently in, formatted as an HTML table,
    with columns in the order: (Name, Alias, Room ID).
    """
    # Collect info in a list of (room_id, alias, name)
    room_info = []
    for room_id, room_obj in bot_client.rooms.items():
        alias = getattr(room_obj, "canonical_alias", None) or ""
        name = room_obj.name or ""
        room_info.append((room_id, alias, name))

    if not room_info:
        return "<p>No rooms found.</p>"

    # Build a table with columns: Name, Alias, Room ID
    rows = []
    for r_id, r_alias, r_name in room_info:
        row_html = (
            "<tr>"
            f"<td>{r_name}</td>"    # Name
            f"<td>{r_alias}</td>"   # Alias
            f"<td>{r_id}</td>"      # Room ID
            "</tr>"
        )
        rows.append(row_html)

    # Combine rows into a table
    table_html = (
        "<p><strong>Rooms the bot is currently in:</strong></p>"
        "<table border='1' style='border-collapse:collapse; margin:1em 0;'>"
        "<thead>"
        "<tr><th>Name</th><th>Alias</th><th>Room ID</th></tr>"
        "</thead>"
        "<tbody>"
        + "".join(rows) +
        "</tbody>"
        "</table>"
    )

    return table_html


async def draw_command(bot_client: AsyncClient, room_id: str, user_prompt: str) -> str:
    """
    Usage:
      !draw <prompt>

    Generates an image from the user's prompt, appending a global
    style (found in GLOBAL_PARAMS['global_draw_prompt_appendix']) if present,
    then uploads the image to Matrix and sends it to the given room.
    Returns a success or error message.
    """
    # -----------------------------------------------------------------
    # 2) Generate the image via your existing ai_functions.generate_image()
    #    => returns a public image URL
    # -----------------------------------------------------------------
    try:
        image_url = generate_image(user_prompt, size="1024x1024")
    except Exception as e:
        logger.exception("[draw_command] Error generating image.")
        return f"Error generating image => {e}"

    logger.info("[draw_command] Image generated, URL => %s", image_url)

    # -----------------------------------------------------------------
    # 3) Download the image to disk
    # -----------------------------------------------------------------
    try:
        logger.debug("[draw_command] Downloading image from %s", image_url)
        os.makedirs("data/images", exist_ok=True)
        timestamp = int(time.time())
        filename = f"data/images/generated_image_{timestamp}.jpg"

        dl_resp = requests.get(image_url)
        dl_resp.raise_for_status()

        with open(filename, "wb") as f:
            f.write(dl_resp.content)

        logger.debug("[draw_command] Image saved to %s", filename)
    except Exception as e:
        logger.exception("[draw_command] Error downloading image.")
        return f"Error downloading the image => {e}"

    # -----------------------------------------------------------------
    # 4) Upload to Matrix (direct_upload_image or client.upload)
    # -----------------------------------------------------------------
    try:
        logger.debug("[draw_command] Uploading image to Matrix.")
        
        mxc_url = await direct_upload_image(bot_client, filename, "image/jpeg")
        logger.debug("[draw_command] Upload success => %s", mxc_url)
    except Exception as e:
        logger.exception("[draw_command] Error uploading image to Matrix.")
        return f"Error uploading image => {e}"

    # -----------------------------------------------------------------
    # 5) Send the m.image event to the room
    # -----------------------------------------------------------------
    try:
        file_size = os.path.getsize(filename)
        image_content = {
            "msgtype": "m.image",
            "body": os.path.basename(filename),
            "url": mxc_url,
            "info": {
                "mimetype": "image/jpeg",
                "size": file_size,
                "w": 1024,
                "h": 1024
            },
        }
        logger.debug("[draw_command] Sending image content => %s", image_content)

        img_response = await bot_client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content=image_content,
        )

        if isinstance(img_response, RoomSendResponse):
            return f"Image posted successfully! Prompt: '{user_prompt}'"
        else:
            logger.warning("[draw_command] Unexpected response => %s", img_response)
            return "Failed to send the image to the room."
    except Exception as e:
        logger.exception("[draw_command] Error sending the image event.")
        return f"Error sending the image => {e}"

def get_param(param_name: str) -> str:
    """
    1) Check in-memory GLOBAL_PARAMS first (quick read).
    2) If not found, load from config.yaml -> 'globals' -> param_name.
    3) Return the string value or a "not found" message.
    """
    # Check in-memory
    if param_name in GLOBAL_PARAMS:
        return str(GLOBAL_PARAMS[param_name])

    # Otherwise, load from config
    cfg = load_config()
    globals_section = cfg.get("globals", {})
    val = globals_section.get(param_name)
    if val is not None:
        # Store it in memory so next time we don't have to reload
        GLOBAL_PARAMS[param_name] = val
        return str(val)

    return f"No param set for '{param_name}'."

def set_param(param_name: str, value: str) -> str:
    """
    1) Update in-memory GLOBAL_PARAMS.
    2) Also persist to config.yaml in the 'globals' section.
    3) Return a confirmation message.
    """
    # Update in-memory
    GLOBAL_PARAMS[param_name] = value

    # Persist to config.yaml
    cfg = load_config()
    if "globals" not in cfg:
        cfg["globals"] = {}
    cfg["globals"][param_name] = value
    save_config(cfg)

    return f"Set {param_name} => {value}"

async def help_command(*args, **kwargs) -> str:
    """
    Usage:
      !help

    Show help for all available commands, displaying usage and description
    in a beautiful HTML table.
    """
    table_html = build_help_table()
    return table_html

def list_params() -> str:
    """
    Usage:
      !list_params

    Lists all key-value pairs in the GLOBAL_PARAMS dictionary, formatted as an HTML table.
    """
    if not GLOBAL_PARAMS:
        return "<p>No parameters have been set.</p>"

    rows = []
    for key, val in GLOBAL_PARAMS.items():
        row = (
            "<tr>"
            f"<td>{key}</td>"
            f"<td>{val}</td>"
            "</tr>"
        )
        rows.append(row)

    table_html = (
        "<p><strong>Current Global Parameters</strong></p>"
        "<table border='1' style='border-collapse:collapse; margin:1em 0;'>"
        "<thead><tr><th>Param Name</th><th>Value</th></tr></thead>"
        "<tbody>"
        + "".join(rows) +
        "</tbody></table>"
    )

    return table_html

async def luna_gpt(bot_client: AsyncClient, room_id: str, raw_args: str) -> str:
    """
    Usage:
      !luna <prompt>

    Sends the user's prompt through GPT with a full context build for Luna,
    using `context_helper.build_context`. Returns GPT's plain-text response.

    Handles both quoted and non-quoted inputs by stripping leading/trailing quotes.
    Examples:
      !luna "Hello world"
      !luna Hello world
    """
    # 1) Strip leading/trailing quotes or whitespace.
    #    If raw_args is something like '"Hello world"', we remove the quotes.
    #    If it's unquoted (e.g. 'Hello world'), we still trim leading/trailing spaces.
    prompt = raw_args.strip().strip('"\'')
    if not prompt:
        return "Usage: !luna <prompt>"

    from luna.context_helper import build_context  # Ensure correct import path
    from luna.ai_functions import get_gpt_response  # Ensure correct import path

    # 2) Build Luna’s GPT context for this room
    try:
        context_config = {"max_history": 20}
        gpt_context = build_context("lunabot", room_id, context_config)
        gpt_context.append({"role": "user", "content": prompt})

        logger.debug("[luna_gpt] GPT context built: %s", gpt_context)

        # 3) Call GPT with the context and user’s final prompt
        gpt_response = await get_gpt_response(
            messages=gpt_context,
            model="chatgpt-4o-latest",
            temperature=0.7
        )
        logger.debug("[luna_gpt] GPT response: %s", gpt_response)

        # 4) Return the plain-text response to the caller
        return gpt_response

    except Exception as e:
        logger.exception("[luna_gpt] Error generating response:")
        return f"Error generating response: {e}"

# -------------------------------------------------------------
# BUILD HELP TABLE
# -------------------------------------------------------------
def build_help_table() -> str:
    """
    Dynamically build an HTML table showing [Command | Usage | Description]
    by parsing docstrings from each command.
    """
    rows = []
    sorted_commands = sorted(COMMAND_ROUTER.items())

    for cmd_name, func in sorted_commands:
        usage, description = parse_command_doc(func)
        row = (
            f"<tr>"
            f"<td><b>{cmd_name}</b></td>"
            f"<td>{usage}</td>"
            f"<td>{description}</td>"
            f"</tr>"
        )
        rows.append(row)

    table = (
        "<table border='1' style='border-collapse: collapse; margin:1em 0;'>"
        "<thead><tr><th>Command</th><th>Usage</th><th>Description</th></tr></thead>"
        "<tbody>"
        + "".join(rows) +
        "</tbody></table>"
    )

    html = (
        "<p><strong>Available Commands</strong></p>"
        + table
    )
    return html


def parse_command_doc(func) -> tuple[str, str]:
    """
    Extract usage and a short description from a function's docstring.
    Expects docstring lines like:
        Usage:
          !command_name <args>

        A longer description...
    """
    doc = inspect.getdoc(func) or ""
    lines = doc.splitlines()
    usage_line = ""
    description_lines = []

    for line in lines:
        line_stripped = line.strip()
        if line_stripped.lower().startswith("usage:"):
            usage_line = line_stripped[len("usage:"):].strip()
        else:
            description_lines.append(line_stripped)

    usage = usage_line
    description = " ".join(description_lines).strip()
    return usage, description

# -------------------------------------------------------------
# COMMAND DISPATCHER
# -------------------------------------------------------------
async def handle_console_command(bot_client: AsyncClient, room_id: str, message_body: str, sender: str) -> str:
    """
    Parse the message (which starts with '!'), extract command name & args,
    invoke the appropriate function from COMMAND_ROUTER, and return the result.
    Now we pass 'room_id' into commands like 'draw_command' so it can post images.
    """
    cmd_line = message_body[1:].strip()

    try:
        parts = shlex.split(cmd_line)
    except ValueError as e:
        return f"SYSTEM: Error parsing command => {e}"

    if not parts:
        return "SYSTEM: No command entered."

    command_name = parts[0].lower()
    args = parts[1:]

    if command_name not in COMMAND_ROUTER:
        return f"SYSTEM: Unrecognized command '{command_name}'."

    command_func = COMMAND_ROUTER[command_name]

    # Dispatch to the correct function
    if command_name == "create_room":
        if not args:
            return "Usage: !create_room <localpart> [topic=\"...\"] [public|private]"
        localpart = args[0]
        topic = None
        is_public = True

        for extra in args[1:]:
            if extra.startswith("topic="):
                topic_val = extra.split("=", 1)[1].strip('"')
                topic = topic_val
            elif extra.lower() in ["public", "private"]:
                is_public = (extra.lower() == "public")

        return await command_func(bot_client, sender, localpart, topic, is_public)

    elif command_name == "set_avatar":
        # We expect exactly two arguments: <localpart> and <mxc_uri_or_mediaID>
        if len(args) < 2:
            return "Usage: !set_avatar <localpart> <mxc_uri_or_mediaID>"
        
        localpart = args[0]
        mxc_or_media_id = args[1]

        # Pass both arguments as a single string to cmd_set_avatar
        args_string = f"{localpart} {mxc_or_media_id}"
        return await command_func(args_string)


    elif command_name == "invite_user":
        if len(args) < 2:
            return "Usage: !invite_user <user_id> <room_localpart>"
        user_id = args[0]
        localpart = args[1]
        return await command_func(bot_client, user_id, localpart)

    elif command_name == "list_params":
        # No arguments expected
        if args:
            return "Usage: !list_params  (no arguments needed)"
        return command_func()

    elif command_name == "luna":
        if not args:
            return "Usage: !luna <prompt>"
        prompt = " ".join(args)
        return await command_func(bot_client, room_id, prompt)
    
    elif command_name == "draw":
        # Now pass in the 'room_id' so we can post the image there
        if not args:
            return "Usage: !draw <prompt>"
        prompt = " ".join(args)
        return await command_func(bot_client, room_id, prompt)

    elif command_name == "list_rooms":
        return await command_func(bot_client)

    elif command_name == "spawn":
        if not args:
            return "Usage: !spawn <descriptor>"
        descriptor = " ".join(args)
        return await command_func(bot_client, descriptor)

    elif command_name == "help":
        return await command_func()

    elif command_name == "set_param":
        if len(args) < 2:
            return "Usage: !set_param <param_name> <value>"
        param_name = args[0]
        value = " ".join(args[1:])
        return command_func(param_name, value)

    elif command_name == "get_param":
        if len(args) < 1:
            return "Usage: !get_param <param_name>"
        param_name = args[0]
        return command_func(param_name)

    # fallback if not handled above
    return f"SYSTEM: Command '{command_name}' is recognized but not handled."

def load_config() -> dict:
    """
    Loads the YAML config from disk into a dict.
    Returns an empty dict if file not found or invalid.
    """
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def save_config(config_data: dict) -> None:
    """
    Writes the config_data dict back to config.yaml, overwriting existing content.
    """
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_data, f)

async def cmd_set_avatar(args: str) -> str:
    """
    Usage:
      set_avatar <localpart> <mxc_uri_or_mediaID>

    Examples:
      set_avatar ghostbot mxc://localhost/HASH123
      set_avatar ghostbot HASH123

    This command:
      1) Looks up the persona data for @<localpart>:localhost to get password, etc.
      2) If we already have an ephemeral bot client loaded, use it; otherwise ephemeral-login.
      3) If the second argument is a raw media ID (no 'mxc://'), we prepend 'mxc://localhost/'.
      4) Calls .set_avatar(<mxc URI>).
      5) Also updates the persona's "portrait_url" trait in personalities.json (so it persists).
      6) Returns a success or error message.
    """
    tokens = shlex.split(args)
    if len(tokens) < 2:
        return "Usage: set_avatar <localpart> <mxc_uri_or_mediaID>"

    localpart = tokens[0]
    raw_avatar_arg = tokens[1]

    # 1) Build the final mxc URI
    if raw_avatar_arg.startswith("mxc://"):
        mxc_uri = raw_avatar_arg
    else:
        # Assume it's just the media ID, e.g. 'jyTMtUvNgbtLcKIvJnoQQtTj'
        # Prepend the local domain name. Adjust if your domain is not 'localhost'.
        mxc_uri = f"mxc://localhost/{raw_avatar_arg}"

    # 2) Read persona to get password, confirm it exists
    full_user_id = f"@{localpart}:localhost"
    persona = read_bot(full_user_id)
    if not persona:
        return f"No persona found for {full_user_id}. Please create one first."

    password = persona.get("password")
    if not password:
        return f"Persona for {full_user_id} has no password stored. Can't ephemeral-login."

    # 3) Attempt to find an existing ephemeral client in your BOTS dict, or ephemeral-login
    #    We'll do a minimal approach: if it's not in BOTS, ephemeral login
    from luna.core import BOTS
    bot_client = BOTS.get(localpart)

    if not bot_client:
        logger.debug(f"[set_avatar] No ephemeral client for '{localpart}' in BOTS.")
    else:
        logger.debug(f"[set_avatar] Found existing ephemeral client for '{localpart}' in BOTS.")

    # 4) Now set the avatar
    try:
        await bot_client.set_avatar(mxc_uri)
    except Exception as e:
        logger.exception("Error setting avatar =>")
        return f"Error setting avatar => {e}"

    # 5) Update the persona's traits to store 'portrait_url' or something similar
    updated_traits = persona.get("traits", {})
    updated_traits["portrait_url"] = mxc_uri
    update_bot(
        full_user_id,
        {
            "traits": updated_traits
        }
    )

    return f"Set avatar for {full_user_id} => {mxc_uri}"

# -------------------------------------------------------------
# COMMAND ROUTER
# -------------------------------------------------------------
COMMAND_ROUTER = {
    "create_room": create_room,    # async
    "invite_user": invite_user,    # async
    "list_rooms":  list_rooms,     # async
    "help":        help_command,   # async
    "set_param":   set_param,      # sync
    "get_param":   get_param,      # sync,
    "list_params": list_params,
    "draw":        draw_command,   # now posts the actual image
    "luna":        luna_gpt,
    "spawn":       cmd_spawn,
    "set_avatar":  cmd_set_avatar
}
=== luna_command_extensions/create_and_login_bot.py ===
"""
create_and_login_bot.py

Handles creating a new bot persona record + user account + ephemeral login,
THEN registers event handlers & spawns the bot's sync loop.
"""

import logging
import asyncio
import re
import secrets  # for fallback random localpart (if needed)

from nio import RoomMessageText, InviteMemberEvent, RoomMemberEvent, AsyncClient

# Adjust these imports to match your new layout:
import luna.luna_personas
from luna.luna_functions import (
    create_user,
    load_or_login_client_v2
)
from luna.luna_command_extensions.bot_message_handler import handle_bot_room_message
from luna.luna_command_extensions.bot_member_event_handler import handle_bot_member_event
from luna.luna_command_extensions.bot_invite_handler import handle_bot_invite

logger = logging.getLogger(__name__)

# Regex that matches valid characters for localparts in Matrix user IDs:
# (Synapse typically allows `[a-z0-9._=/-]+` by default).
VALID_LOCALPART_REGEX = re.compile(r'[a-z0-9._=\-/]+')

async def create_and_login_bot(
    bot_id: str,
    password: str,
    displayname: str,
    system_prompt: str,
    traits: dict,
    creator_user_id: str = "@lunabot:localhost",
    is_admin: bool = False
) -> tuple[str, AsyncClient | None]:
    """
    1) Creates a local persona entry in personalities.json (using bot_id as key).
    2) Calls create_user(...) to register with Synapse.
    3) Does ephemeral login (load_or_login_client_v2) => returns an AsyncClient for that user.
    4) Registers event handlers, spawns the bot’s sync loop.
    5) Stores references (AsyncClient + sync task) in the global BOTS/TASKS.
    6) Returns (success_message, ephemeral_bot_client). If something fails, returns (error_msg, None).
    """

    logger.debug("[create_and_login_bot] Called with bot_id=%r, displayname=%r", bot_id, displayname)

    # 1) Validate & parse localpart
    if not bot_id.startswith("@") or ":" not in bot_id:
        err = f"[create_and_login_bot] Invalid bot_id => {bot_id}"
        logger.warning(err)
        return (err, None)

    original_localpart = bot_id.split(":")[0].replace("@", "", 1)
    logger.debug("Original localpart extracted => %r", original_localpart)

    # 2) Sanitize localpart
    tmp = original_localpart.lower()
    sanitized = "".join(ch for ch in tmp if VALID_LOCALPART_REGEX.match(ch))
    if not sanitized:
        random_suffix = secrets.token_hex(4)
        sanitized = f"bot_{random_suffix}"
        logger.debug("Localpart was invalid, using fallback => %r", sanitized)
    elif sanitized != original_localpart.lower():
        logger.debug("Sanitized localpart from %r to %r", original_localpart, sanitized)

    new_bot_id = f"@{sanitized}:localhost"
    logger.debug("Final bot_id => %r", new_bot_id)
    bot_id = new_bot_id

    # 3) Create persona in personalities.json
    try:
        logger.debug("Creating persona in personalities.json => %r", bot_id)
        luna.luna_personas.create_bot(
            bot_id=bot_id,
            password=password,
            displayname=displayname,
            creator_user_id=creator_user_id,
            system_prompt=system_prompt,
            traits=traits
        )
        logger.info("[create_and_login_bot] Persona created for %s.", bot_id)
    except Exception as e:
        msg = f"[create_and_login_bot] Could not create persona => {e}"
        logger.exception(msg)
        return (msg, None)

    # 4) Create the user in Synapse
    matrix_localpart = sanitized
    logger.debug("Attempting create_user(localpart=%r)", matrix_localpart)
    creation_msg = await create_user(matrix_localpart, password, is_admin=is_admin)
    if not creation_msg.startswith("Created user"):
        err = f"[create_and_login_bot] Synapse user creation failed => {creation_msg}"
        logger.error(err)
        return (err, None)

    # 5) Ephemeral login
    try:
        logger.debug("Attempting ephemeral login => bot_id=%r", bot_id)
        client = await load_or_login_client_v2(
            homeserver_url="http://localhost:8008",
            user_id=bot_id,
            password=password,
            device_name=f"{sanitized}_device"
        )
        logger.info("[create_and_login_bot] Ephemeral login success => %s", bot_id)
    except Exception as e:
        logger.exception("[create_and_login_bot] Ephemeral login failed => %s", e)
        return (f"Error ephemeral-logging in {bot_id}: {e}", None)

    # 6) Register event callbacks
    client.add_event_callback(
        lambda room, evt: handle_bot_room_message(client, sanitized, room, evt),
        RoomMessageText
    )
    client.add_event_callback(
        lambda room, evt: handle_bot_invite(client, sanitized, room, evt),
        InviteMemberEvent
    )
    client.add_event_callback(
        lambda room, evt: handle_bot_member_event(client, sanitized, room, evt),
        RoomMemberEvent
    )
    logger.info("[create_and_login_bot] Registered event handlers for '%s'.", sanitized)

    # 7) Start the sync loop & store references
    try:
        from luna.core import BOTS, BOT_TASKS, run_bot_sync
        BOTS[sanitized] = client
        sync_task = asyncio.create_task(run_bot_sync(client, sanitized))
        BOT_TASKS.append(sync_task)
        logger.info("[create_and_login_bot] Bot '%s' sync loop started.", sanitized)
    except Exception as e:
        logger.exception("[create_and_login_bot] Could not store references or start sync => %s", e)
        return (f"Error hooking bot '{sanitized}' into global loops => {e}", None)

    # 8) Return final success message plus ephemeral-bot client
    success_msg = f"Successfully created & logged in => {bot_id}"
    logger.info(success_msg)
    return (success_msg, client)


async def create_and_login_bot_dep(
    bot_id: str,
    password: str,
    displayname: str,
    system_prompt: str,
    traits: dict,
    creator_user_id: str = "@lunabot:localhost",
    is_admin: bool = False
) -> str:
    """
    1) Creates a local persona entry in personalities.json (using bot_id as key).
    2) Calls create_user(...) to register with Synapse.
    3) Does ephemeral login (load_or_login_client_v2).
    4) Registers event handlers, spawns the bot’s sync loop.
    5) Stores references (AsyncClient + sync task) in the globals BOTS and BOT_TASKS.

    :param bot_id: Full Matrix user ID, e.g. "@spiderbot:localhost".
    :param password:  The password for the new bot.
    :param displayname: The user-friendly name for the bot.
    :param system_prompt: GPT system instructions or persona description.
    :param traits:    A dictionary of arbitrary trait key-values (e.g. theme, power).
    :param creator_user_id: Who “spawned” this bot. Default is @lunabot:localhost.
    :param is_admin:  Whether to create an admin user in Synapse. Defaults False.
    :return:          Success or error string (unchanged).
    """

    logger.debug("[create_and_login_bot] Called with bot_id=%r, displayname=%r", bot_id, displayname)

    # ------------------------------------------------------------------
    # 1) Validate & parse localpart
    # ------------------------------------------------------------------
    if not bot_id.startswith("@") or ":" not in bot_id:
        err = f"[create_and_login_bot] Invalid bot_id => {bot_id}"
        logger.warning(err)
        return err

    # Example: bot_id="@myGuy!:localhost"
    # localpart => "myGuy!"
    original_localpart = bot_id.split(":")[0].replace("@", "", 1)
    logger.debug("Original localpart extracted => %r", original_localpart)

    # ------------------------------------------------------------------
    # 2) Sanitize the localpart
    # ------------------------------------------------------------------
    # Convert to lowercase for consistency
    tmp = original_localpart.lower()
    # Keep only valid characters
    sanitized = "".join(ch for ch in tmp if VALID_LOCALPART_REGEX.match(ch))

    # If sanitized ends up empty, fallback to random
    if not sanitized:
        # e.g. "bot_" + short random suffix
        random_suffix = secrets.token_hex(4)  # e.g. "a1b2"
        sanitized = f"bot_{random_suffix}"
        logger.debug("Localpart was invalid, using fallback => %r", sanitized)
    elif sanitized != original_localpart.lower():
        # Provide a debug log to note that we changed it
        logger.debug("Sanitized localpart from %r to %r", original_localpart, sanitized)

    # Rebuild the bot_id with the sanitized localpart
    # e.g. bot_id="@sanitized:localhost"
    new_bot_id = f"@{sanitized}:localhost"
    logger.debug("Final bot_id => %r", new_bot_id)

    # We'll just overwrite the caller's bot_id with new_bot_id, for consistency
    bot_id = new_bot_id

    # ------------------------------------------------------------------
    # 3) Create persona in personalities.json
    # ------------------------------------------------------------------
    try:
        logger.debug("Creating persona in personalities.json => %r", bot_id)
        luna.luna_personas.create_bot(
            bot_id=bot_id,
            password=password,
            displayname=displayname,
            creator_user_id=creator_user_id,
            system_prompt=system_prompt,
            traits=traits
        )
        logger.info("[create_and_login_bot] Persona created for %s.", bot_id)
    except Exception as e:
        msg = f"[create_and_login_bot] Could not create persona => {e}"
        logger.exception(msg)
        return msg

    # ------------------------------------------------------------------
    # 4) Create the user in Synapse
    # ------------------------------------------------------------------
    # localpart for matrix creation => everything after "@..." but before :...
    # e.g. "sanitized"
    matrix_localpart = sanitized
    logger.debug("Attempting create_user(localpart=%r)", matrix_localpart)
    creation_msg = await create_user(matrix_localpart, password, is_admin=is_admin)

    if not creation_msg.startswith("Created user"):
        # e.g. "Error creating user..." or "HTTP 409 user already exists..."
        err = f"[create_and_login_bot] Synapse user creation failed => {creation_msg}"
        logger.error(err)
        return err

    # ------------------------------------------------------------------
    # 5) Ephemeral login
    # ------------------------------------------------------------------
    try:
        logger.debug("Attempting ephemeral login => bot_id=%r", bot_id)
        client = await load_or_login_client_v2(
            homeserver_url="http://localhost:8008",  # or from config
            user_id=bot_id,
            password=password,
            device_name=f"{sanitized}_device"
        )
        logger.info("[create_and_login_bot] Ephemeral login success => %s", bot_id)
    except Exception as e:
        logger.exception("[create_and_login_bot] Ephemeral login failed => %s", e)
        return f"Error ephemeral-logging in {bot_id}: {e}"

    # ------------------------------------------------------------------
    # 6) Register event callbacks
    # ------------------------------------------------------------------
    client.add_event_callback(
        lambda room, evt: handle_bot_room_message(client, sanitized, room, evt),
        RoomMessageText
    )
    client.add_event_callback(
        lambda room, evt: handle_bot_invite(client, sanitized, room, evt),
        InviteMemberEvent
    )
    client.add_event_callback(
        lambda room, evt: handle_bot_member_event(client, sanitized, room, evt),
        RoomMemberEvent
    )
    logger.info("[create_and_login_bot] Registered event handlers for '%s'.", sanitized)

    # ------------------------------------------------------------------
    # 7) Start the sync loop & store references
    # ------------------------------------------------------------------
    try:
        from luna.core import BOTS, BOT_TASKS, run_bot_sync
        BOTS[sanitized] = client
        sync_task = asyncio.create_task(run_bot_sync(client, sanitized))
        BOT_TASKS.append(sync_task)
        logger.info("[create_and_login_bot] Bot '%s' sync loop started.", sanitized)

    except Exception as e:
        logger.exception("[create_and_login_bot] Could not store references or start sync => %s", e)
        return f"Error hooking bot '{sanitized}' into global loops => {e}"

    # ------------------------------------------------------------------
    # 8) Return final success message
    # ------------------------------------------------------------------
    success_msg = f"Successfully created & logged in => {bot_id}"
    logger.info(success_msg)
    return success_msg


# Optional: quick test harness
if __name__ == "__main__":
    async def test_run():
        user_id_full = "@testbot(!!!):localhost"  # intentionally invalid chars
        pwd  = "testbotPass!"
        display = "Test Bot #123"
        s_prompt = "You are a friendly test-bot for demonstration."
        traits_example = {"color": "blue", "hobby": "testing code"}
        
        result = await create_and_login_bot(
            bot_id=user_id_full,
            password=pwd,
            displayname=display,
            system_prompt=s_prompt,
            traits=traits_example
        )
        print(result)

    asyncio.run(test_run())

=== luna_command_extensions/create_room.py ===
import logging
import shlex  # <-- We’ll use this to parse user arguments correctly

logger = logging.getLogger(__name__)

from luna.luna_functions import getClient
from nio import RoomCreateResponse
from nio.api import RoomVisibility

async def create_room(args_string: str) -> str:
    """
    Creates a new Matrix room, returning a message describing the outcome.
    By default, it creates a public room; if '--private' is given, it's private.

    We now parse 'args_string' with shlex.split() so that quotes are respected.
      Example usage from the console:
        create_room "My new room" --private
    
    :param args_string: The raw argument string from the console, which might
                       contain quoted text or flags.
    :return: A result message describing success or failure.
    """

    # 1) Parse the raw string with shlex to allow quoted words
    try:
        tokens = shlex.split(args_string)
    except ValueError as e:
        logger.exception("Error parsing arguments with shlex:")
        return f"Error parsing arguments: {e}"

    if not tokens:
        return "Usage: create_room <roomName> [--private]"

    # 2) Extract room name from the first token, check for optional "--private"
    room_name = tokens[0]
    is_public = True

    if "--private" in tokens[1:]:
        is_public = False

    logger.debug("Creating room with name=%r, is_public=%r", room_name, is_public)

    client = getClient()
    if not client:
        return "Error: No DIRECTOR_CLIENT set."

    # 3) Convert is_public => the appropriate room visibility
    room_visibility = RoomVisibility.public if is_public else RoomVisibility.private

    # 4) Attempt to create the room via the client
    try:
        response = await client.room_create(
            name=room_name,
            visibility=room_visibility
        )

        if isinstance(response, RoomCreateResponse):
            return f"Created room '{room_name}' => {response.room_id}"
        else:
            # Possibly an ErrorResponse or something else
            return f"Error creating room => {response}"

    except Exception as e:
        logger.exception("Caught an exception while creating room %r:", room_name)
        return f"Exception while creating room => {e}"

=== luna_command_extensions/image_helpers.py ===
# image_helpers.py

import os
import logging
import urllib.parse

import aiohttp
from nio import AsyncClient

logger = logging.getLogger(__name__)

async def direct_upload_image(
    client: AsyncClient,
    file_path: str,
    content_type: str = "image/jpeg"
) -> str:
    """
    Manually upload a file to Synapse's media repository, explicitly setting
    Content-Length (avoiding chunked requests).
    
    Returns the mxc:// URI if successful, or raises an exception on failure.
    """
    if not client.access_token or not client.homeserver:
        raise RuntimeError("AsyncClient has no access_token or homeserver set.")

    base_url = client.homeserver.rstrip("/")
    filename = os.path.basename(file_path)
    encoded_name = urllib.parse.quote(filename)
    upload_url = f"{base_url}/_matrix/media/v3/upload?filename={encoded_name}"

    file_size = os.path.getsize(file_path)
    headers = {
        "Authorization": f"Bearer {client.access_token}",
        "Content-Type": content_type,
        "Content-Length": str(file_size),
    }

    logger.debug("[direct_upload_image] POST to %s, size=%d", upload_url, file_size)

    async with aiohttp.ClientSession() as session:
        with open(file_path, "rb") as f:
            async with session.post(upload_url, headers=headers, data=f) as resp:
                if resp.status == 200:
                    body = await resp.json()
                    content_uri = body.get("content_uri")
                    if not content_uri:
                        raise RuntimeError("No 'content_uri' in response JSON.")
                    logger.debug("[direct_upload_image] Uploaded. content_uri=%s", content_uri)
                    return content_uri
                else:
                    err_text = await resp.text()
                    raise RuntimeError(
                        f"Upload failed (HTTP {resp.status}): {err_text}"
                    )

=== luna_command_extensions/luna_message_handler4.py ===
"""
luna_message_handler4.py

Admin-only behavior, but now GPT fallback is interpreted as Markdown and sent
via 'org.matrix.custom.html', so it can render bold/italics/etc. in the client.
We assume there's no color code being injected – any mention highlighting is
still a client-side theme/notifications setting.
"""

import os
import time
import logging
import urllib.parse
import aiohttp
import random
import asyncio
import time
import logging
import re
import markdown  # for converting GPT's string to HTML

from nio import (
    AsyncClient,
    RoomMessageText,
    RoomSendResponse,
    RoomCreateResponse
)

from luna.luna_command_extensions.command_router import handle_console_command
from luna.context_helper import build_context
from luna.ai_functions import get_gpt_response
from luna import bot_messages_store

logger = logging.getLogger(__name__)
BOT_START_TIME = time.time() * 1000

async def handle_luna_message4(bot_client: AsyncClient, bot_localpart: str, room, event):
    """
    1) Ignores old/self messages
    2) Must be text
    3) Saves inbound
    4) If DM (2 participants) => handle commands or GPT
       Else => role-play channel => commands => respond by DM
    """
    message_body = event.body or ""
    logger.info("handle_luna_message4: room=%s from=%s => %r",
                room.room_id, event.sender, message_body)

    # 3) store inbound
    bot_messages_store.append_message(
        bot_localpart=bot_localpart,
        room_id=room.room_id,
        event_id=event.event_id,
        sender=event.sender,
        timestamp=event.server_timestamp,
        body=message_body
    )

    # 1) ignore old / from self
    if event.server_timestamp < BOT_START_TIME:
        logger.debug("Ignoring old event => %s", event.event_id)
        return

    bot_full_id = bot_client.user
    if event.sender == bot_full_id:
        logger.debug("Ignoring message from myself: %s", event.sender)
        return

    # 2) Must be text
    if not isinstance(event, RoomMessageText):
        logger.debug("Ignoring non-text event => %s", event.type)
        return

    # 4) DM vs. role-play channel
    participant_count = len(room.users)
    if participant_count == 2:
        await _handle_dm_channel(bot_client, bot_localpart, room, event, message_body)
    else:
        await _handle_roleplay_channel(bot_client, bot_localpart, room, event, message_body)


async def _handle_dm_channel(bot_client, bot_localpart, room, event, message_body):
    """
    2-participant DM:
      - If command => handle, respond in same room
      - Else => GPT fallback => interpret as Markdown
    """
    await _start_typing(bot_client, room.room_id)

    if message_body.startswith("!"):
        # commands
        reply_text = await handle_console_command(bot_client, room.room_id, message_body, event.sender)

        if "<table" in reply_text:
            # Possibly HTML from e.g. !help
            await send_formatted_text(bot_client, room.room_id, reply_text)
        else:
            await send_text(bot_client, room.room_id, reply_text)

    else:
        # GPT fallback => interpret as Markdown
        await asyncio.sleep(random.uniform(0.5, 2.0))
        gpt_reply = await _call_gpt(bot_localpart, room.room_id, message_body)

        # Convert GPT’s string from Markdown => HTML
        # (If GPT doesn't use markdown, it still renders fine.)
        reply_html = markdown.markdown(gpt_reply, extensions=["extra", "sane_lists"])
        # Then post it with formatted_text
        await send_formatted_text(bot_client, room.room_id, reply_html)
    
    await bot_client.sync(timeout=500)
    
    await _stop_typing(bot_client, room.room_id)


async def _handle_roleplay_channel(bot_client, bot_localpart, room, event, message_body):
    """
    If 3+ participants => role-play context:
      - Only respond to commands => respond right in the same room thread
      - Tag each response with "context_cue": "SYSTEM RESPONSE"
    """
    # 1) If the message does NOT start with '!', ignore
    if not message_body.startswith("!"):
        logger.debug("Ignoring non-command in role-play channel.")
        return

    # 2) Indicate typing
    await _start_typing(bot_client, room.room_id)

    try:
        # 3) Handle the console command
        command_reply = await handle_console_command(
            bot_client, 
            room.room_id, 
            message_body, 
            event.sender
        )

        # 4) If the command output includes tables (<table>), we send HTML
        if "<table" in command_reply:
            await send_formatted_text(
                bot_client, 
                room.room_id, 
                command_reply,
                context_cue="SYSTEM RESPONSE"
            )
        else:
            await send_text(
                bot_client, 
                room.room_id, 
                command_reply,
                context_cue="SYSTEM RESPONSE"
            )

    finally:
        # 5) Stop typing no matter what
        await bot_client.sync(timeout=500) 
        await _stop_typing(bot_client, room.room_id)



# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
# @TODO delete this if it's truly not being used
async def _ensure_dm_room(bot_client: AsyncClient, user_id: str) -> str:
    for rid, room_obj in bot_client.rooms.items():
        if len(room_obj.users) == 2 and user_id in room_obj.users:
            logger.debug("Found existing DM => %s", rid)
            return rid

    # create if not found
    logger.debug("No existing DM => create for %s", user_id)
    try:
        resp = await bot_client.room_create(
            invite=[user_id],
            is_direct=True,
            name=f"DM_with_{user_id}"
        )
        if isinstance(resp, RoomCreateResponse):
            logger.info("Created DM => %s", resp.room_id)
            return resp.room_id
        else:
            logger.warning("room_create => %s", resp)
            return "!failedDM:localhost"
    except Exception as e:
        logger.exception("Error creating DM => %s", e)
        return "!failedDM:localhost"

async def _start_typing(bot_client: AsyncClient, room_id: str):
    try:
        await bot_client.room_typing(room_id, True, timeout=5000)
        logger.debug("Typing start => %s", room_id)
    except Exception as e:
        logger.warning("Could not send typing start => %s", e)

async def _stop_typing(bot_client: AsyncClient, room_id: str):
    try:
        await bot_client.room_typing(room_id, False, timeout=0)
        logger.debug("Typing stop => %s", room_id)
    except Exception as e:
        logger.warning("Could not send typing stop => %s", e)

async def _call_gpt(bot_localpart: str, room_id: str, user_message: str) -> str:
    context_config = {"max_history": 10}
    gpt_context = build_context(bot_localpart, room_id, context_config)
    gpt_context.append({"role": "user", "content": user_message})
    logger.debug("GPT context => %s", gpt_context)

    reply = await get_gpt_response(
        messages=gpt_context,
        model="chatgpt-4o-latest",
        temperature=0.7,
        max_tokens=2000
    )
    return reply

# ---------------------------------------------------------------------
# Senders
# ---------------------------------------------------------------------
async def send_text(bot_client: AsyncClient, room_id: str, text: str, context_cue: str = None):
    """
    Sends plain text. If `context_cue` is provided, we add it to the message content.
    """
    content = {
        "msgtype": "m.text",
        "body": text
    }
    if context_cue:
        content["context_cue"] = context_cue  # custom field

    resp = await bot_client.room_send(room_id, "m.room.message", content=content)
    if isinstance(resp, RoomSendResponse):
        logger.info("Sent text => event_id=%s in %s", resp.event_id, room_id)
    else:
        logger.warning("Failed to send text => %s", resp)



async def send_formatted_text(bot_client: AsyncClient, room_id: str, html_content: str, context_cue: str = None):
    """
    Sends HTML in 'formatted_body', with a stripped fallback in 'body'.
    This can handle any markdown->html or other markup.
    """
    fallback_text = remove_html_tags(html_content)
    content = {
        "msgtype": "m.text",
        "body": fallback_text,
        "format": "org.matrix.custom.html",
        "formatted_body": html_content
    }

    if context_cue:
        content["context_cue"] = context_cue  # custom field

    resp = await bot_client.room_send(room_id=room_id, message_type="m.room.message", content=content)
    if isinstance(resp, RoomSendResponse):
        logger.info("Sent formatted text => event_id=%s in %s", resp.event_id, room_id)
    else:
        logger.warning("Failed to send formatted text => %s", resp)

def remove_html_tags(text: str) -> str:
    import re
    return re.sub(r'<[^>]*>', '', text or "").strip()


=== luna_command_extensions/parse_and_execute.py ===
import json
import logging
import asyncio
import re
import time

logger = logging.getLogger(__name__)

def parse_and_execute(script_str, loop):
    """
    A blocking version of parse_and_execute that:
      1) Creates rooms by name (private or public).
      2) Parses the console output to grab the actual room ID.
      3) Stores the (name -> room_id) mapping in a dictionary so that future
         "invite_user" actions can use the real room ID.
      4) Waits (or optionally does a forced sync) after creation so that
         the director has fully joined the room with correct power level
         before sending invites.

    Example JSON:
    {
      "title": "BlockInviteScript",
      "actions": [
        {
          "type": "create_room",
          "args": {
            "room_name": "myTreetop",
            "private": true
          }
        },
        {
          "type": "invite_user",
          "args": {
            "user_id": "@lunabot:localhost",
            "room_id_or_alias": "myTreetop"
          }
        },
        ...
      ]
    }
    """
    try:
        data = json.loads(script_str)
    except json.JSONDecodeError as e:
        logger.debug(f"[parse_and_execute] Failed to parse JSON => {e}")
        print(f"SYSTEM: Error parsing JSON => {e}")
        return

    script_title = data.get("title", "Untitled")
    logger.debug(f"[parse_and_execute] Beginning script => {script_title}")
    print(f"SYSTEM: Running script titled '{script_title}' (blocking)...")

    actions = data.get("actions", [])
    if not actions:
        logger.debug("[parse_and_execute] No actions found in script.")
        print("SYSTEM: No actions to perform. Script is empty.")
        return

    # We'll import these on demand to avoid circular references
    from luna.console_functions import cmd_create_room
    from luna.console_functions import cmd_invite_user

    # 1) We'll keep a small map of "room_name" -> "room_id"
    #    so if user typed "myTreetop", we can transform that into e.g. "!abc123:localhost".
    name_to_id_map = {}

    # Regex to capture something like:
    # "SYSTEM: Created room 'myTreetop' => !abc123:localhost"
    room_id_pattern = re.compile(
        r"Created room '(.+)' => (![A-Za-z0-9]+:[A-Za-z0-9\.\-]+)"
    )

    for i, action_item in enumerate(actions, start=1):
        action_type = action_item.get("type")
        args_dict = action_item.get("args", {})

        logger.debug(f"[parse_and_execute] Action #{i}: {action_type}, args={args_dict}")
        print(f"SYSTEM: [#{i}] Executing '{action_type}' with args={args_dict}...")

        if action_type == "create_room":
            # e.g. "myTreetop" --private
            room_name = args_dict.get("room_name", "UntitledRoom")
            is_private = args_dict.get("private", False)

            if is_private:
                arg_string = f"\"{room_name}\" --private"
            else:
                arg_string = f"\"{room_name}\""

            # We capture the console output by temporarily redirecting stdout,
            # or we can rely on the user to see "Created room 'X' => !id".
            # For simplicity, let's just parse the log lines after cmd_create_room finishes.
            original_stdout_write = None
            output_lines = []

            def custom_write(s):
                output_lines.append(s)
                if original_stdout_write:
                    original_stdout_write(s)

            import sys
            if sys.stdout.write != custom_write:  # Only override once
                original_stdout_write = sys.stdout.write
                sys.stdout.write = custom_write

            # 1a) Create the room (blocking call)
            cmd_create_room(arg_string, loop)

            # force a sync here
            from luna.luna_functions import DIRECTOR_CLIENT
            future = asyncio.run_coroutine_threadsafe(DIRECTOR_CLIENT.sync(timeout=1000), loop)
            future.result()
          
            # 1b) Restore stdout
            sys.stdout.write = original_stdout_write

            # 1c) Parse the lines for the created room ID
            for line in output_lines:
                match = room_id_pattern.search(line)
                if match:
                    captured_name = match.group(1)  # e.g. myTreetop
                    captured_id = match.group(2)    # e.g. !abc123:localhost
                    if captured_name == room_name:
                        name_to_id_map[room_name] = captured_id
                        print(f"SYSTEM: Mapped '{room_name}' => '{captured_id}'")

            # 1d) Sleep or forced sync to ensure the user is recognized
            time.sleep(1.0)
            # Optionally: you could call a forced sync here.

        elif action_type == "invite_user":
            user_id = args_dict.get("user_id")
            user_room = args_dict.get("room_id_or_alias")

            # If user_room is in our name_to_id_map, replace it with the real ID
            if user_room in name_to_id_map:
                real_id = name_to_id_map[user_room]
                print(f"SYSTEM: Translating '{user_room}' -> '{real_id}' for invitation.")
                user_room = real_id

            arg_string = f"{user_id} {user_room}"
            cmd_invite_user(arg_string, loop)
            time.sleep(2.0)

        else:
            logger.debug(f"[parse_and_execute] Unknown action type: {action_type}")
            print(f"SYSTEM: Unrecognized action '{action_type}'. Skipping.")

    logger.debug("[parse_and_execute] Script completed.")
    print("SYSTEM: Script execution complete (blocking).")

=== luna_command_extensions/spawn_persona.py ===
import asyncio
import logging
import json
import shlex
import time
import os
import html

from luna.ai_functions import get_gpt_response, generate_image
from luna.luna_command_extensions.create_and_login_bot import create_and_login_bot
from luna.luna_personas import update_bot
from luna.luna_functions import getClient

logger = logging.getLogger(__name__)

async def spawn_persona(descriptor: str) -> str:
    """
    Creates a new persona, returning one HTML string that includes:
    - A table (the "character card") with:
       * localpart, displayname, biography, backstory, system prompt
       * the EXACT DALL·E prompt used for image creation
       * traits as a nested table
    - Possibly an <img> referencing the final mxc:// URI.
    """

    # 1) GPT => persona JSON
    system_instructions = (
        "You are an assistant that outputs ONLY valid JSON. "
        "No markdown, no code fences, no extra commentary. "
        "Generate a persona object which must have keys: localpart, displayname, biography, backstory, "
        "system_prompt, password, traits. No other keys. "
        "The 'traits' key is a JSON object with arbitrary key/values. "
        "Be sure that the system prompt instructs the bot to behave in character."
    )
    user_message = (
        f"Create a persona based on:\n{descriptor}\n\n"
        "Return ONLY valid JSON with required keys."
    )

    messages = [
        {"role": "system", "content": system_instructions},
        {"role": "user", "content": user_message},
    ]

    logger.info(f"SYSTEM: Attemping to get a character card generated via GPT. System Instruction: {system_instructions}. Prompt: {user_message}")
    try:
        gpt_response = await get_gpt_response(
            messages=messages,
            model="gpt-4",
            temperature=0.7,
            max_tokens=5000
        )
    except Exception as e:
        logger.exception("GPT error =>")
        return f"SYSTEM: GPT error => {e}"

    # 2) Parse persona JSON
    try:
        persona_data = json.loads(gpt_response)
    except json.JSONDecodeError as e:
        logger.exception("JSON parse error =>")
        return f"SYSTEM: GPT returned invalid JSON => {e}"

    required = ["localpart", "password", "displayname", "system_prompt", "traits"]
    missing = [f for f in required if f not in persona_data]
    if missing:
        return f"SYSTEM: Persona missing fields => {missing}"

    localpart     = persona_data["localpart"]
    password      = persona_data["password"]
    displayname   = persona_data["displayname"]
    system_prompt = persona_data["system_prompt"]
    traits        = persona_data["traits"] or {}
    biography     = persona_data.get("biography", "")
    backstory     = persona_data.get("backstory", "")

    # 3) Register & login the persona
    spawn_msg, ephemeral_bot_client = await create_and_login_bot(
        bot_id=f"@{localpart}:localhost",
        password=password,
        displayname=displayname,
        system_prompt=system_prompt,
        traits=traits
    )
    if not spawn_msg.startswith("Successfully created & logged in"):
        return f"SYSTEM: Bot creation failed => {spawn_msg}"

    # 4) Attempt to generate & upload a portrait
    #    We'll store the EXACT DALL·E prompt in 'final_prompt'
    final_prompt = descriptor.strip()  
    portrait_mxc = None
    try:
        portrait_url = generate_image(final_prompt, size="1024x1024")
        if portrait_url:
            portrait_mxc = await _download_and_upload_portrait(portrait_url, localpart, password, system_prompt, traits, ephemeral_bot_client)
    except Exception as e:
        logger.warning("Portrait error => %s", e)

    # get the global style prompt appendix
    from luna.luna_command_extensions.command_router import GLOBAL_PARAMS
    global_draw_appendix = GLOBAL_PARAMS["global_draw_prompt_appendix"]

    # 5) Build final HTML table (with nested table for `traits`)
    #    plus an <img> if we have a portrait.
    card_html = _build_persona_card(
        localpart=localpart,
        displayname=displayname,
        biography=biography,
        backstory=backstory,
        system_prompt=system_prompt,
        dall_e_prompt=final_prompt,   # EXACT final prompt
        traits=traits,
        portrait_mxc=portrait_mxc,
        global_draw_appendix = global_draw_appendix 
    )
    return card_html


async def cmd_spawn(bot_client, descriptor):
    """
    Usage: spawn "A cosmic explorer..."
    Returns a single HTML string containing the entire character card
    (table + optional <img>).
    """
    try:
        card_html = await spawn_persona(descriptor)
        return card_html
    except Exception as e:
        logger.exception("cmd_spawn => error in spawn_persona")
        return f"SYSTEM: Error spawning persona => {e}"


# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------

async def _download_and_upload_portrait(
    portrait_url: str,
    localpart: str,
    password: str,
    system_prompt: str,
    traits: dict,
    ephemeral_bot_client
) -> str:
    """
    Download the image from portrait_url, upload to matrix,
    update persona record + set bot avatar. Returns mxc:// URI or None.
    """
    import requests
    os.makedirs("data/images", exist_ok=True)
    filename = f"data/images/portrait_{int(time.time())}.jpg"
    dl_resp = requests.get(portrait_url)
    dl_resp.raise_for_status()
    with open(filename, "wb") as f:
        f.write(dl_resp.content)

    client = getClient()
    if not client:
        return None

    # Upload
    from luna.luna_command_extensions.luna_message_handler4 import direct_upload_image
    portrait_mxc = await direct_upload_image(client, filename, "image/jpeg")
    # Update persona
    traits["portrait_url"] = portrait_mxc
    update_bot(
        f"@{localpart}:localhost",
        {
            "password": password,
            "system_prompt": system_prompt,
            "traits": traits
        }
    )
    # Attempt to set avatar
    if ephemeral_bot_client:
        try:
            await ephemeral_bot_client.set_avatar(portrait_mxc)
        except Exception as e:
            logger.warning("Error setting avatar => %s", e)

    return portrait_mxc

def _build_persona_card(
    localpart: str,
    displayname: str,
    biography: str,
    backstory: str,
    system_prompt: str,
    dall_e_prompt: str,
    global_draw_appendix: str,
    traits: dict,
    portrait_mxc: str = None
) -> str:
    """
    1) Show the localpart as a big title above the portrait.
    2) Show an italic line beneath the title (e.g. the displayname).
    3) Then the portrait if available.
    4) Then a table with the rest of the details, including version=1.0.
    """

    import html
    def esc(t): 
        return html.escape(str(t))

    # -------------------------
    # Sub-table for traits
    # -------------------------
    trait_rows = []
    for k, v in traits.items():
        trait_rows.append(
            "<tr>"
            f"<td style='padding:2px 6px;'><b>{esc(k)}</b></td>"
            f"<td style='padding:2px 6px;'>{esc(v)}</td>"
            "</tr>"
        )
    traits_subtable = (
        "<table border='1' style='border-collapse:collapse; font-size:0.9em;'>"
        "<thead><tr><th colspan='2'>Traits</th></tr></thead>"
        f"<tbody>{''.join(trait_rows)}</tbody>"
        "</table>"
    )

    # A quick helper to build each row
    def row(label, val):
        return (
            "<tr>"
            f"<td style='padding:4px 8px;vertical-align:top;'><b>{esc(label)}</b></td>"
            f"<td style='padding:4px 8px;'>{val}</td>"
            "</tr>"
        )

    # -------------------------
    # The portrait HTML (if any)
    # -------------------------
    portrait_html = ""
    if portrait_mxc:
        portrait_html = (
            f"<div style='margin-bottom:8px;'>"
            f"<img src='{esc(portrait_mxc)}' alt='Portrait' width='300'/>"
            "</div>"
        )

    # -------------------------
    # The table of fields
    # -------------------------
    # Hardcoded version => "1.0"
    row_version       = row("Version", "1.0")
    row_localpart     = row("Localpart", esc(localpart))
    row_displayname   = row("DisplayName", esc(displayname))
    row_biography     = row("Biography", esc(biography))
    row_backstory     = row("Backstory", esc(backstory))
    row_systemprompt  = row("System Prompt", esc(system_prompt))
    row_dalle_prompt  = row("DALL·E Prompt", esc(dall_e_prompt))
    row_draw_appendix = row("Draw Prompt Appendix", esc(global_draw_appendix))
    row_traits        = row("Traits", traits_subtable)

    table_body = "".join([
        row_localpart,
        row_displayname,
        row_biography,
        row_backstory,
        row_systemprompt,
        row_dalle_prompt,
        row_draw_appendix,
        row_traits,
        row_version
    ])

    table_html = (
        "<table border='1' style='border-collapse:collapse;'>"
        f"<tbody>{table_body}</tbody>"
        "</table>"
    )

    # -------------------------
    # Combine everything
    # -------------------------
    # 1) <h2>@localpart</h2> as a big title
    # 2) Italic line with displayName (or biography if you prefer)
    # 3) The portrait
    # 4) The table
    final_html = (
        f"<h2 style='margin-bottom:2px;'>{esc(localpart)}</h2>"
        f"<p style='margin-top:0; margin-bottom:10px;'><em>{esc(displayname)}</em></p>"
        f"{portrait_html}"
        f"{table_html}"
        "<p><em>All done creating the persona!</em></p>"
    )
    return final_html

=== luna_command_extensions/spawner.py ===
# spawner.py

import json
import asyncio
import logging
import shlex

# Suppose your GPT call is in ai_functions.py
from luna.ai_functions import get_gpt_response

logger = logging.getLogger(__name__)

# Simple ANSI color codes for old-school vibe:
ANSI_YELLOW = "\033[93m"
ANSI_GREEN = "\033[92m"
ANSI_CYAN = "\033[96m"
ANSI_MAGENTA = "\033[95m"
ANSI_RED = "\033[91m"
ANSI_WHITE = "\033[97m"
ANSI_RESET = "\033[0m"


def cmd_spawn_squad(args, loop):
    """
    The real logic for spawn_squad.
    Called by console_functions.py or whichever file includes the “command router.”

    Usage: spawn_squad <numBots> "<theme or style>"

    Example:
      spawn_squad 3 "A jazzy trio of improvisational bots"

    This version displays a more colorful, “BBS-like” console output
    when describing the spawned personas and their JSON details.
    """

    logger.debug("cmd_spawn_squad => Received args=%r", args)

    # 1) Parse the arguments
    tokens = shlex.split(args.strip())
    logger.debug("Parsed tokens => %s", tokens)

    if len(tokens) < 2:
        msg = "SYSTEM: Usage: spawn_squad <numBots> \"<theme>\""
        print(msg)
        logger.warning(msg)
        return

    # Try to parse the count as an integer
    try:
        count = int(tokens[0])
    except ValueError:
        msg = "SYSTEM: First arg must be an integer for the number of bots."
        print(msg)
        logger.warning(msg)
        return

    # We only allow 1–5 bots
    if count < 1 or count > 5:
        msg = "SYSTEM: Allowed range is 1 to 5 bots."
        print(msg)
        logger.warning(msg)
        return

    # Reconstruct the theme from all tokens after the first
    theme = " ".join(tokens[1:])
    logger.debug("Spawn_squad => count=%d, theme=%r", count, theme)

    # 2) Build the GPT system instructions & user message.
    #    We now require 'biography' and 'backstory' keys as well.
    system_instructions = (
        "You are an assistant that outputs ONLY valid JSON. "
        "No markdown, no code fences, no extra commentary. "
        f"Generate an array of exactly {count} persona objects. "
        "Each object must have keys: localpart, displayname, biography, backstory, system_prompt, password, traits."
        "No other keys. "
        "The 'traits' key is a JSON object with arbitrary key/values. "
        "Be sure that the system prompt instructs the bot to behave at all times in character."
        "Incorporate as much of the character's identity into the system prompt as possible"
        "In this environment, you can explicitly mention another bot by typing their Matrix user ID in the format @<localpart>:localhost. For example, if a bot’s localpart is diamond_dave, you would mention them as @diamond_dave:localhost. Important: mentioning a bot this way always triggers a response from them. Therefore, avoid frivolous or unnecessary mentions. Only mention another bot when you genuinely need their attention or expertise."
    )

    user_message = (
        f"Please create {count} persona(s) for the theme: '{theme}'. "
        "Return ONLY valid JSON (an array, no outer text). Be sure that the system prompt instructs the bot to behave at all times in character."
    )

    logger.debug("system_instructions=%r", system_instructions)
    logger.debug("user_message=%r", user_message)

    async def do_spawn():
        logger.debug("do_spawn => Starting GPT call (count=%d)", count)

        # 3) Call GPT to get JSON for the requested # of personas
        gpt_response = await get_gpt_response(
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user",   "content": user_message}
            ],
            model="gpt-4",
            temperature=0.7,
            max_tokens=1000
        )

        logger.debug("GPT raw response => %r", gpt_response)

        # 4) Parse JSON
        try:
            persona_array = json.loads(gpt_response)
        except json.JSONDecodeError as e:
            err_msg = f"SYSTEM: GPT returned invalid JSON => {e}"
            print(err_msg)
            logger.error("%s -- full GPT response => %s", err_msg, gpt_response)
            return

        if not isinstance(persona_array, list):
            msg = "SYSTEM: GPT did not return a JSON list. Aborting."
            print(msg)
            logger.warning(msg)
            return

        if len(persona_array) != count:
            msg = (
                f"SYSTEM: GPT returned a list of length "
                f"{len(persona_array)}, expected {count}. Aborting."
            )
            print(msg)
            logger.warning(msg)
            return

        # 5) Summon each persona
        successes = 0

        for i, persona in enumerate(persona_array):
            logger.debug("Persona[%d] => %s", i, persona)

            # Check for required keys
            required_keys = [
                "localpart",
                "displayname",
                "biography",
                "backstory",
                "system_prompt",
                "password",
                "traits",
            ]

            missing_key = None
            for rk in required_keys:
                if rk not in persona:
                    missing_key = rk
                    break
            if missing_key:
                msg = f"SYSTEM: Missing key '{missing_key}' in GPT object {i}. Skipping."
                print(msg)
                logger.warning(msg)
                continue

            # Display a fancy "character sheet" in BBS style
            persona_label = f"{ANSI_GREEN}Persona #{i+1} of {count}{ANSI_RESET}"

            print(f"\n{ANSI_MAGENTA}{'=' * 60}{ANSI_RESET}")
            print(f"{ANSI_YELLOW} Summoning {persona_label} for your {theme} squad...{ANSI_RESET}")
            print(f"{ANSI_MAGENTA}{'=' * 60}{ANSI_RESET}")

            # We'll display the entire JSON so we don't rely on a specific schema.
            # For color + indentation, let's do a pretty print but highlight keys.
            # We'll build lines by hand:
            for k, v in persona.items():
                # Show keys in CYAN, values in WHITE
                # If v is a dict, we can pretty-dump it
                if isinstance(v, dict):
                    dict_str = json.dumps(v, indent=2)
                    print(f"{ANSI_CYAN}  {k}{ANSI_RESET} = {ANSI_WHITE}{dict_str}{ANSI_RESET}")
                else:
                    # Just convert to string
                    print(f"{ANSI_CYAN}  {k}{ANSI_RESET} = {ANSI_WHITE}{v}{ANSI_RESET}")

            # Actually spawn the user
            full_bot_id = f"@{persona['localpart']}:localhost"
            password = persona["password"]
            displayname = persona["displayname"]
            system_prompt = persona["system_prompt"]
            traits = persona["traits"]

            async def single_spawn():
                from luna.luna_command_extensions.create_and_login_bot import create_and_login_bot
                logger.debug("single_spawn => Creating user_id=%r", full_bot_id)
                result_msg = await create_and_login_bot(
                    bot_id=full_bot_id,
                    password=password,
                    displayname=displayname,
                    system_prompt=system_prompt,
                    traits=traits,
                    creator_user_id="@lunabot:localhost",
                    is_admin=False
                )
                return result_msg

            spawn_result = await single_spawn()

            # Check if creation was successful
            if "Successfully created" in spawn_result:
                successes += 1
                print(
                    f"{ANSI_GREEN}SUCCESS:{ANSI_RESET} {spawn_result}"
                )
            else:
                print(
                    f"{ANSI_RED}FAILED:{ANSI_RESET} {spawn_result}"
                )

        # 6) Summary
        print()
        summary_msg = (
            f"SYSTEM: Attempted to spawn {count} persona(s). "
            f"{successes} succeeded, {count - successes} failed. Done."
        )
        print(f"{ANSI_CYAN}{summary_msg}{ANSI_RESET}")
        logger.info(summary_msg)

    # Announce to user we're about to do it
    print(
        f"{ANSI_YELLOW}SYSTEM:{ANSI_RESET} Summoning a squad of {count} "
        f"'{theme}'... stand by."
    )
    logger.info("cmd_spawn_squad => scheduling do_spawn (count=%d, theme=%r)", count, theme)

    # 7) We do a blocking run of do_spawn on the given loop
    future = asyncio.run_coroutine_threadsafe(do_spawn(), loop)

    # Block until do_spawn() completes
    try:
        future.result()
    except Exception as e:
        print(
            f"{ANSI_RED}SYSTEM: spawn_squad encountered an error => {e}{ANSI_RESET}"
        )
        logger.exception("spawn_squad encountered an exception =>", exc_info=e)

=== luna_command_extensions/summarize_room_for_participant.py ===
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

=== luna_functions.py ===
"""
luna_functions.py

Contains:
- Token-based login logic (load_or_login_client)
- Global reference to the Director client
- Message & invite callbacks
- Utility to load/save sync token
"""
import asyncio
import aiohttp
import logging
import time
import json
import pandas as pd
import os
import datetime
from nio import (
    AsyncClient,
    LoginResponse,
    RoomMessageText,
    InviteMemberEvent,
    RoomCreateResponse,
    RoomInviteResponse,
    LocalProtocolError
)
from nio.responses import ErrorResponse, SyncResponse, RoomMessagesResponse
from luna.luna_personas import _load_personalities
logger = logging.getLogger(__name__)
logging.getLogger("nio.responses").setLevel(logging.CRITICAL)

# ──────────────────────────────────────────────────────────
# GLOBALS
# ──────────────────────────────────────────────────────────
DIRECTOR_CLIENT: AsyncClient = None  # The client object used across callbacks
TOKEN_FILE = "data/tokens.json"   # Where we store/reuse the access token
SYNC_TOKEN_FILE = "data/sync_token.json"  # Where we store the last sync token
MESSAGES_CSV = "data/luna_messages.csv"   # We'll store all messages in this CSV

# Global context dictionary (if needed by your logic)
room_context = {}
MAX_CONTEXT_LENGTH = 100  # Limit to the last 100 messages per room


import logging
from nio import AsyncClient, LoginResponse

logger = logging.getLogger(__name__)

async def load_or_login_client_v2(
    homeserver_url: str,
    user_id: str,
    password: str,
    device_name: str = "BotDevice"
) -> AsyncClient:
    """
    load_or_login_client_ephemeral

    A simplified function that logs in a Matrix user via password each time,
    returning a ready-to-use AsyncClient. No tokens are stored or reused.

    Args:
      homeserver_url: Your Synapse server address, e.g. "http://localhost:8008"
      user_id: A full Matrix user ID (e.g. "@inky:localhost") or localpart if you prefer
      password: The account's password.
      device_name: A label for the login session.

    Returns:
      An AsyncClient logged in as `user_id`. If login fails, raises Exception.
    """

    # If the caller passed only the local part (like "inky"), you might want to ensure:
    #   if not user_id.startswith("@"):
    #       user_id = f"@{user_id}:localhost"
    # But that depends on your usage.

    logger.info(f"[load_or_login_client_v2] [{user_id}] Attempting password login...")

    # 1) Construct the client
    client = AsyncClient(homeserver=homeserver_url, user=user_id)

    # 2) Attempt the password login
    resp = await client.login(password=password, device_name=device_name)

    # 3) Check result
    if isinstance(resp, LoginResponse):
        logger.info(f"[{user_id}] Password login succeeded. user_id={client.user_id}")
        return client
    else:
        logger.error(f"[{user_id}] Password login failed => {resp}")
        raise Exception(f"Password login failed for {user_id}: {resp}")



# ──────────────────────────────────────────────────────────
# TOKEN-BASED LOGIN
# ──────────────────────────────────────────────────────────
async def load_or_login_client(homeserver_url: str, username: str, password: str) -> AsyncClient:
    """
    Attempt to load a saved access token. If found, verify it by calling whoami().
    If valid, reuse it. If invalid (or absent), do a normal password login and store
    the resulting token. Returns an AsyncClient ready to use.
    """

    # since DIRECTOR_CLIENT is a global variable in this module, we need to protect that
    # memory space within python by re-declaring it here. otherwise the script would simply create a local
    # which would have unintended consequences
    global DIRECTOR_CLIENT

    full_user_id = f"@{username}:localhost"  # Adjust the domain if needed
    client = None

    # 1. Check for an existing token file
    if os.path.exists(TOKEN_FILE):
        logger.debug(f"Found {TOKEN_FILE}; attempting token-based login.")
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
            saved_user_id = data.get("user_id")
            saved_access_token = data.get("access_token")
            saved_device_id = data.get("device_id")

        # 2. If the file contains valid fields, construct a client
        if saved_user_id and saved_access_token:
            logger.debug("Loading client with saved token credentials.")
            client = AsyncClient(homeserver=homeserver_url, user=saved_user_id)
            client.access_token = saved_access_token
            client.device_id = saved_device_id

            # 3. Verify the token with whoami()
            try:
                whoami_resp = await client.whoami()
                if whoami_resp and whoami_resp.user_id == saved_user_id:
                    # If it matches, we're good to go
                    logger.info(f"Token-based login verified for user {saved_user_id}.")
                    DIRECTOR_CLIENT = client
                    return client
                else:
                    # Otherwise, token is invalid or stale
                    logger.warning("Token-based login invalid. Deleting token file.")
                    os.remove(TOKEN_FILE)
            except Exception as e:
                # whoami() call itself failed; treat as invalid
                logger.warning(f"Token-based verification failed: {e}. Deleting token file.")
                os.remove(TOKEN_FILE)

    # 4. If we reach here, either there was no token file or token verification failed
    logger.debug("No valid token (or it was invalid). Attempting normal password login.")
    client = AsyncClient(homeserver=homeserver_url, user=full_user_id)
    resp = await client.login(password=password, device_name="LunaDirector")
    if isinstance(resp, LoginResponse):
        # 5. Password login succeeded; store a fresh token
        logger.info(f"Password login succeeded for user {client.user_id}. Storing token...")
        store_token_info(client.user_id, client.access_token, client.device_id)
        DIRECTOR_CLIENT = client
        return client
    else:
        # 6. Password login failed: raise an exception or handle it as desired
        logger.error(f"Password login failed: {resp}")
        raise Exception("Password login failed. Check credentials or homeserver settings.")
    
# ──────────────────────────────────────────────────────────
# CREATE USER LOGIC
# ──────────────────────────────────────────────────────────
async def create_user(username: str, password: str, is_admin: bool = False) -> str:
    """
    The single Luna function to create a user.
    1) Loads the admin token from tokens.json.
    2) Calls add_user_via_admin_api(...) from luna_functions.py.
    3) Returns a success/error message.
    """
    # 1) Load admin token
    HOMESERVER_URL = "http://localhost:8008"  # or read from config
    try:
        with open("data/tokens.json", "r") as f:
            data = json.load(f)
        admin_token = data["access_token"]
    except Exception as e:
        err_msg = f"Error loading admin token from tokens.json: {e}"
        logger.error(err_msg)
        return err_msg

    # 2) Delegate the actual call to your existing function
    #    (Yes, ironically still referencing `luna_functions`, but that’s how your code is structured)
    result = await add_user_via_admin_api(
        homeserver_url=HOMESERVER_URL,
        admin_token=admin_token,
        username=username,
        password=password,
        is_admin=is_admin
    )

    # 3) Return the result message
    return result

# ──────────────────────────────────────────────────────────
# LIST ROOMS
# ──────────────────────────────────────────────────────────
import json
import logging
import aiohttp

logger = logging.getLogger(__name__)

async def list_rooms() -> list[dict]:
    """
    Fetches all rooms on the Synapse server via the admin API, then for each room,
    calls a membership API to get participant info. Returns a list of dicts, e.g.:
       [
         {
           "room_id": "!abc123:localhost",
           "name": "My Great Room",
           "joined_members_count": 3,
           "participants": ["@userA:localhost", "@userB:localhost", "@lunabot:localhost"]
         },
         ...
       ]

    Implementation steps:
      1) Load admin token from data/tokens.json
      2) GET /_synapse/admin/v1/rooms to list all rooms
      3) For each room, GET /_synapse/admin/v2/rooms/<roomID>/members
         to find participants with membership = "join"
      4) Build the final list of room info, returning it
    """

    # 1) Load admin token from data/tokens.json
    homeserver_url = "http://localhost:8008"  # Adjust if needed
    try:
        with open("data/tokens.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        admin_token = data["access_token"]
    except Exception as e:
        logger.error(f"Unable to load admin token from tokens.json: {e}")
        return []

    # 2) Query the list of rooms
    list_url = f"{homeserver_url}/_synapse/admin/v1/rooms?limit=5000"
    headers = {"Authorization": f"Bearer {admin_token}"}

    all_rooms_info = []

    try:
        async with aiohttp.ClientSession() as session:
            # First call: get the top-level list of rooms
            async with session.get(list_url, headers=headers) as resp:
                if resp.status == 200:
                    resp_data = await resp.json()
                    raw_rooms = resp_data.get("rooms", [])
                    logger.debug(f"Found {len(raw_rooms)} total rooms on the server.")

                    # 3) For each room, fetch membership
                    for r in raw_rooms:
                        room_id = r.get("room_id")
                        # 'name' might be provided, or use the canonical_alias if present
                        room_name = r.get("name") or r.get("canonical_alias") or "(unnamed)"

                        # membership call: /_synapse/admin/v2/rooms/<room_id>/members
                        members_url = f"{homeserver_url}/_synapse/admin/v2/rooms/{room_id}/members"
                        async with session.get(members_url, headers=headers) as mresp:
                            if mresp.status == 200:
                                m_data = await mresp.json()
                                raw_members = m_data.get("members", [])
                                # We gather user_ids with membership='join'
                                participants = []
                                for mem_item in raw_members:
                                    if mem_item.get("membership") == "join":
                                        participants.append(mem_item.get("user_id"))

                                # Build the final info
                                all_rooms_info.append({
                                    "room_id": room_id,
                                    "name": room_name,
                                    "joined_members_count": len(participants),
                                    "participants": participants
                                })
                            else:
                                # If membership call fails, we can log and skip
                                text = await mresp.text()
                                logger.warning(
                                    f"Failed to fetch membership for {room_id} => "
                                    f"HTTP {mresp.status}: {text}"
                                )
                                # We still return partial data (no participants)
                                all_rooms_info.append({
                                    "room_id": room_id,
                                    "name": room_name,
                                    "joined_members_count": r.get("joined_members", 0),
                                    "participants": []
                                })
                else:
                    # If the main /rooms call fails, log and return empty
                    text = await resp.text()
                    logger.error(f"Failed to list rooms (HTTP {resp.status}): {text}")
                    return []
    except Exception as e:
        logger.exception(f"Error calling list_rooms admin API: {e}")
        return []

    return all_rooms_info


async def list_rooms_dep() -> list[dict]:
    """
    Returns a list of rooms that DIRECTOR_CLIENT knows about, 
    including participant names.

    Each dict in the returned list includes:
       {
         "room_id": "<string>",
         "name": "<string>",
         "joined_members_count": <int>,
         "participants": [<list of user IDs or display names>]
       }
    """
    if not DIRECTOR_CLIENT:
        logger.warning("list_rooms called, but DIRECTOR_CLIENT is None.")
        return []

    logger.info("[luna_functions] [list_rooms] Entering List Rooms.")
    rooms_info = []
    for room_id, room_obj in DIRECTOR_CLIENT.rooms.items():
        room_name = room_obj.display_name or "(unnamed)"
        participant_list = [user_id for user_id in room_obj.users.keys()]

        rooms_info.append({
            "room_id": room_id,
            "name": room_name,
            "joined_members_count": len(participant_list),
            "participants": participant_list
        })

    return rooms_info


# ──────────────────────────────────────────────────────────
# ADMIN API FOR CREATING USERS
# ──────────────────────────────────────────────────────────
async def add_user_via_admin_api(
    homeserver_url: str,
    admin_token: str,
    username: str,
    password: str,
    is_admin: bool = False
) -> str:
    """
    Creates a new user by hitting the Synapse Admin API.
    """
    user_id = f"@{username}:localhost"
    url = f"{homeserver_url}/_synapse/admin/v2/users/{user_id}"

    body = {
        "password": password,
        "admin": is_admin,
        "deactivated": False
    }
    headers = {
        "Authorization": f"Bearer {admin_token}"
    }

    logger.info(f"Creating user {user_id}, admin={is_admin} via {url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.request("PUT", url, headers=headers, json=body) as resp:
                if resp.status in (200, 201):
                    logger.info(f"Created user {user_id} (HTTP {resp.status})")
                    return f"Created user {user_id} (admin={is_admin})."
                else:
                    text = await resp.text()
                    logger.error(f"Error creating user {user_id}: {resp.status} => {text}")
                    return f"HTTP {resp.status}: {text}"

    except aiohttp.ClientError as e:
        logger.exception(f"Network error creating user {user_id}")
        return f"Network error: {e}"
    except Exception as e:
        logger.exception("Unexpected error.")
        return f"Unexpected error: {e}"

# ──────────────────────────────────────────────────────────
# RECENT MESSAGES
# ──────────────────────────────────────────────────────────
async def fetch_recent_messages(room_id: str, limit: int = 100) -> list:
    """
    Fetches the most recent messages from a Matrix room. Used to build context for
    """
    logger.info(f"Fetching last {limit} messages from room {room_id}.")
    client = DIRECTOR_CLIENT
    try:
        response = await client.room_messages(
            room_id=room_id,
            start=None,  # None fetches the latest messages
            limit=limit,
        )
        formatted_messages = []
        for event in response.chunk:
            if isinstance(event, RoomMessageText):
                formatted_messages.append({
                    "role": "user",
                    "content": event.body
                })

        logger.info(f"Fetched {len(formatted_messages)} messages from room {room_id}.")
        return formatted_messages

    except Exception as e:
        logger.exception(f"Failed to fetch messages from room {room_id}: {e}")
        return []


def store_token_info(user_id: str, access_token: str, device_id: str) -> None:
    """
    Write the token file to disk, so we can reuse it in later runs.
    """
    data = {
        "user_id": user_id,
        "access_token": access_token,
        "device_id": device_id
    }
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f)
    logger.debug(f"Stored token data for {user_id} into {TOKEN_FILE}.")


# ──────────────────────────────────────────────────────────
# SYNC TOKEN MANAGEMENT
# ──────────────────────────────────────────────────────────
def load_sync_token() -> str:
    """
    Load the previously saved sync token (next_batch).
    """
    if not os.path.exists(SYNC_TOKEN_FILE):
        return None
    try:
        with open(SYNC_TOKEN_FILE, "r") as f:
            return json.load(f).get("sync_token")
    except Exception as e:
        logger.warning(f"Failed to load sync token: {e}")
    return None

def store_sync_token(sync_token: str) -> None:
    """
    Persist the sync token so we won't re-fetch old messages on next run.
    """
    if not sync_token:
        return
    with open(SYNC_TOKEN_FILE, "w") as f:
        json.dump({"sync_token": sync_token}, f)
    logger.debug(f"Sync token saved to {SYNC_TOKEN_FILE}.")

async def post_gpt_reply(room_id: str, gpt_reply: str) -> None:
    """
    Helper to post a GPT-generated reply to a given room,
    using the global DIRECTOR_CLIENT if it's set.
    """
    global DIRECTOR_CLIENT

    if not DIRECTOR_CLIENT:
        logger.warning("No DIRECTOR_CLIENT set; cannot post GPT reply.")
        return

    try:
        await DIRECTOR_CLIENT.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": gpt_reply},
        )
        logger.info(f"Posted GPT reply to room {room_id}")
    except Exception as e:
        logger.exception(f"Failed to send GPT reply: {e}")
        
# ──────────────────────────────────────────────────────────
# CHECK RATE LIMIT
# ──────────────────────────────────────────────────────────
async def check_rate_limit() -> str:
    """
    Send a minimal sync request with a short timeout (1000 ms).
    If it returns SyncResponse => not rate-limited.
    If it's ErrorResponse => check the status code for 429 or something else.
    """
    global DIRECTOR_CLIENT
    if not DIRECTOR_CLIENT:
        return "No DIRECTOR_CLIENT available. Are we logged in?"

    try:
        response = await DIRECTOR_CLIENT.sync(timeout=1000)

        if isinstance(response, SyncResponse):
            return "200 OK => Not rate-limited. The server responded normally."
        elif isinstance(response, ErrorResponse):
            if response.status_code == 429:
                return "429 Too Many Requests => You are currently rate-limited."
            else:
                return (
                    f"{response.status_code} => Unexpected error.\n"
                    f"errcode: {response.errcode}, error: {response.error}"
                )
        return "Unexpected response type from DIRECTOR_CLIENT.sync(...)."
    except Exception as e:
        logger.exception(f"check_rate_limit encountered an error: {e}")
        return f"Encountered error while checking rate limit: {e}"

def _print_progress(stop_event):
    """
    Prints '...' every second until stop_event is set.
    """
    while not stop_event.is_set():
        print("...", end='', flush=True)
        time.sleep(1)

async def fetch_all_messages_once(
    client: AsyncClient, 
    room_ids: list[str] = None, 
    page_size: int = 100
) -> None:
    """
    Fetch *all* historical messages from the given room_ids (or all joined rooms if None).
    Populates the MESSAGES_CSV file, creating it if it doesn't exist or is empty.
    """
    if not room_ids:
        room_ids = list(client.rooms.keys())
        logger.info(f"No room_ids specified. Using all joined rooms: {room_ids}")

    all_records = []
    for rid in room_ids:
        logger.info(f"Fetching *all* messages for room: {rid}")
        room_history = await _fetch_room_history_paged(client, rid, page_size=page_size)
        all_records.extend(room_history)

    if not all_records:
        logger.warning("No messages fetched. CSV file will not be updated.")
        return

    df = pd.DataFrame(all_records, columns=["room_id", "event_id", "sender", "timestamp", "body"])
    logger.info(f"Fetched total {len(df)} messages across {len(room_ids)} room(s).")

    if os.path.exists(MESSAGES_CSV):
        try:
            # Attempt to read existing CSV
            existing_df = pd.read_csv(MESSAGES_CSV)
            logger.debug(f"Existing CSV loaded with {len(existing_df)} records.")
        except pd.errors.EmptyDataError:
            # Handle empty CSV by creating an empty DataFrame with the correct columns
            existing_df = pd.DataFrame(columns=["room_id", "event_id", "sender", "timestamp", "body"])
            logger.warning(f"{MESSAGES_CSV} is empty. Creating a new DataFrame with columns.")

        # Combine existing and new records
        combined_df = pd.concat([existing_df, df], ignore_index=True)
        # Drop duplicates based on 'room_id' and 'event_id'
        combined_df.drop_duplicates(subset=["room_id", "event_id"], keep="last", inplace=True)
        # Save back to CSV
        combined_df.to_csv(MESSAGES_CSV, index=False)
        logger.info(f"Appended new records to existing {MESSAGES_CSV}. New total: {len(combined_df)}")
    else:
        # If CSV doesn't exist, create it with the new records
        df.to_csv(MESSAGES_CSV, index=False)
        logger.info(f"Wrote all records to new CSV {MESSAGES_CSV}.")

async def _fetch_room_history_paged(
    client: AsyncClient, 
    room_id: str, 
    page_size: int
) -> list[dict]:
    """
    Helper to page backwards in time until no more messages or we hit server's earliest.
    ...
    """
    all_events = []
    end_token = None

    while True:
        try:
            response = await client.room_messages(
                room_id=room_id,
                start=end_token,
                limit=page_size,
                direction="b"
            )
            if not isinstance(response, RoomMessagesResponse):
                logger.warning(f"Got a non-success response: {response}")
                break
            
            chunk = response.chunk
            if not chunk:
                logger.info(f"No more chunk for {room_id}, done paging.")
                break

            for ev in chunk:
                if isinstance(ev, RoomMessageText):
                    all_events.append({
                        "room_id": room_id,
                        "event_id": ev.event_id,
                        "sender": ev.sender,
                        "timestamp": ev.server_timestamp,
                        "body": ev.body
                    })
            
            end_token = response.end
            if not end_token:
                logger.info(f"Got empty 'end' token for {room_id}, done paging.")
                break

            logger.debug(f"Fetched {len(chunk)} messages this page for room={room_id}, new end={end_token}")
            await asyncio.sleep(0.25)

        except Exception as e:
            logger.exception(f"Error in room_messages paging for {room_id}: {e}")
            break

    return all_events


# ──────────────────────────────────────────────────────────
# LIST USERS
# ──────────────────────────────────────────────────────────
async def list_users() -> list[dict]:
    """
    Returns a list of all users on the Synapse server, using the admin API.
    ...
    """
    homeserver_url = "http://localhost:8008"  # adjust if needed
    try:
        with open("data/tokens.json", "r") as f:
            data = json.load(f)
        admin_token = data["access_token"]
    except Exception as e:
        logger.error(f"Unable to load admin token from tokens.json: {e}")
        return []

    url = f"{homeserver_url}/_synapse/admin/v2/users"
    headers = {"Authorization": f"Bearer {admin_token}"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    resp_data = await resp.json()
                    raw_users = resp_data.get("users", [])
                    users_list = []
                    for u in raw_users:
                        users_list.append({
                            "user_id": u.get("name"),
                            "displayname": u.get("displayname"),
                            "admin": u.get("admin", False),
                            "deactivated": u.get("deactivated", False),
                        })
                    return users_list
                else:
                    text = await resp.text()
                    logger.error(f"Failed to list users (HTTP {resp.status}): {text}")
                    return []
    except Exception as e:
        logger.exception(f"Error calling list_users admin API: {e}")
        return []


# ──────────────────────────────────────────────────────────
# INVITE USER TO ROOM
# ──────────────────────────────────────────────────────────
async def invite_user_to_room(user_id: str, room_id_or_alias: str) -> str:
    """
    Force-join (invite) an existing Matrix user to a room/alias by calling
    the Synapse Admin API (POST /_synapse/admin/v1/join/<room_id_or_alias>)
    with a JSON body: {"user_id": "<user_id>"}

    Unlike a normal Matrix invite, this bypasses user consent. The user is
    automatically joined if they're local to this homeserver.

    Requirements:
      - The user running this code (DIRECTOR_CLIENT) must be a homeserver admin.
      - The user_id must be local to this server.
      - The admin must already be in the room with permission to invite.
    """
    from luna.luna_functions import DIRECTOR_CLIENT, getClient  # or your actual import path

    # Ensure we have a valid client with admin credentials
    client = getClient()  # or use DIRECTOR_CLIENT directly
    if not client:
        error_msg = "Error: No DIRECTOR_CLIENT available."
        logger.error(error_msg)
        return error_msg

    admin_token = client.access_token
    if not admin_token:
        error_msg = "Error: No admin token is present in DIRECTOR_CLIENT."
        logger.error(error_msg)
        return error_msg

    homeserver_url = client.homeserver
    # Endpoint for forced join
    endpoint = f"{homeserver_url}/_synapse/admin/v1/join/{room_id_or_alias}"

    payload = {"user_id": user_id}
    headers = {"Authorization": f"Bearer {admin_token}"}

    logger.debug("Force-joining user %s to room %s via %s", user_id, room_id_or_alias, endpoint)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, json=payload) as resp:
                if resp.status in (200, 201):
                    logger.info(f"Successfully forced {user_id} into {room_id_or_alias}.")
                    return f"Forcibly joined {user_id} to {room_id_or_alias}."
                else:
                    text = await resp.text()
                    logger.error(f"Failed to force-join {user_id} to {room_id_or_alias}: {text}")
                    return f"Error {resp.status} forcibly joining {user_id} => {text}"
    except Exception as e:
        logger.exception(f"Exception while forcing {user_id} into {room_id_or_alias}: {e}")
        return f"Exception forcibly joining {user_id} => {e}"

def getClient():
    return DIRECTOR_CLIENT

=== luna_personas.py ===
# luna_personalities.py
import os
import json
import datetime
import yaml
import os
import logging

logger = logging.getLogger(__name__)

PERSONALITIES_FILE = "data/luna_personalities.json"

def _load_personalities() -> dict:
    """
    Internal helper to load the entire JSON dictionary from disk.
    Returns {} if file not found or invalid.
    """
    
    if not os.path.exists(PERSONALITIES_FILE):
        return {}
    try:
        with open(PERSONALITIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # If malformed or other error
        return {}


def _save_personalities(data: dict) -> None:
    """
    Internal helper to write the entire JSON dictionary to disk.
    """
    # Using `ensure_ascii=False` to better handle spaces, quotes, and
    # avoid weird escape behavior for non-ASCII. `indent=2` is still fine.
    with open(PERSONALITIES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _sanitize_field(value: str) -> str:
    """
    Strips leading and trailing quotes or whitespace from a field,
    and removes embedded unescaped quotes that might break JSON structure.
    Adjust logic as needed for your environment or console usage.
    """
    if not value:
        return ""

    # Remove leading/trailing quotes/spaces
    cleaned = value.strip().strip('"').strip()

    # Remove any accidental embedded quotes that might fragment JSON
    # (If you prefer to keep them and properly escape them, that is also an option.)
    cleaned = cleaned.replace('"', '')

    return cleaned


def create_bot(
    bot_id: str,
    displayname: str,
    password:str,
    creator_user_id: str,
    system_prompt: str,
    traits: dict | None = None,
    notes: str = ""
) -> dict:
    """
    Creates a new bot persona entry in personalities.json.

    :param bot_id: The Matrix user ID for this bot (e.g. "@mybot:localhost").
    :param displayname: A user-friendly name, e.g. "Anne Bonny".
    :param creator_user_id: The user who spawned this bot (e.g. "@lunabot:localhost").
    :param system_prompt: GPT system text describing the bot’s style/personality.
    :param traits: Optional dictionary with arbitrary traits (age, color, etc.).
    :param notes: Optional freeform text or dev notes.
    :return: The newly created bot data (dict).
    """

    data = _load_personalities()

    # If the bot_id already exists, you might want to error out or update.
    # For now, let's raise an exception to keep it simple.
    if bot_id in data:
        raise ValueError(f"Bot ID {bot_id} already exists in {PERSONALITIES_FILE}.")

    # Clean up potential quotes
    displayname_clean = _sanitize_field(displayname)
    system_prompt_clean = _sanitize_field(system_prompt)
    notes_clean = _sanitize_field(notes)

    # Build the new persona
    persona = {
        "displayname": displayname_clean,
        "system_prompt": system_prompt_clean,
        "password": password,
        "traits": traits if traits else {},
        "creator_user_id": creator_user_id,
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",  # e.g. 2025-01-07T14:06:15Z
        "notes": notes_clean
    }

    data[bot_id] = persona
    _save_personalities(data)

    return persona


def update_bot(bot_id: str, updates: dict) -> dict:
    """
    Updates an existing bot persona with given key-value pairs.

    :param bot_id: The Matrix user ID for this bot (e.g. "@mybot:localhost").
    :param updates: A dict of fields to update, e.g. {"displayname": "New Name"}.
    :return: The updated bot data (dict).
    """
    data = _load_personalities()

    if bot_id not in data:
        raise ValueError(f"Bot ID {bot_id} not found in {PERSONALITIES_FILE}.")

    persona = data[bot_id]

    # Clean each field if it's a string
    for key, val in updates.items():
        if isinstance(val, str):
            updates[key] = _sanitize_field(val)

    # Merge updates in
    for key, val in updates.items():
        persona[key] = val

    data[bot_id] = persona
    _save_personalities(data)
    return persona


def read_bot(bot_id: str) -> dict | None:
    """
    Fetch a single bot persona by ID.

    :param bot_id: The Matrix user ID (e.g. "@mybot:localhost").
    :return: The bot's data dict, or None if not found.
    """
    data = _load_personalities()
    return data.get(bot_id)


def delete_bot_persona(bot_id: str) -> None:
    """
    Removes the bot entry from personalities.json.
    Raises KeyError if bot_id not found.
    """
    data = _load_personalities()
    if bot_id not in data:
        raise KeyError(f"Bot ID {bot_id} not found in {PERSONALITIES_FILE}")

    del data[bot_id]  # remove that entry
    _save_personalities(data)
    # no return needed; it either succeeds or raises an exception


def load_luna_config() -> dict:
    """
    Loads the config from data/config/config.yaml and returns it as a dict.
    Expected structure (example):
    
    bots:
      luna:
        system_prompt: |
          You are Luna, the advanced AI director...
    """
    config_path = "data/config/config.yaml"
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def get_system_prompt_by_localpart(localpart: str) -> str | None:
    """
    Returns the system_prompt for the bot whose localpart is `localpart`,
    or None if that bot does not exist or has no system prompt.
    """

    bot_id = f"@{localpart}:localhost"

    # 1) Try reading a persona for the given bot.
    persona = read_bot(bot_id)
    if persona:
        return persona.get("system_prompt")

    # 2) If no persona found but this is lunabot, read from config.yaml
    if localpart == "lunabot":
        logger.debug("No persona found in read_bot for lunabot => loading from config.yaml")
        cfg = load_luna_config()
        # Adapt key lookups to your actual YAML structure:
        # e.g.  cfg['bots']['luna']['system_prompt'] if your file is structured that way.
        try:
            system_prompt = cfg["bots"]["luna"]["system_prompt"]
            return system_prompt
        except KeyError:
            logger.warning("No 'bots.luna.system_prompt' found in config.yaml.")
            return None

    # 3) Otherwise, no system prompt available
    return None

def set_system_prompt_by_localpart(localpart: str, new_prompt: str) -> dict | None:
    """
    Updates the system_prompt for the bot whose localpart is `localpart`.
    Returns the updated persona dict, or None if the bot doesn't exist.

    :param localpart: The localpart of the bot user (e.g. "inky").
    :param new_prompt: The new system_prompt text to set.
    :return: The updated bot data dict, or None if not found.
    """
    bot_id = f"@{localpart}:localhost"
    existing = read_bot(bot_id)
    if not existing:
        return None  # bot doesn't exist

    # Update with the sanitized prompt
    updated = update_bot(bot_id, {"system_prompt": new_prompt})
    return updated

=== requirements.txt ===

=== run_luna.py ===
#!/usr/bin/env python3

"""
run_luna.py

A simple entry-point script that imports 'luna_main' from 'core'
and runs it.
"""

import sys

# Import the main entry function from core.py
from luna.core import luna_main

def main():
    """
    Simply calls the 'luna_main()' function, which will:
     - configure logging
     - create an event loop
     - start the console thread
     - run the main logic
    """
    print("Launching Luna from run_luna.py ...")
    luna_main()

if __name__ == "__main__":
    main()

=== sync_token.json ===
{"sync_token": "s7_139_0_1_8_1_1_10_0_1"}
