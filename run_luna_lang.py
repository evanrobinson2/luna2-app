# luna/run_lanluna.py

import os
import logging
import yaml
import json
import asyncio
import time
from dotenv import load_dotenv
from nio import (
    LoginResponse,
    AsyncClient,
    RoomMessageText,
    InviteMemberEvent,
    RoomMemberEvent
)

# LangGraph imports
from langgraph.graph import StateGraph, START, END

# If you're using ChatOpenAI directly:
from langchain_openai import ChatOpenAI
from langchain.schema import AIMessage, HumanMessage

# Import the global variables & typed dict
import luna.GLOBALS as g
# If these handlers are in separate files, adjust imports accordingly:
from luna.luna_command_extensions.bot_message_handler import handle_bot_room_message
from luna.luna_command_extensions.bot_invite_handler import handle_bot_invite
from luna.luna_command_extensions.bot_member_event_handler import handle_bot_member_event
# from luna.luna_command_extensions.luna_message_handler5 import handle_luna_message5
from luna.luna_lang import handle_user_message
from luna.bot_messages_store import load_messages
from luna.luna_command_extensions.ascii_art import show_ascii_banner

# luna_lang.py
import asyncio
import logging

from nio import RoomMessageText, AsyncClient
from langchain.schema import AIMessage, HumanMessage

import luna.GLOBALS as g
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict
from typing import Annotated


class State(TypedDict):
    # A typed dict to hold conversation messages in the node-based workflow.
    messages: Annotated[list, add_messages]


def console_chatbot_node(state: State):
    """
    A single node function that uses the global LLM to respond to user messages.
    state["messages"] is a list of user/assistant messages (HumanMessage / AIMessage).
    We'll call g.LLM.invoke(...) with that list, then return the new assistant message.
    """
    g.LOGGER.info("chatbot_node called with %d messages", len(state["messages"]))

    if g.LLM is None:
        g.LOGGER.error("Global LLM is None! Did _init_globals not run properly?")
        raise RuntimeError("Global LLM not initialized.")

    # Actually call the LLM
    response_msg = g.LLM.invoke(state["messages"])

    g.LOGGER.info("LLM returned an AIMessage of type: %s", type(response_msg).__name__)
    return {"messages": [response_msg]}

async def main():
    g.LOGGER = _configure_logging()

    g.LOGGER.info(f"----------------------------------------------------------------------")
    g.LOGGER.info(f"------                 STARTING UP LUNA LANGGRAPH               ------")
    g.LOGGER.info(f"------                     {g.LUNA_VERSION}                   ------")
    g.LOGGER.info(f"----------------------------------------------------------------------")

    ########## LOAD OPEN AI KEY
    g.LOGGER.info(f"Loading Luna OPENAI_API_KEY from .env. STARTING")    
    load_dotenv()  # loads .env     
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        g.LOGGER.critical("No OPENAI_API_KEY found. Exiting.")
        return
    g.OPENAI_API_KEY = key
    g.LOGGER.info("Set g.OPENAI_API_KEY to: %s******", key[:5])

    g.LOGGER.info("Loading Luna OPENAI_API_KEY from .env. COMPLETE")

    ########## LOAD LUNA RAM (OMNI-PURPOSE IN-MEMORY PARAMS)
    g.LOGGER.info("Loading Luna random access memory variables from config.yaml. STARTING")    
    _init_luna_ram() 
    g.LOGGER.info("Loading Luna random access memory variables from config.yaml. COMPLETE")

    ########## LOAD CHATROOM MESSAGES FROM DATABASE
    g.LOGGER.info("Loading bot messages store. STARTING")
    load_messages() 
    g.LOGGER.info("Loading bot messages store. COMPLETE")
    
    ########## CONNECT TO THE MATRIX SERVER AS LUNA
    g.LOGGER.info("Luna client login. STARTING")
    # A) Log in Luna (the "director" user)
    luna_client = await _login_matrix_client(
        homeserver_url = g.HOMESERVER_URL,
        user_id = g.LUNA_USERNAME,
        password = g.LUNA_PASSWORD
    )
    g.LOGGER.info("Luna client login. COMPLETE")

    # -- 1) Attach Luna's event callbacks --
    # For messages:
    luna_client.add_event_callback(
        lambda room, event: handle_user_message(luna_client, "lunabot", room, event),
        RoomMessageText
    )

    # For invites (the same invite handler you'd use for normal bots, or a specialized one):
    luna_client.add_event_callback(
        lambda room, event: handle_bot_invite(luna_client, "lunabot", room, event),
        InviteMemberEvent
    )

    # For membership changes (same or specialized):
    luna_client.add_event_callback(
        lambda room, event: handle_bot_member_event(luna_client, "lunabot", room, event),
        RoomMemberEvent
    )

    ########## CONNECT TO THE AS EACH OF THE BOTS
    g.LOGGER.info("Logging in ephemeral bots. STARTING")
    asyncio.create_task(_login_all_bots(g.PERSONALITIES_FILE, g.BOTS))    
    g.LOGGER.info("Logging in ephemeral bots. Ayncio create_task DISPATCHED SUCCESSFULLY.")
     
    # 3) Initialize the global LLM
    g.LOGGER.info("Initializing global LLM. STARTING")
    g.LLM = ChatOpenAI(
        openai_api_key=g.OPENAI_API_KEY,
        model_name="gpt-3.5-turbo",
        temperature=0.0
    )   
    g.LOGGER.info("Initializing global LLM. COMPLETE")

    # 5) Build a minimal graph => START -> chatbot_node -> END
    g.LOGGER.info("Building minimal MVP graph. STARTING")
    graph_builder = StateGraph(g.State)
    graph_builder.add_node("chatbot", console_chatbot_node)
    graph_builder.add_edge(START, "chatbot")
    graph_builder.add_edge("chatbot", END)
    graph = graph_builder.compile()
    g.LOGGER.info("Building minimal MVP graph. COMPLETED")

    # We'll store the entire conversation in memory
    conv_state = {"messages": []}

    os.system('clear')
    print(show_ascii_banner("LUNA LANG"))

    # -- 2) For each loaded bot, attach event callbacks and start a sync loop
    bot_tasks = []
    for localpart, bot_client in g.BOTS.items():
        try:
            # Register each callback via a distinct helper
            bot_client.add_event_callback(
                _make_message_callback(bot_client, localpart),
                RoomMessageText
            )
            bot_client.add_event_callback(
                _make_invite_callback(bot_client, localpart),
                InviteMemberEvent
            )
            bot_client.add_event_callback(
                _make_member_callback(bot_client, localpart),
                RoomMemberEvent
            )

            # Start its sync loop
            task = asyncio.create_task(_run_bot_sync(bot_client, localpart))
            bot_tasks.append(task)

            g.LOGGER.info(f"Set up bot '{localpart}' successfully.")

        except Exception as e:
            g.LOGGER.exception(f"Error setting up bot '{localpart}': {e}")


    # 5) Run the console loop & matrix sync loop concurrently.
    sync_task = asyncio.create_task(_matrix_sync_loop(luna_client))
    console_task = asyncio.create_task(_console_loop())

    # Wait until either the console requests a quit OR the sync loop terminates.
    done, pending = await asyncio.wait(
        [sync_task, console_task],
        return_when=asyncio.FIRST_COMPLETED
    )


    # # Append the user’s message as a dict or HumanMessage
    # conv_state["messages"].append({"role": "user", "content": user_input})

    # g.LOGGER.info("conv_state now has %d total messages", len(conv_state["messages"]))

    # # 8) Execute the graph
    # events = graph.stream(conv_state, stream_mode="values")

    # assistant_msg = None
    # for e in events:
    #     if "messages" in e:
    #         assistant_msg = e["messages"][-1]
    #         conv_state["messages"] = e["messages"]

    # # 9) Print the assistant's reply
    # if assistant_msg:
    #     # Usually an AIMessage
    #     if isinstance(assistant_msg, dict):
    #         print("Assistant:", assistant_msg.get("content", ""))
    #     else:
    #         print("Assistant:", assistant_msg.content)
    
    # shutdown operations
    await luna_client.logout()
    await luna_client.close()
    await _shutdown_all_bots()
    g.LOGGER.info("----------------------------------------------------------------------")
    g.LOGGER.info("------              SHUTTING DOWN LUNA LANGGRAPH                ------")
    g.LOGGER.info("----------------------------------------------------------------------")

import time

async def _login_all_bots(personalities_file, BOTS):
    """
    Reads 'data/luna_personalities.json', ephemeral-logs each bot,
    and stores the resulting AsyncClient in a local dict (BOTS).
    Does NOT attach event callbacks or start sync tasks here.
    
    Now collects aggregated stats:
     - how many bots had no password => "skipped"
     - how many had success
     - how many failed
    Then logs a summary with comma-separated localpart: @localpart:localhost

    We also track how long the entire login process took using a simple stopwatch.
    """
    start_time = time.monotonic()

    if not os.path.exists(personalities_file):
        g.LOGGER.error(f"Bot login file not found: {personalities_file}")
        return {}

    with open(personalities_file, "r", encoding="utf-8") as f:
        personalities_data = json.load(f)

    # Lists to track results
    skipped_bots = []
    success_bots = []
    fail_bots = []

    homeserver_url = g.HOMESERVER_URL

    for user_id, persona in personalities_data.items():
        # user_id might be something like "@venom_shock:localhost"
        localpart = user_id.split(":")[0].replace("@", "")
        password = persona.get("password", "")

        if not password:
            # Skip due to no password
            skipped_bots.append(f"@{localpart}:localhost")
            continue

        # Attempt login
        try:
            client = await _login_matrix_client(
                homeserver_url=homeserver_url,
                user_id=user_id,
                password=password,
                device_name=f"{localpart}_device"
            )
            BOTS[localpart] = client
            success_bots.append(f"@{localpart}:localhost")
        except Exception as e:
            fail_bots.append(f"@{localpart}:localhost")

    # Summaries
    num_skipped = len(skipped_bots)
    num_success = len(success_bots)
    num_fail = len(fail_bots)
    num_total = num_skipped + num_success + num_fail

    # Comma-separated lists
    skipped_list = ", ".join(skipped_bots) if skipped_bots else "(none)"
    success_list = ", ".join(success_bots) if success_bots else "(none)"
    fail_list = ", ".join(fail_bots) if fail_bots else "(none)"

    # Log everything in one summary
    g.LOGGER.info(
        "Bot login results: %d total in file, %d skipped (no password), %d success, %d fail",
        num_total, num_skipped, num_success, num_fail
    )
    g.LOGGER.info("Skipped bots: %s", skipped_list)
    g.LOGGER.info("Successful logins: %s", success_list)
    g.LOGGER.info("Failed logins: %s", fail_list)

    # End stopwatch
    end_time = time.monotonic()
    elapsed = end_time - start_time
    g.LOGGER.info("All ephemeral bot logins finished in %.3f seconds.", elapsed)

async def _shutdown_all_bots():
    """
    Logs out each bot in the global BOTS dict.
    """
    for localpart, client in g.BOTS.items():
        try:
            await client.logout()
            await client.close()
        except Exception as e:
            g.LOGGER.exception(f"Failed to logout bot '{localpart}': {e}")
        else:
            g.LOGGER.info(f"Logged out bot '{localpart}'.")

def _configure_logging():
    """
    Configures Python logging to remove any console logs and only log to a file,
    with the root logger set to DEBUG and function names in the output.
    """
    # 1) Remove any existing handlers from the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # If you previously called logging.basicConfig(level=...), it might have
    # attached a default StreamHandler to the root logger. We remove them all:
    while root_logger.handlers:
        root_logger.removeHandler(root_logger.handlers[0])

    # 2) Create a file handler with your desired format
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(funcName)s: %(message)s"
    )

    os.makedirs("data/logs", exist_ok=True)
    log_file_path = "data/logs/server.log"
    
    file_handler = logging.FileHandler(log_file_path, mode="a")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # 3) Attach only this file handler to the root logger
    root_logger.addHandler(file_handler)
    root_logger.info("Set logging to %s", log_file_path)
    
    # 4) Optionally create or retrieve a named logger
    logger = logging.getLogger("main")
    logger.info("Finished configuring logging (no console output).")

    return logger

def _init_luna_ram():
    """
    Loads the config.yaml file at startup and populates GLOBAL_PARAMS
    with any keys found under 'globals:'.
    This ensures your in-memory parameters are up-to-date before the bot runs.
    Also logs aggregate statistics about how many variables were loaded,
    how many were blank, etc., and outputs comma-separated variable names.
    """
    g.LOGGER.info("Initializing global parameters from config.yaml...")
    cfg = _load_config()

    globals_section = cfg.get("globals", {})
    total_keys = len(globals_section)

    blank_vars = []
    nonblank_vars = []

    for key, value in globals_section.items():
        # Define "blank" as None, empty string, or empty container
        is_blank = False
        if value is None:
            is_blank = True
        elif isinstance(value, str) and value.strip() == "":
            is_blank = True
        elif isinstance(value, (list, dict)) and len(value) == 0:
            is_blank = True

        if is_blank:
            blank_vars.append(key)
        else:
            nonblank_vars.append(key)

        # Store in GLOBAL_PARAMS
        g.GLOBAL_PARAMS[key] = value

    # Prepare comma-separated lists
    nonblank_list = ", ".join(nonblank_vars)
    blank_list = ", ".join(blank_vars)

    # Count them
    nonblank_count = len(nonblank_vars)
    blank_count = len(blank_vars)

    # Log final stats
    g.LOGGER.info(
        "Global parameters initialized: %d total, %d non-blank, %d blank.",
        total_keys, nonblank_count, blank_count
    )
    g.LOGGER.info("Non-blank variables: %s", nonblank_list if nonblank_list else "(none)")
    g.LOGGER.info("Blank variables: %s", blank_list if blank_list else "(none)")

def _load_config() -> dict:
    """
    Loads the YAML config from disk into a dict.
    Returns an empty dict if file not found or invalid.
    """
    if not os.path.exists(g.CONFIG_PATH):
        return {}
    with open(g.CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

async def _login_matrix_client(
    homeserver_url: str,
    user_id: str,
    password: str,
    device_name: str = "BotDevice"
) -> AsyncClient:
    """
    login_client

    A simplified function that logs in a Matrix user via password each time,
    returning a ready-to-use AsyncClient. No tokens are stored or reused.

    Args:
      homeserver_url: Your Synapse server address, e.g. "http://localhost:8008"
      user_id: A full Matrix user ID (e.g. "@inky:localhost") or localpart if you prefer
      password: The account's password.
      device_name: A label for the login session.

    Returns:
      An AsyncClient logged in as `user_id`. If login fails, raises Exception.
    """

    # If the caller passed only the local part (like "inky"), you might want to ensure:
    #   if not user_id.startswith("@"):
    #       user_id = f"@{user_id}:localhost"
    # But that depends on your usage.

    g.LOGGER.debug(f"Logging in Bot [{user_id}]. STARTED")
    client = AsyncClient(homeserver=homeserver_url, user=user_id)
    resp = await client.login(password=password, device_name=device_name)

    if isinstance(resp, LoginResponse):
        g.LOGGER.debug(f"Logging in Bot [{user_id}]. COMPLETE. user_id={client.user_id}")
        return client
    else:
        g.LOGGER.error(f"Logging in Bot [{user_id}]. FAILED. user_id={client.user_id}")
        raise Exception(f"Password login failed for {user_id}: {resp}")

async def _run_bot_sync(bot_client: AsyncClient, localpart: str):
    """
    Simple sync loop for each bot, runs until SHOULD_SHUT_DOWN is True.
    """
    while not g.SHOULD_SHUT_DOWN:
        try:
            await bot_client.sync(timeout=5000)
        except Exception as e:
            g.LOGGER.exception(
                f"Bot '{localpart}' had sync error: {e}"
            )
            await asyncio.sleep(2)  # brief backoff
        else:
            # If no error, give control to other tasks
            await asyncio.sleep(0)

async def _async_console_input(prompt: str = "") -> str:
    """
    Uses run_in_executor to perform blocking input() in a thread,
    returning the user-entered string without blocking the main event loop.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, input, prompt)

def _make_message_callback(bot_client, localpart):
    """
    Returns a function that references exactly these arguments,
    intended for handling normal room messages for a non-Luna bot.
    """
    async def on_message(room, event):
        await handle_bot_room_message(bot_client, localpart, room, event)
    return on_message

def _make_invite_callback(bot_client, localpart):
    """
    Returns a function to handle invites for a non-Luna bot.
    """
    async def on_invite(room, event):
        await handle_bot_invite(bot_client, localpart, room, event)
    return on_invite

def _make_member_callback(bot_client, localpart):
    """
    Returns a function to handle membership changes for a non-Luna bot.
    """
    async def on_member(room, event):
        await handle_bot_member_event(bot_client, localpart, room, event)
    return on_member

async def _console_loop():
    """
    Async loop to read user input from the console in parallel to the matrix sync loop.
    If the user types 'exit', we'll set g.SHOULD_SHUT_DOWN to True and exit gracefully.
    """
    loop = asyncio.get_event_loop()
    while not g.SHOULD_SHUT_DOWN:
        # Offload blocking input() call to a thread executor
        user_input = await loop.run_in_executor(None, input, "Enter command (or 'exit'): ")

        if user_input.strip().lower() == "exit":
            g.LOGGER.info("User requested shutdown via console command.")
            g.SHOULD_SHUT_DOWN = True
            break
        else:
            g.LOGGER.info(f"Received console command: {user_input.strip()}")
            # Optionally: handle other console commands here if you want


async def _matrix_sync_loop(luna_client: AsyncClient):
    """
    A dedicated task for the matrix sync. We keep calling sync_forever or a custom
    sync loop until g.SHOULD_SHUT_DOWN is True, at which point we gracefully close.
    """
    try:
        # This is an example using the typical nio sync loop:
        # For a more controlled approach, you might implement
        # your own sync loop with a while-not-SHOULD_SHUT_DOWN check.
        g.LOGGER.info("Starting matrix sync loop...")
        await luna_client.sync_forever(timeout=30000, full_state=True)
    except Exception as e:
        g.LOGGER.error(f"Exception in matrix sync loop: {e}")
    finally:
        g.LOGGER.info("Matrix sync loop terminating. Attempting graceful client shutdown.")
        if luna_client:
            await luna_client.close()



if __name__ == "__main__":
    asyncio.run(main())
