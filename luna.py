"""
luna.py

- Configures logging (console + file)
- Creates one main event loop
- Spawns the console in a background thread (reads user commands, schedules coroutines)
- Runs the 'main_logic' which logs in and syncs forever
"""

import asyncio
import sys
import logging
import threading

from nio import RoomMessageText, InviteMemberEvent, AsyncClient, LoginResponse

import src.luna_functions
from src.luna_functions import on_room_message, on_invite_event
from src.console_functions import console_loop

# We'll store the main event loop globally so both the console thread
# and the Director logic can access it.
MAIN_LOOP = None

def configure_logging():
    """
    Configure Python's logging so logs go to both console and server.log.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Overall log level

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = logging.FileHandler("server.log", mode="a")  # Append to server.log
    file_handler.setLevel(logging.DEBUG)  # Store everything (DEBUG+) in the file
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

def start_console_thread(loop):
    """
    Spawn the console input loop in a background thread,
    passing in `loop` so commands can schedule tasks on that loop.
    """
    thread = threading.Thread(target=lambda: console_loop(loop), daemon=True)
    thread.start()

async def main_logic():
    """
    Main async logic:
    1. Instantiates AsyncClient
    2. Logs in the Director
    3. Registers callbacks
    4. Calls sync_forever to handle events
    """
    logger = logging.getLogger(__name__)
    logger.debug("Entering main_logic function...")

    # 1. Create the AsyncClient
    client = AsyncClient(
        homeserver="http://localhost:8008",  # Update as needed
        user="@director:localhost",          # Update as needed
    )

    # 2. Log in the Director
    resp = await client.login(password="12345", device_name="LunaDirector")
    if isinstance(resp, LoginResponse):
        logger.info("Director logged in successfully.")
        # Point the global in src.luna_functions to this client
        src.luna_functions.DIRECTOR_CLIENT = client
    else:
        logger.error(f"Failed to log in: {resp}")
        sys.exit(1)

    # 3. Register callbacks for messages & invites
    client.add_event_callback(on_room_message, RoomMessageText)
    client.add_event_callback(on_invite_event, InviteMemberEvent)

    logger.debug("Starting sync_forever loop. Waiting for new events...")
    await client.sync_forever(timeout=30000)
    logger.debug("sync_forever has exited (unexpected in normal operation).")

def main():
    """
    Orchestrates everything:
    - Configure logging
    - Create the main event loop
    - Start the console thread (which schedules coroutines on the loop)
    - Run `main_logic()` until complete (i.e., forever, unless Ctrl+C, etc.)
    """
    configure_logging()

    # 1. Create our own event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)  # Make it the default for this thread

    global MAIN_LOOP
    MAIN_LOOP = loop  # Store in a global, so if we want, we can reference it

    # 2. Start the console in a background thread, passing it the same loop
    start_console_thread(loop)

    # 3. Run the main async logic (director login & sync) on this loop
    try:
        loop.run_until_complete(main_logic())
    except KeyboardInterrupt:
        logger = logging.getLogger(__name__)
        logger.info("Shutting down Director via KeyboardInterrupt.")
    finally:
        # 4. If we exit, close everything gracefully
        logger = logging.getLogger(__name__)
        logger.debug("Closing event loop.")
        loop.close()

if __name__ == "__main__":
    main()
