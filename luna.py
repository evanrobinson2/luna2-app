"""
luna.py

- Configures logging (console + file)
- Creates one main event loop
- Spawns the console in a background thread (reads user commands, schedules coroutines)
- Runs the 'main_logic' which logs in (reusing token or password) and syncs forever
"""

import asyncio
import sys
import logging
import threading

from nio import RoomMessageText, InviteMemberEvent, AsyncClient
from src.luna_functions import (
    on_room_message,
    on_invite_event,
    load_or_login_client,
)
from src.console_apparatus import console_loop

# We'll store the main event loop globally so both the console thread
# and the Director logic can access it.
MAIN_LOOP = None

def configure_logging():
    """
    Configure Python's logging so logs go to both console and server.log.
    """
    logger = logging.getLogger(__name__)
    logging.getLogger("nio.responses").setLevel(logging.CRITICAL)
    logger.debug("Entering configure_logging function.")

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Overall log level
    logger.debug("Set root logger level to DEBUG.")

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.debug("Formatter for logs created.")

    file_handler = logging.FileHandler("server.log", mode="a")  # Append to server.log
    file_handler.setLevel(logging.DEBUG)  # Store everything (DEBUG+) in the file
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    logger.debug("Added file handler to root logger. Logging to 'server.log' at DEBUG level.")

    logger.debug("Exiting configure_logging function.")


def start_console_thread(loop):
    """
    Spawn the console input loop in a background thread,
    passing in `loop` so commands can schedule tasks on that loop.
    """
    logger = logging.getLogger(__name__)
    logger.debug("Entering start_console_thread function.")

    try:
        thread = threading.Thread(target=lambda: console_loop(loop), daemon=True)
        thread.start()
        logger.info("Console thread started successfully.")
    except Exception as e:
        logger.exception(f"Failed to start console thread: {e}")

    logger.debug("Exiting start_console_thread function.")


async def main_logic():
    """
    Main async logic:
    1. Acquire AsyncClient (preferring token-based login, else do password login)
    2. Registers callbacks
    3. Calls sync_forever to handle events
    """
    logger = logging.getLogger(__name__)
    logger.debug("Entering main_logic function...")

    # 1. Acquire a client (token-based if possible, otherwise password)
    logger.debug("Attempting to load or log in the client.")
    await asyncio.sleep(0.1)
    client: AsyncClient = await load_or_login_client(
        homeserver_url="http://localhost:8008",
        username="luna",   # e.g., @luna:localhost
        password="12345"
    )
    logger.debug("Client obtained. Storing reference to DIRECTOR_CLIENT in src.luna_functions.")
    
    # 2. Register callbacks for messages & invites
    client.add_event_callback(on_room_message, RoomMessageText)
    client.add_event_callback(on_invite_event, InviteMemberEvent)
    logger.debug("Callbacks registered successfully.")

    # 3. Start the sync loop
    logger.debug("Starting sync_forever loop. Awaiting new events with timeout=30000.")
    await client.sync_forever(timeout=30000)
    logger.debug("sync_forever has exited (unexpected in normal operation).")


def luna():
    """
    Orchestrates everything:
    - Configure logging
    - Create the main event loop
    - Start the console thread (which schedules coroutines on the loop)
    - Run `main_logic()` until complete (i.e., forever, unless Ctrl+C, etc.)
    """
    logger = logging.getLogger(__name__)
    logger.debug("Entering luna() function.")

    # 1. Configure logging
    configure_logging()
    logger.debug("Logging configuration complete.")

    # 2. Create our own event loop
    logger.debug("Creating a new asyncio event loop.")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    logger.debug("Set this new loop as the default event loop for the current thread.")

    global MAIN_LOOP
    MAIN_LOOP = loop  # Store in a global
    logger.debug("Stored reference to the new loop in MAIN_LOOP.")

    # 3. Start the console in a background thread
    start_console_thread(loop)
    logger.debug("Console thread has been initiated. Returning to main thread.")

    # 4. Run the main async logic (token-based login & sync) on this loop
    try:
        logger.info("Starting main_logic coroutine.")
        loop.run_until_complete(main_logic())
    except KeyboardInterrupt:
        logger.warning("KeyboardInterrupt received. Shutting down Director.")
    except Exception as e:
        logger.exception(f"An unexpected exception occurred in main_logic: {e}")
    finally:
        logger.debug("Preparing to close the event loop.")
        loop.close()
        logger.info("Event loop closed. Exiting main function.")


if __name__ == "__main__":
    luna()
