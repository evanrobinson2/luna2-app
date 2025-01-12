import logging

logger = logging.getLogger(__name__)

from src.luna_functions import getClient
from nio import RoomCreateResponse 
from nio.api import RoomVisibility

async def create_room(room_name: str, is_public: bool = True) -> str:
    """
    Creates a new Matrix room, returning a message describing the outcome.
    By default, it creates a public room, but if is_public=False, a private room
    is created instead. The function references DIRECTOR_CLIENT from src.luna_functions.
    
    Args:
        room_name (str): The name for the new Matrix room.
        is_public (bool): If True, room is public; otherwise it's private.
    
    Returns:
        str: A result message describing success or failure.
    """
    logger.debug("Entering create_room() with room_name=%r, is_public=%r", room_name, is_public)
    
    client = getClient()
    # Check if there's a global client available
    if not client:
        logger.debug("No DIRECTOR_CLIENT found. Exiting early with error message.")
        return "Error: No DIRECTOR_CLIENT set."
    
    try:
        # Convert is_public into the appropriate RoomVisibility
        room_visibility = RoomVisibility.public if is_public else RoomVisibility.private
        logger.debug("Setting room_visibility to %s", room_visibility)

        # Attempt to create the room
        logger.debug(
            "Calling DIRECTOR_CLIENT.room_create(name=%r, visibility=%r)",
            room_name, room_visibility
        )
        response = await client.room_create(name=room_name, visibility=room_visibility)

        # Check the response type
        if isinstance(response, RoomCreateResponse):
            logger.debug("RoomCreateResponse received. room_id=%r", response.room_id)
            return f"Created room '{room_name}' => {response.room_id}"
        else:
            # Possibly an ErrorResponse or another unexpected type
            logger.debug("Received a non-RoomCreateResponse => %r", response)
            return f"Error creating room => {response}"

    except Exception as e:
        logger.exception("Caught an exception while creating room %r:", room_name)
        return f"Exception while creating room => {e}"
