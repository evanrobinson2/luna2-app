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
