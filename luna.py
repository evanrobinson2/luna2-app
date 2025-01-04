"""
luna.py

Ultra-minimal main launcher:
- Configures logging (console + file)
- Starts the console in a background thread (reads user commands)
- Runs the 'main_logic' which logs in and syncs forever
- Respects the additional files: console_functions.py and luna_functions.py
"""

import asyncio
import sys
import logging
import threading

from nio import RoomMessageText, InviteMemberEvent, AsyncClient, LoginResponse

from src.luna_functions import director_login, on_room_message, on_invite_event, DIRECTOR_CLIENT
from src.console_functions import console_loop
import src.luna_functions

def configure_logging():
    """
    Configure Python's logging so logs go to both console and server.log.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Overall log level

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)  # Show INFO+ in console
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    file_handler = logging.FileHandler("server.log", mode="a")  # Append to server.log
    file_handler.setLevel(logging.DEBUG)  # Store everything (DEBUG+) in the file
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

def start_console_thread():
    """
    Spawn the console input loop in a background thread.
    (The loop is defined in console_functions.py)
    """
    thread = threading.Thread(target=console_loop, daemon=True)
    thread.start()

async def main_logic():
    """
    Main async logic:
    1. Instantiates AsyncClient
    2. Logs in the Director
    3. Registers callbacks
    4. sync_forever to handle events
    """
    logger = logging.getLogger(__name__)
    logger.debug("Entering main_logic function...")

    # 1. Create the AsyncClient
    client = AsyncClient(
        homeserver="http://localhost:8008",  # Replace with your Matrix server
        user="@director:localhost",         # Replace with your Director's user ID
    )

    # 2. Log in the Director
    resp = await client.login(password="12345", device_name="LunaDirector")
    if isinstance(resp, LoginResponse):
        logger.info("Director logged in successfully.") 
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

if __name__ == "__main__":
    try:
        # Configure logging once at startup
        configure_logging()

        # Start the console input loop in a background thread
        start_console_thread()

        # Run the main async function
        asyncio.run(main_logic())

    except KeyboardInterrupt:
        logger = logging.getLogger(__name__)
        logger.info("Shutting down Director via KeyboardInterrupt.")
        logger.debug("Caught KeyboardInterrupt; exiting now.")

    except SystemExit:
        logger = logging.getLogger(__name__)
        logger.info("SystemExit triggered; shutting down.")
        if DIRECTOR_CLIENT and not DIRECTOR_CLIENT.closed:
            asyncio.run(DIRECTOR_CLIENT.close())
        sys.exit(0)
