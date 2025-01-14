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
