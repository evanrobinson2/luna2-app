# File: luna_functions_team.py

import json
import logging
import datetime
import asyncio
from src.ai_functions import get_gpt_response
from src.luna_functions import create_user, invite_user_to_room, getClient
from luna_command_extensions.luna_functions_create_room import create_room
from src.luna_personas import create_bot

logger = logging.getLogger(__name__)

def cmd_assemble(args, loop):
    """
    A synchronous console command that calls GPT asynchronously
    and parses the JSON result.
    """
    # 1) Make a future
    future = asyncio.run_coroutine_threadsafe(
        get_gpt_response(
            context=[{"role": "user", "content": "Generate some JSON"}],
            model="gpt-4"
        ),
        loop
    )

    # 2) Block until that future is done, retrieving the actual string
    try:
        gpt_response_str = future.result()  # This is the JSON string
    except Exception as e:
        print(f"SYSTEM: Error calling GPT => {e}")
        return

    # 3) Now parse the string with json.loads
    import json
    try:
        personas = json.loads(gpt_response_str)
    except json.JSONDecodeError as e:
        print(f"SYSTEM: GPT returned invalid JSON => {e}")
        print("SYSTEM: Raw GPT response was:")
        print(gpt_response_str)
        return

    print("SYSTEM: Successfully parsed GPT persona data:")
    print(personas)