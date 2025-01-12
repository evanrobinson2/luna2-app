"""
create_and_login_bot.py

Handles creating a new bot persona record + user account + ephemeral login.
"""

import logging
import asyncio

# Adjust these imports for your project structure:
from src.luna_functions import (
    create_user,
    load_or_login_client_v2
)
import src.luna_personas

logger = logging.getLogger(__name__)


async def create_and_login_bot(
    bot_id: str,
    password: str,
    displayname: str,
    system_prompt: str,
    traits: dict,
    creator_user_id: str = "@lunabot:localhost",
    is_admin: bool = False
) -> str:
    """
    1) Creates a local persona entry in personalities.json (using bot_id as key).
    2) Calls create_user(...) to register with Synapse.
    3) Does ephemeral login (load_or_login_client_v2).
    4) Stores the new AsyncClient in BOTS[localpart].

    :param bot_id: Full Matrix user ID, e.g. "@spiderbot:localhost".
    :param password: The password for the new bot.
    :param displayname: The user-friendly name for the bot.
    :param system_prompt: GPT system instructions or persona description.
    :param traits: A dictionary of arbitrary trait key-values (e.g. theme, power).
    :param creator_user_id: Who “spawned” this bot. Default is @lunabot:localhost.
    :param is_admin: Whether to create an admin user in Synapse. Defaults to False.
    :return: Success/error string.
    """

    # 1) Parse out the localpart from e.g. "@spiderbot:localhost" => "spiderbot"
    if not bot_id.startswith("@") or ":" not in bot_id:
        return f"[create_and_login_bot] Invalid bot_id => {bot_id}"

    localpart = bot_id.split(":")[0].replace("@", "")  # e.g. "spiderbot"

    # 2) Create the local persona in personalities.json
    try:
        persona = src.luna_personas.create_bot(
            bot_id=bot_id,
            password=password,
            displayname=displayname,
            creator_user_id=creator_user_id,
            system_prompt=system_prompt,
            traits=traits
        )
        logger.info(f"[create_and_login_bot] Saved persona for {bot_id} into personalities.json")
    except Exception as e:
        msg = f"[create_and_login_bot] Could not create persona => {e}"
        logger.exception(msg)
        return msg

    # 3) Actually create the user in Synapse
    username = localpart  # the localpart only
    creation_msg = await create_user(username, password, is_admin=is_admin)
    if not creation_msg.startswith("Created user"):
        # e.g. "Error creating user..." or "HTTP 409 user already exists..."
        error_msg = f"[create_and_login_bot] Could not create user '{username}'. => {creation_msg}"
        logger.error(error_msg)
        return error_msg

    # 4) Ephemeral login
    try:
        client = await load_or_login_client_v2(
            homeserver_url="http://localhost:8008",  # or from config
            user_id=bot_id,
            password=password,
            device_name=f"{localpart}_device"
        )
    except Exception as e:
        logger.exception(f"[create_and_login_bot] Ephemeral login failed for {bot_id}: {e}")
        return f"Error ephemeral-logging in {bot_id}: {e}"

    # 5) Store the AsyncClient in luna.py:BOTS
    try:
        # Deferred import to avoid circular references
        from luna import BOTS
        BOTS[localpart] = client
        logger.info(f"[create_and_login_bot] Stored {bot_id} in BOTS as '{localpart}'")
    except Exception as e:
        logger.exception(f"[create_and_login_bot] Could not store {bot_id} in BOTS: {e}")
        return f"Error storing {bot_id} in BOTS => {e}"

    success_msg = f"Successfully created + logged in => {bot_id}"
    logger.info(success_msg)
    return success_msg


# Optional test harness if run directly
if __name__ == "__main__":
    async def test_run():
        user_id_full = "@testbot123:localhost"
        pwd  = "testbotPass!"
        display = "Test Bot #123"
        s_prompt = "You are a friendly test-bot for demonstration."
        traits_example = {"color": "blue", "hobby": "testing code"}
        
        result = await create_and_login_bot(
            bot_id=user_id_full,
            password=pwd,
            displayname=display,
            system_prompt=s_prompt,
            traits=traits_example
        )
        print(result)

    asyncio.run(test_run())
