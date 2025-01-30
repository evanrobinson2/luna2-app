#!/usr/bin/env python3
"""
run_luna_lang.py

Main entry point for Luna. Largely the same as your snippet:
 - sets up logging
 - loads config & .env
 - logs in to Matrix
 - spawns ephemeral bots
 - attaches event callbacks
 - runs matrix & console loops in parallel
 - builds a minimal graph (we'll do that in the second file now)
"""

import os
import psutil
import sys
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

# If you're using ChatOpenAI directly:
from langchain_openai import ChatOpenAI
from langchain.schema import AIMessage, HumanMessage

# We'll use your global references
import luna.GLOBALS as g

# Matrix bot extension handlers
from luna.luna_command_extensions.bot_message_handler import handle_bot_room_message
from luna.luna_command_extensions.bot_invite_handler import handle_bot_invite
from luna.luna_command_extensions.bot_member_event_handler import handle_bot_member_event
from luna.luna_lang_router import build_router_graph

# We now import our new advanced router approach from "luna_lanrouter"
from luna.luna_lang_router import handle_luna_message  # new advanced version

# Database & ASCII art
from luna.bot_messages_store import load_messages
from luna.luna_command_extensions.ascii_art import show_ascii_banner

import asyncio
import logging
from nio import RoomMessageText

def _configure_logging():
    """
    Configures Python logging to remove console logs and only log to server.log
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # remove existing handlers
    while root_logger.handlers:
        root_logger.removeHandler(root_logger.handlers[0])

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(funcName)s: %(message)s"
    )

    os.makedirs("data/logs", exist_ok=True)
    log_file_path = "data/logs/server.log"

    file_handler = logging.FileHandler(log_file_path, mode="a")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    root_logger.info("Set logging to %s", log_file_path)

    logger = logging.getLogger("main")
    logger.info("Finished configuring logging (no console output).")

    return logger

def _load_config() -> dict:
    """
    Load configuration from YAML file into the global `g.CONFIG` dictionary.
    If the file does not exist or is malformed, it returns an empty dictionary.
    """
    if not os.path.exists(g.CONFIG_PATH):
        g.LOGGER.warning(f"Config file not found: {g.CONFIG_PATH}")
        return {}

    try:
        with open(g.CONFIG_PATH, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}  # Ensure it always returns a dict
    except yaml.YAMLError as e:
        g.LOGGER.error(f"Error parsing YAML config: {e}")
        return {}

    g.CONFIG = config_data  # Explicitly update the global config
    return g.CONFIG  # Return the loaded config for optional use
    
    

def _init_luna_ram():
    """
    Reads config.yaml, populates g.GLOBAL_PARAMS, logs results.
    """
    g.LOGGER.info("Initializing global parameters from config.yaml...")
    
    globals_section = g.CONFIG.get("globals", {})
    total_keys = len(globals_section)

    blank_vars = []
    nonblank_vars = []

    for key, value in globals_section.items():
        # define "blank"
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

        g.GLOBAL_PARAMS[key] = value

    # log final
    nonblank_list = ", ".join(nonblank_vars)
    blank_list = ", ".join(blank_vars)
    nb_count = len(nonblank_vars)
    b_count = len(blank_vars)

    g.LOGGER.info(
        "Global parameters initialized: %d total, %d non-blank, %d blank.",
        total_keys, nb_count, b_count
    )
    g.LOGGER.info("Non-blank variables: %s", nonblank_list if nonblank_list else "(none)")
    g.LOGGER.info("Blank variables: %s", blank_list if blank_list else "(none)")

async def _login_matrix_client(
    homeserver_url: str,
    user_id: str,
    password: str,
    device_name: str="BotDevice"
) -> AsyncClient:
    """
    Minimal ephemeral login. no token reuse
    """
    g.LOGGER.debug(f"Logging in Bot [{user_id}]. STARTED")
    client = AsyncClient(homeserver=homeserver_url, user=user_id)
    resp = await client.login(password=password, device_name=device_name)
    from nio import LoginResponse
    if isinstance(resp, LoginResponse):
        g.LOGGER.debug(f"Logging in Bot [{user_id}]. COMPLETE. user_id={client.user_id}")
        return client
    else:
        g.LOGGER.error(f"Logging in Bot [{user_id}]. FAILED. user_id={client.user_id}")
        raise Exception(f"Password login failed for {user_id}: {resp}")

async def _login_all_bots(personalities_file, BOTS):
    """
    ephemeral login for each bot in personalities.json
    """
    import time
    start_time = time.monotonic()

    if not os.path.exists(personalities_file):
        g.LOGGER.error(f"Bot login file not found: {personalities_file}")
        return {}

    with open(personalities_file, "r", encoding="utf-8") as f:
        personalities_data = json.load(f)

    skipped_bots = []
    success_bots = []
    fail_bots = []
    homeserver_url = g.HOMESERVER_URL

    for user_id, persona in personalities_data.items():
        localpart = user_id.split(":")[0].replace("@","")
        password = persona.get("password", "")
        if not password:
            skipped_bots.append(user_id)
            continue

        try:
            client = await _login_matrix_client(
                homeserver_url, user_id, password, device_name=f"{localpart}_device"
            )
            BOTS[localpart] = client
            success_bots.append(user_id)
        except Exception as e:
            fail_bots.append(user_id)

    total = len(skipped_bots)+len(success_bots)+len(fail_bots)
    g.LOGGER.info(
        f"Bot login results: {total} total, {len(skipped_bots)} skipped, {len(success_bots)} success, {len(fail_bots)} fail"
    )
    g.LOGGER.info("Skipped: %s", ", ".join(skipped_bots) if skipped_bots else "(none)")
    g.LOGGER.info("Success: %s", ", ".join(success_bots) if success_bots else "(none)")
    g.LOGGER.info("Failed: %s", ", ".join(fail_bots) if fail_bots else "(none)")

    end_time = time.monotonic()
    elapsed = end_time - start_time
    g.LOGGER.info("All ephemeral bot logins finished in %.3f seconds.", elapsed)

async def _run_bot_sync(bot_client: AsyncClient, localpart: str):
    """
    sync loop for each ephemeral bot
    """
    while not g.SHOULD_SHUT_DOWN:
        try:
            await bot_client.sync(timeout=5000)
        except Exception as e:
            g.LOGGER.exception(f"Bot '{localpart}' had sync error: {e}")
            await asyncio.sleep(2)
        else:
            await asyncio.sleep(0)

async def _matrix_sync_loop(luna_client: AsyncClient):
    try:
        g.LOGGER.info("Starting matrix sync loop...")
        await luna_client.sync_forever(timeout=30000, full_state=True)
    except Exception as e:
        g.LOGGER.error(f"Exception in matrix sync loop: {e}")
    finally:
        g.LOGGER.info("Matrix sync loop terminating. Attempting graceful client shutdown.")
        if luna_client:
            await luna_client.close()

async def _console_loop():
    """
    parallel console loop
    """
    loop = asyncio.get_event_loop()
    while not g.SHOULD_SHUT_DOWN:
        user_input = await loop.run_in_executor(None, input, "Enter command (or 'exit'): ")
        if user_input.strip().lower() == "exit":
            g.LOGGER.info("User requested shutdown via console command.")
            g.SHOULD_SHUT_DOWN = True
            break
        else:
            g.LOGGER.info("Received console command: %s", user_input.strip())
            # no other commands for now

async def _shutdown_all_bots():
    """
    close ephemeral bots
    """
    for localpart, client in g.BOTS.items():
        try:
            await client.logout()
            await client.close()
        except Exception as e:
            g.LOGGER.exception(f"Failed to logout bot '{localpart}': {e}")
        else:
            g.LOGGER.info(f"Logged out bot '{localpart}'.")

async def main():
    _check_existing_instance()
    g.LOGGER = _configure_logging()

    g.LOGGER.info("----------------------------------------------------")
    g.LOGGER.info(f"Starting up Luna (version {g.LUNA_VERSION})")
    g.LOGGER.info("----------------------------------------------------")

    ########## LOAD ENV
    load_dotenv()
    openai_key = os.getenv("OPENAI_API_KEY","")
    if not openai_key:
        g.LOGGER.error("No OPENAI_API_KEY found. Exiting.")
        return
    g.OPENAI_API_KEY = openai_key

    ## It's good practice to keep the config and global params separate
    ########## LOAD config.yaml
    _load_config()

    ########## LOAD Luna RAM Variables
    _init_luna_ram()

    ########## LOAD messages
    load_messages()

    ########## LOGIN as Luna
    luna_client = await _login_matrix_client(
        g.HOMESERVER_URL, f"@{g.LUNA_USERNAME}:localhost", g.LUNA_PASSWORD
    )

    # attach event callbacks
    luna_client.add_event_callback(
        lambda room, event: handle_luna_message(luna_client, "lunabot", room, event),
        RoomMessageText
    )
    # invites, membership events:
    luna_client.add_event_callback(
        lambda r, e: handle_bot_invite(luna_client, "lunabot", r, e),
        InviteMemberEvent
    )
    luna_client.add_event_callback(
        lambda r, e: handle_bot_member_event(luna_client, "lunabot", r, e),
        RoomMemberEvent
    )

    # ephemeral bots
    asyncio.create_task(_login_all_bots(g.PERSONALITIES_FILE, g.BOTS))

    # Initialize LLM
    from langchain_openai import ChatOpenAI
    g.LLM = ChatOpenAI(
        openai_api_key=g.OPENAI_API_KEY,
        model_name="gpt-4o",
        temperature=0.7
    )

    g.ROUTER_GRAPH =  build_router_graph()

    # clear screen, show ascii banner
    os.system("clear")
    print(show_ascii_banner("LUNA LANG"))

    # start ephemeral bot loops
    tasks = []
    for localpart, bot_client in g.BOTS.items():
        t = asyncio.create_task(_run_bot_sync(bot_client, localpart))
        tasks.append(t)

    # run matrix sync & console loops
    sync_task = asyncio.create_task(_matrix_sync_loop(luna_client))
    console_task = asyncio.create_task(_console_loop())
    done, pending = await asyncio.wait([sync_task, console_task], return_when=asyncio.FIRST_COMPLETED)

    # shutdown
    await luna_client.logout()
    await luna_client.close()
    await _shutdown_all_bots()

    g.LOGGER.info("Shutting down. Bye.")

def _check_existing_instance():
    """
    Prevent multiple instances of Luna from running.
    If an existing PID is found in the lock file and still running, exit.
    """
    if os.path.exists(g.LUNA_LOCK_FILE):
        try:
            with open(g.LUNA_LOCK_FILE, "r") as f:
                existing_pid = int(f.read().strip())

            if psutil.pid_exists(existing_pid):
                print(f"🚨 Luna is already running with PID {existing_pid}. Exiting.")
                sys.exit(1)  # Fatal error
            else:
                print(f"🛑 Stale lock file found (PID {existing_pid} not running). Overwriting.")

        except ValueError:
            print(f"⚠️ Invalid PID found in lock file. Overwriting.")

    # Write the current process PID
    with open(g.LUNA_LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

def _cleanup_lock_file():
    """Remove the lock file when Luna shuts down."""
    if os.path.exists(g.LUNA_LOCK_FILE):
        os.remove(g.LUNA_LOCK_FILE)


if __name__ == "__main__":
    asyncio.run(main())
