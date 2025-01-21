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
DATABASE_PATH = "data/luna.db"

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
