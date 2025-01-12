import logging
import shlex  # <-- We’ll use this to parse user arguments correctly

logger = logging.getLogger(__name__)

from src.luna_functions import getClient
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
