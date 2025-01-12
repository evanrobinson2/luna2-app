import os
import sys
import logging
import subprocess
import asyncio
import aiohttp
from datetime import datetime
import textwrap # or however you import from the same package
from nio import AsyncClient
from asyncio import CancelledError
import json
from src.luna_command_extensions.cmd_shutdown import request_shutdown
from . import luna_personas
from . import luna_functions
from nio.api import RoomVisibility
from src.luna_command_extensions.ascii_art import show_ascii_banner
from src.luna_command_extensions.luna_functions_assemble import cmd_assemble
from src.luna_functions import DIRECTOR_CLIENT
import asyncio
from src.luna_functions_create_room import create_room
from src.luna_command_extensions.console_functions_cmd_summarize_room import cmd_summarize_room

logger = logging.getLogger(__name__)

########################################################
# 1) COMMAND HANDLER FUNCTIONS
########################################################
def cmd_banner(args, loop):
    print ("\n" + show_ascii_banner("Luna Bot"))

def cmd_help(args, loop):
    """
    Usage: help

    Show usage for all known commands in a more readable multi-line format.
    """
    logger.debug("Showing help to user.")
    print("SYSTEM: Available commands:\n")

    # A small utility to wrap text nicely at ~70 characters, for readability.
    wrapper = textwrap.TextWrapper(width=70, subsequent_indent="    ")

    for cmd_name, cmd_func in COMMAND_ROUTER.items():
        doc = (cmd_func.__doc__ or "").strip()
        if not doc:
            usage_line = f"(No usage info for `{cmd_name}`)"
            description = ""
        else:
            # Split docstring lines
            lines = doc.splitlines()
            usage_line = ""
            description = ""

            # We assume first line is "Usage:", subsequent lines are description
            if lines:
                first_line = lines[0].strip()
                if first_line.startswith("Usage:"):
                    usage_line = first_line
                    # Join the rest as the description
                    if len(lines) > 1:
                        description = " ".join(l.strip() for l in lines[1:] if l.strip())
                else:
                    # If we didn't find "Usage:" up front, treat everything as description
                    usage_line = "(No usage line found.)"
                    description = " ".join(l.strip() for l in lines if l.strip())

        # Wrap the usage and description
        usage_line_wrapped = wrapper.fill(usage_line)
        description_wrapped = wrapper.fill(description)

        print(f"{cmd_name}\n  {usage_line_wrapped}")
        if description_wrapped:
            print(f"  {description_wrapped}")
        print()  # blank line after each command

def cmd_exit(args, loop):
    """
    Usage: exit

    Gracefully shuts down Luna by setting the shutdown flag
    and stopping the main loop.
    """
    logger.info("Console received 'exit' command; requesting shutdown.")
    print("SYSTEM: Shutting down Luna gracefully...")    
    request_shutdown()



def cmd_restart(args, loop):
    """
    Usage: restart

    Kills and relaunches the process with the same arguments.
    """
    logger.info("Console received 'restart' command; restarting now.")
    print("SYSTEM: Attempting to restart the entire process...")

    python_executable = sys.executable
    script = sys.argv[0]
    extra_args = sys.argv[1:]

    # This call does not return if successful
    os.execl(python_executable, python_executable, script, *extra_args)

def cmd_log(args, loop):
    """
    Usage: log

    Displays the log file path and helpful note about logs.
    """
    LOGFILE_PATH = "server.log"  # or read from a config
    print(f"SYSTEM: Log file is located at: {LOGFILE_PATH}\n"
          "SYSTEM: Check that file for all logs, since console output is minimized or disabled.")

def cmd_who(args, loop):
    """
    Usage: who

    Shows the current director's user ID if any.
    """
    # Typically you'd do something like:
    # from src.luna_functions import get_director
    # director = get_director()
    # but let's pretend we do that inline for demonstration:

    # Mock example:
    from src.luna_functions import DIRECTOR_CLIENT
    if DIRECTOR_CLIENT:
        print(f"SYSTEM: Director is => {DIRECTOR_CLIENT.user}")
    else:
        print("SYSTEM: No Director Found")

def cmd_clear(args, loop):
    """
    Usage: clear

    Clears the console screen.
    """
    if os.name == 'nt':
        os.system('cls')
    else:
        os.system('clear')
    logger.info("Console screen cleared.")

def cmd_autojoin(args, loop):
    """
    Usage: autojoin <enable|disable>

    If <enable> or <disable> is given, toggles automatic joining of new invited rooms.
    If no argument is provided, shows the current auto-join status.
    If an invalid argument is given, displays usage and also shows the current status.
    """
    from src.luna_functions import set_auto_join, get_auto_join_enabled

    choice = args.strip().lower()

    # (A) No argument => show current status
    if not choice:
        current = "ENABLED" if get_auto_join_enabled() else "DISABLED"
        print(f"SYSTEM: Auto-join is currently {current}.")
        return

    # (B) Check for valid arguments
    if choice not in ("enable", "disable"):
        current = "ENABLED" if get_auto_join_enabled() else "DISABLED"
        print("SYSTEM: Usage: autojoin <enable|disable>")
        print(f"SYSTEM: Auto-join is currently {current}.")
        return

    # (C) If valid, set auto-join state and confirm
    enable_flag = (choice == "enable")
    set_auto_join(enable_flag)
    state_word = "ENABLED" if enable_flag else "DISABLED"
    print(f"SYSTEM: Auto-join is now {state_word}.")

def cmd_rotate_logs(args, loop):
    """
    Usage: rotate_logs

    Renames 'server.log' to a timestamped file (e.g. server-20250105-193045.log),
    then reinitializes the logger so the new logs go into the fresh file.
    """
    logger.info("Rotating logs...")

    # 1) Rotate the current file
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = "data/server.log"
    rotated_file = f"data/logs/server-{timestamp}.log"

    if os.path.exists(log_file):
        try:
            os.rename(log_file, rotated_file)
            print(f"SYSTEM: Rotated {log_file} -> {rotated_file}")
        except Exception as e:
            print(f"SYSTEM: Error rotating logs: {e}")
            return
    else:
        print("SYSTEM: No server.log found to rotate.")

    # 2) Create a fresh server.log
    try:
        with open(log_file, "w") as f:
            pass
        print("SYSTEM: New server.log created.")
    except Exception as e:
        print(f"SYSTEM: Error creating new server.log: {e}")

    # 3) Re-init logging so future logs go into the new file
    #    (Close the old handler, create a new FileHandler, attach it, etc.)

    root_logger = logging.getLogger()
    # Remove old file handlers
    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)
            handler.close()
    # Create a new file handler for "server.log"
    new_handler = logging.FileHandler(log_file)
    new_handler.setLevel(logging.DEBUG)  # match your preferred level
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    new_handler.setFormatter(formatter)
    root_logger.addHandler(new_handler)

    logger.info(f"Log rotation complete. Logging to {log_file} again.")
    print(f"SYSTEM: Logging has been reinitialized to {log_file}.")

def cmd_purge_and_seed(args, loop):
    """
    Usage: purge_and_seed

    1) Prompt user to shut down Synapse (type 'confirm' when done).
    2) Remove 'homeserver.db' + local store files (CSV, sync_token.json, director_token.json).
    3) Prompt user to start server again (type 'confirm').
    4) Re-register admin/lunabot accounts on the freshly started server.
    5) Prompt user to confirm if they'd like to restart Luna, which calls cmd_restart.

    This is a destructive operation. Press any key to continue.
    """
    print ("SYSTEM> DOES NOTHING NOW. 'rm /Users/evanrobinson/Documents/Luna2/matrix/homeserver.db'")
    print ("STOP THE SERVER FIRST")

########################################################
# NEW COMMAND HANDLER
########################################################
def cmd_check_limit(args, loop):
    """
    Usage: check-limit

    Makes a single short sync request to see if we get rate-limited (HTTP 429).
    Blocks until the request completes, then prints the result.
    """
    logger.info("Console received 'check-limit' command. Blocking until result is returned...")

    try:
        # run_coroutine_threadsafe returns a Future, then .result() blocks
        # this background thread (the console thread) until the coroutine finishes.
        result_msg = asyncio.run_coroutine_threadsafe(
            luna_functions.check_rate_limit(),
            loop
        ).result()

        # Now we have the final string from check_rate_limit()
        print(f"SYSTEM: {result_msg}")

    except Exception as e:
        logger.exception(f"Error in check-limit: {e}")
        print(f"SYSTEM: Error in check-limit: {e}")



def cmd_check_limit_dep(args, loop):
    """
    Usage: check-matrix

    Makes a single request to the Matrix server to see if we get rate-limited (HTTP 429).
    If it returns 200, you're good. If 429, you're being throttled. Otherwise, see logs.
    """
    logger.info("Console received 'check-limit' command. Checking for rate-limit...")

    future = asyncio.run_coroutine_threadsafe(
        luna_functions.check_rate_limit(),
        loop
    )

    def on_done(fut):
        try:
            result_msg = fut.result()
            print(f"SYSTEM: {result_msg}")
        except Exception as e:
            logger.exception(f"Error in check-limit: {e}")
            print(f"SYSTEM: Error in check-limit: {e}")

    future.add_done_callback(on_done)

def cmd_fetch_all(args, loop):
    """
    Usage: fetch_all

    Fetch all historical messages from all joined rooms in pages, 
    storing them in a CSV. This might take a while if rooms are large.
    """
    logger.info("Console received 'fetch_all' command. Blocking until done...")

    future = asyncio.run_coroutine_threadsafe(
        luna_functions.fetch_all_messages_once(
            luna_functions.DIRECTOR_CLIENT,
            room_ids=None,       # or specify a list of specific room IDs
            page_size=100
        ),
        loop
    )

    def on_done(fut):
        try:
            fut.result()
            print("SYSTEM: Successfully fetched all historical messages.")
        except Exception as e:
            logger.exception(f"Error in fetch_all: {e}")
            print(f"SYSTEM: Error in fetch_all: {e}")

    future.add_done_callback(on_done)


def cmd_fetch_new(args, loop):
    """
    Usage: fetch_new

    Incremental fetch: only retrieves events since the last sync token,
    appending them to the CSV.
    """
    logger.info("Console received 'fetch_new' command. Blocking until done...")

    future = asyncio.run_coroutine_threadsafe(
        luna_functions.fetch_all_new_messages(
            luna_functions.DIRECTOR_CLIENT
        ),
        loop
    )

    def on_done(fut):
        try:
            fut.result()
            print("SYSTEM: Successfully fetched new messages.")
        except Exception as e:
            logger.exception(f"Error in fetch_new: {e}")
            print(f"SYSTEM: Error in fetch_new: {e}")

    future.add_done_callback(on_done)


def cmd_create_user(args, loop):
    """
    Usage: create_user <username> <password> [--admin]

    Example:
      create_user alice supersecret
      create_user bob mypass --admin

    Parses console arguments, then calls `luna.create_user(...)`.
    The actual user creation is handled entirely in Luna.
    """
    parts = args.strip().split()
    if len(parts) < 2:
        print("Usage: create_user <username> <password> [--admin]")
        return

    username, password = parts[:2]
    is_admin = False

    # If the third argument is "--admin", set admin flag
    if len(parts) > 2 and parts[2].lower() == "--admin":
        is_admin = True

    # Schedule the async call to Luna's create_user(...)
    future = asyncio.run_coroutine_threadsafe(
    luna_functions.create_user(username, password, is_admin),
        loop
    )

    def on_done(fut):
        try:
            result = fut.result()
            print(result)  # e.g. "Created user @alice:localhost (admin=True)." or an error message
        except Exception as e:
            print(f"Error while creating user '{username}': {e}")
            logger.exception("Exception in cmd_create_user callback.")

    future.add_done_callback(on_done)

    print(f"SYSTEM: Asking Luna to create user '{username}' (admin={is_admin})...")


def cmd_show_shutdown(args, loop):
    """
    Usage: show_shutdown

    Prints the current value of SHOULD_SHUT_DOWN (a boolean).
    """
    from cmd_shutdown import SHOULD_SHUT_DOWN
    print(f"SYSTEM: SHOULD_SHUT_DOWN is currently set to {SHOULD_SHUT_DOWN}.")


def cmd_list_rooms(args, loop):
    """
    Usage: list_rooms [--json]

    Fetches a list of rooms (name, ID, participant count, etc.) from the director client.
    If you provide '--json', it will print the output as JSON instead of a table.
    """
    # 1) Check if the user wants JSON output
    parts = args.strip().split()
    json_flag = ("--json" in parts)

    # 2) Schedule the async call to list_rooms and wait for its result
    try:
        rooms_info = asyncio.run_coroutine_threadsafe(
            luna_functions.list_rooms(),
            loop
        ).result()  # <-- This will block until the coroutine completes

        if not rooms_info:
            print("SYSTEM: No rooms found or DIRECTOR_CLIENT is not ready.")
            return

        # 3) Output the result
        if json_flag:
            # Print as JSON
            print(json.dumps(rooms_info, indent=2))
        else:
            # Print a formatted table
            _print_rooms_table(rooms_info)

    except Exception as e:
        logger.exception(f"Exception in cmd_list_rooms: {e}")
        print(f"SYSTEM: Error listing rooms: {e}")

def _print_rooms_table(rooms_info: list[dict]):
    """
    Helper function to print a nice table of rooms:
      NAME (up to ~30 chars)  | ROOM ID (up to ~35 chars) | COUNT (5 chars) | PARTICIPANTS
    """
    # Build a header line with fixed-width columns
    header = f"{'NAME':30} | {'ROOM ID':35} | {'COUNT':5} | PARTICIPANTS"
    print(header)
    print("-" * 105)  # or 90, depending on how wide you like

    for room in rooms_info:
        name = (room['name'] or "(unnamed)")[:30]
        room_id = room['room_id']
        count = room['joined_members_count']
        participants_str = ", ".join(room['participants'])

        # Format each row to match the header widths
        row = f"{name:30} | {room_id:35} | {count:5} | {participants_str}"
        print(row)

def cmd_list_users(args, loop):
    """
    Usage: list_users [--json]

    Fetches a list of users from the Synapse server,
    prints them in a table or JSON, then returns control to the console.
    """
    parts = args.strip().split()
    json_flag = ("--json" in parts)

    try:
        # Directly block the console thread until the future completes
        users_info = asyncio.run_coroutine_threadsafe(
            luna_functions.list_users(), loop
        ).result(timeout=10)  # optional timeout in seconds

        if not users_info:
            print("SYSTEM: No users found or we failed to query the server.")
            return

        if json_flag:
            # Print as JSON
            print(json.dumps(users_info, indent=2))
        else:
            _print_users_table(users_info)

    except Exception as e:
        logger.exception(f"Exception in cmd_list_users: {e}")
        print(f"SYSTEM: Error listing users: {e}")


def _print_users_table(users_info: list[dict]):
    """
    Helper function to print a table of user data:
      USER ID (up to ~25 chars) | ADMIN | DEACT | DISPLAYNAME
    """
    header = f"{'USER ID':25} | {'ADMIN':5} | {'DEACT'} | DISPLAYNAME"
    print(header)
    print("-" * 70)

    for user in users_info:
        user_id = (user['user_id'] or "")[:25]
        admin_str = "Yes" if user.get("admin") else "No"
        deact_str = "Yes" if user.get("deactivated") else "No"
        display = user.get("displayname") or ""

        row = f"{user_id:25} | {admin_str:5} | {deact_str:5} | {display}"
        print(row)

def cmd_invite_user(args, loop):
    """
    Usage: invite_user <user_id> <room_id>

    Example:
      invite_user @bob:localhost !testRoom:localhost

    Invites (actually forces) a user to join the given room using the director client.
    Unlike normal invites, this bypasses user consent by calling the Synapse Admin API.
    Requires that the user running Luna has admin privileges on the homeserver.
    """
    parts = args.strip().split()
    if len(parts) < 2:
        print("SYSTEM: Usage: invite_user <user_id> <room_id>")
        return

    user_id = parts[0]
    room_id = parts[1]

    # We'll define the forced-join logic inside this command function, so there's no helper function.
    async def do_force_join(user: str, room: str) -> str:
        """
        Asynchronous subroutine to forcibly join 'user' to 'room'
        via Synapse Admin API, using the same token as DIRECTOR_CLIENT.
        """
        client = luna_functions.getClient()
        if not client:
            return "Error: No DIRECTOR_CLIENT set."

        admin_token = client.access_token
        if not admin_token:
            return "Error: No admin token is present in DIRECTOR_CLIENT."

        # The base homeserver URL (e.g. "http://localhost:8008"); adjust if needed.
        homeserver_url = client.homeserver

        # Synapse Admin endpoint for forcing a user into a room:
        # PUT /_synapse/admin/v1/rooms/{roomIdOrAlias}/join?user_id=@someone:domain
        endpoint = f"{homeserver_url}/_synapse/admin/v1/rooms/{room}/join"
        params = {"user_id": user}
        headers = {"Authorization": f"Bearer {admin_token}"}

        logger.debug("Forcing %s to join %s via %s", user, room, endpoint)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(endpoint, headers=headers, params=params) as resp:
                    if resp.status in (200, 201):
                        return f"Forcibly joined {user} to {room}."
                    else:
                        text = await resp.text()
                        return f"Error {resp.status} forcibly joining {user} => {text}"
        except Exception as e:
            logger.exception("Exception in do_force_join:")
            return f"Exception forcibly joining user => {e}"

    # Schedule our async forced-join subroutine on the existing event loop:
    future = asyncio.run_coroutine_threadsafe(do_force_join(user_id, room_id), loop)

    def on_done(fut):
        try:
            result_msg = fut.result()
            print(f"SYSTEM: {result_msg}")
        except Exception as e:
            logger.exception(f"Exception in cmd_invite_user callback: {e}")
            print(f"SYSTEM: Error forcibly inviting user: {e}")

    future.add_done_callback(on_done)
    print(f"SYSTEM: Inviting {user_id} to {room_id}... Please wait.")

def cmd_add_user(args, loop):
    """
    Usage: add_user <user_id> <room_id_or_alias>

    Example:
      add_user @bob:localhost !testRoom:localhost
      add_user @spyclops:localhost #mychannel:localhost

    This console command force-joins a user to the given room or alias,
    bypassing normal invite acceptance. It calls the Synapse Admin API
    `POST /_synapse/admin/v1/join/<room_id_or_alias>` with a JSON body:
    {
      "user_id": "@bob:localhost"
    }

    Requires that the user running this command (Luna's director)
    is an admin on the homeserver and already has power to invite in the room.
    """

    parts = args.strip().split()
    if len(parts) < 2:
        print("SYSTEM: Usage: add_user <user_id> <room_id_or_alias>")
        return

    user_id = parts[0]
    room_id_or_alias = parts[1]

    async def do_force_join(user: str, room: str) -> str:
        """
        Asynchronous subroutine to forcibly join 'user' to 'room'
        via Synapse Admin API, using the same token as DIRECTOR_CLIENT.
        """
        client = luna_functions.getClient()
        if not client:
            return "Error: No DIRECTOR_CLIENT set."

        admin_token = client.access_token
        if not admin_token:
            return "Error: No admin token is present in DIRECTOR_CLIENT."

        # The base homeserver URL (e.g., "http://localhost:8008")
        homeserver_url = client.homeserver

        # Synapse Admin API endpoint for forcing a user into a room:
        # POST /_synapse/admin/v1/join/<room_id_or_alias>
        # JSON body: { "user_id": "@someone:localhost" }
        endpoint = f"{homeserver_url}/_synapse/admin/v1/join/{room}"
        headers = {"Authorization": f"Bearer {admin_token}"}
        payload = {"user_id": user}

        logger.debug("Forcing %s to join %s via %s", user, room, endpoint)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, headers=headers, json=payload) as resp:
                    if resp.status in (200, 201):
                        return f"Forcibly joined {user} to {room}."
                    else:
                        text = await resp.text()
                        return f"Error {resp.status} forcibly joining {user} => {text}"
        except Exception as e:
            logger.exception("Exception in do_force_join:")
            return f"Exception forcibly joining user => {e}"

    # Schedule our async forced-join subroutine on the existing event loop:
    future = asyncio.run_coroutine_threadsafe(do_force_join(user_id, room_id_or_alias), loop)

    def on_done(fut):
        try:
            result_msg = fut.result()
            print(f"SYSTEM: {result_msg}")
        except Exception as e:
            logger.exception(f"Exception in cmd_add_user callback: {e}")
            print(f"SYSTEM: Error forcibly adding user: {e}")

    future.add_done_callback(on_done)
    print(f"SYSTEM: Force-joining {user_id} to {room_id_or_alias}... Please wait.")

def cmd_create_bot_user(args, loop):
    """
    Usage:
      create_bot '{"localpart": "...", "displayname": "...", "system_prompt": "...", "password": "...", "traits": {...}}'
    """

    # 1. Check if there's any input at all
    if not args.strip():
        print("SYSTEM: No input provided. Please provide a valid JSON payload.")
        return

    # 2. Parse as JSON
    try:
        data = json.loads(args)
    except json.JSONDecodeError as e:
        print(f"SYSTEM: Invalid JSON: {e}")
        return

    # 3. Extract fields
    localpart = data.get("localpart")
    displayname = data.get("displayname")
    system_prompt = data.get("system_prompt")
    password = data.get("password")
    traits = data.get("traits", {})

    # 4. Validate required fields
    missing_fields = []
    if not localpart:
        missing_fields.append("localpart")
    if not displayname:
        missing_fields.append("displayname")
    if not system_prompt:
        missing_fields.append("system_prompt")
    if not password:
        missing_fields.append("password")

    if missing_fields:
        print(f"SYSTEM: Missing required fields: {', '.join(missing_fields)}")
        return

    # 5. Construct bot_id
    bot_id = f"@{localpart}:localhost"

    # 6. Create local persona
    try:
        persona = luna_personas.create_bot(
            bot_id=bot_id,
            password=password,
            displayname=displayname,
            creator_user_id="@lunabot:localhost",
            system_prompt=system_prompt,
            traits=traits
        )
        print(f"SYSTEM: Local persona created => {persona}")
    except ValueError as ve:
        print(f"SYSTEM: Error creating persona: {ve}")
        return
    except Exception as e:
        print(f"SYSTEM: Unexpected error => {e}")
        return

    # 7. Register user with Synapse (async call)
    from src.luna_functions import create_user as matrix_create_user
    fut = asyncio.run_coroutine_threadsafe(
        matrix_create_user(localpart, password, is_admin=False),
        loop
    )

    try:
        result_msg = fut.result()
        print(f"SYSTEM: Matrix user creation => {result_msg}")
    except Exception as e:
        print(f"SYSTEM: Error creating matrix user => {e}")

def cmd_list_server(args, loop):
    """
    Usage: cmd_list_server

    Example:
      list_server

    Steps:
    1) Lists the server's rooms along with summary information
    2) Lists the server's users    
    """
    
    cmd_list_rooms(args, loop)
    print("\n")
    cmd_list_users(args, loop)
    

def cmd_delete_bot(args, loop):
    """
    Usage: delete_bot <bot_localpart>

    Example:
      delete_bot jamiebot

    Steps:
    1) Remove the local persona entry from personalities.json.
    2) Delete the Matrix user @jamiebot:localhost from the server via admin API.
    """

    parts = args.strip().split()
    if len(parts) < 1:
        print("SYSTEM: Usage: delete_bot <bot_localpart>")
        return

    localpart = parts[0].lower()
    bot_id = f"@{localpart}:localhost"

    # Step A: Delete local persona from personalities.json
    try:
        from luna_functions import delete_bot_persona
        delete_bot_persona(bot_id)  
        print(f"SYSTEM: Successfully removed persona record for {bot_id}")
    except FileNotFoundError:
        print("SYSTEM: personalities.json not found; skipping local removal.")
    except KeyError as ke:
        print(f"SYSTEM: {ke}")
    except Exception as e:
        print(f"SYSTEM: Unexpected error removing {bot_id} from local store: {e}")
        return

    # Step B: Delete user from Synapse
    from src.luna_functions import delete_matrix_user
    future = asyncio.run_coroutine_threadsafe(
        delete_matrix_user(localpart),
        loop
    )

    def on_done(fut):
        try:
            result_msg = fut.result()
            print(f"SYSTEM: {result_msg}")
        except Exception as e:
            print(f"SYSTEM: Error deleting Matrix user {bot_id}: {e}")

    future.add_done_callback(on_done)
    
    
# Suppose in luna_functions_create_inspired_bot.py you have:
def cmd_create_room(args, loop):
    """
    Usage: create_room <roomName> [--private]

    Examples:
      create_room2 MyConferenceRoom
      create_room2 MyPrivateRoom --private

    Steps:
    1) Parse the arguments to identify the desired room name and determine whether
       the user wants a public room (default) or a private one (if --private is present).
    2) If no room name is provided, print a usage message and return.
    3) Convert the user's input into 'room_name' (string) and 'is_public' (bool).
    4) Schedule the `create_room_luna(room_name, is_public)` coroutine on the event loop,
       then block until the result is returned.
    5) Print the outcome message (room created successfully or an error).
    """
    logging.info("Received create_room_luna command.")
    parts = args.strip().split()
    if not parts:
        print("Usage: create_room <roomName> [--private]")
        return

    room_name = parts[0]
    is_public = True
    if "--private" in parts[1:]:
        is_public = False

    logging.info("Calling luna_functions.create_room.")
    future = asyncio.run_coroutine_threadsafe(create_room(room_name, is_public), loop)
    try:
        result_msg = future.result()
        print(f"SYSTEM: {result_msg}")
    except Exception as e:
        print(f"SYSTEM: Exception while creating room => {e}")


def cmd_create_inspired_bot(args, loop):
    """
    A simple wrapper function that delegates to the real cmd_create_inspired_bot()
    in luna_functions_create_inspired_bot.py.
    """
    print("Attempting to create an inspired bot")

    # Import inside the function to avoid potential circular imports
    from src.luna_functions_create_inspired_bot import cmd_create_inspired_bot
    # Call the imported function
    return cmd_create_inspired_bot(args, loop)


########################################################
# THE COMMAND ROUTER DICTIONARY
########################################################

COMMAND_ROUTER = {
    # System or meta-commands
    "help": cmd_help,
    "exit": cmd_exit,
    "restart": cmd_restart,
    "log": cmd_log,
    "autojoin": cmd_autojoin,
    "rotate_logs": cmd_rotate_logs,
    "check_matrix": cmd_check_limit,
    "show_shutdown":cmd_show_shutdown,
    "who": cmd_who,
    "clear": cmd_clear,
    "purge_and_seed": cmd_purge_and_seed,
    
    "banner": cmd_banner,

    "create_room": cmd_create_room,
    "create_bot": cmd_create_bot_user,

    "fetch_all": cmd_fetch_all,
    "fetch_new": cmd_fetch_new,

    "list_users": cmd_list_users,
    "list_channels": cmd_list_rooms,
    "list_server": cmd_list_server,
    "server": cmd_list_server,

    "invite_user": cmd_invite_user,
    "add_user_to_channel":cmd_add_user,
    "summarize_room": cmd_summarize_room,
    "summon_random":cmd_create_inspired_bot,
    "assemble": cmd_assemble
}