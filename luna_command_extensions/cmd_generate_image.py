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