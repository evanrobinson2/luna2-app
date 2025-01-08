import os
import sys
import logging
import subprocess
import asyncio
from datetime import datetime
import textwrap # or however you import from the same package
from nio import AsyncClient
from asyncio import CancelledError
import json
from src.cmd_shutdown import request_shutdown
from . import luna_personas
from . import luna_functions
from nio.api import RoomVisibility


logger = logging.getLogger(__name__)

########################################################
# 1) COMMAND HANDLER FUNCTIONS
########################################################
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

def cmd_create_room(args, loop):
    """
    Usage: create_room <roomName>

    Creates a new room named <roomName> using a direct approach:
    1) Loads the director token from `director_token.json`.
    2) Instantiates an AsyncClient with that token.
    3) Schedules `room_create(...)` on the existing event loop with run_coroutine_threadsafe().
    4) Blocks on .result().
    5) Schedules client.close() as well.

    This version includes extensive debugging logs to trace every step.
    """
    logger.debug(f"cmd_create_room called with args='{args}', loop={loop}")

    if not args:
        logger.debug("No args provided. Displaying usage message and returning.")
        print("SYSTEM: Usage: create_room <roomName>")
        return

    room_name = args.strip()
    logger.info(f"SYSTEM: Creating a new room named '{room_name}'...")  # user-facing print

    # Step 1) Load the director token from disk
    logger.debug("Attempting to load token from 'director_token.json'...")
    try:
        with open("director_token.json", "r") as f:
            data = json.load(f)
        user_id = data.get("user_id")
        access_token = data.get("access_token")
        device_id = data.get("device_id")
        logger.debug(f"Loaded token data. user_id={user_id}, access_token=(redacted), device_id={device_id}")
    except Exception as e:
        logger.exception("Error reading 'director_token.json'.")
        print(f"SYSTEM: Error loading director token => {e}")
        return

    # Step 2) Create a local AsyncClient with that token
    from nio import AsyncClient, RoomCreateResponse
    HOMESERVER_URL = "http://localhost:8008"  # Adjust if needed
    logger.debug(f"Creating local AsyncClient for user_id='{user_id}' with homeserver='{HOMESERVER_URL}'")

    client = AsyncClient(homeserver=HOMESERVER_URL, user=user_id)
    client.access_token = access_token
    client.device_id = device_id

    # We'll define a small coroutine to do the room creation
    async def do_create_room():
        """
        Coroutine that calls room_create and returns the response.
        """
        logger.debug(f"do_create_room: about to call room_create(name='{room_name}', visibility='public')")
        try:
            resp = await client.room_create(name=room_name, visibility=RoomVisibility.public,)
            logger.debug(f"do_create_room: room_create call returned {resp}")
            return resp
        except Exception as exc:
            logger.exception("Exception in do_create_room during room_create.")
            raise exc

    # Another small coroutine to close the client
    async def do_close_client():
        logger.debug("do_close_client: closing the AsyncClient.")
        await client.close()
        logger.debug("do_close_client: client closed successfully.")

    # 3) Schedule the create-room coroutine on the existing loop
    logger.debug("Scheduling do_create_room() on the existing loop with run_coroutine_threadsafe.")
    future_create = asyncio.run_coroutine_threadsafe(do_create_room(), loop)

    try:
        # 4) Block on the future’s .result()
        logger.debug("Blocking on future_create.result() to get the room_create response.")
        resp = future_create.result()
        logger.debug(f"future_create.result() returned => {resp}")

        if isinstance(resp, RoomCreateResponse):
            logger.info(f"SYSTEM: Created room '{room_name}' => {resp.room_id}")
        else:
            # Possibly an ErrorResponse or some unexpected type
            logger.warning(f"room_create returned a non-RoomCreateResponse => {resp}")
            print(f"SYSTEM: Error creating room => {resp}")

    except Exception as e:
        logger.exception("Exception while creating room in cmd_create_room.")
        print(f"SYSTEM: Exception while creating room => {e}")

    finally:
        # 5) Clean up: schedule the close() coroutine
        logger.debug("Scheduling do_close_client() to gracefully close the AsyncClient.")
        future_close = asyncio.run_coroutine_threadsafe(do_close_client(), loop)
        try:
            logger.debug("Blocking on future_close.result() to confirm the client is closed.")
            future_close.result()
        except Exception as e2:
            logger.exception("Error while closing the client in cmd_create_room final block.")
            print(f"SYSTEM: Error closing client => {e2}")
        logger.debug("cmd_create_room: Done with final block.")



def cmd_create_room_dep(args, loop):
    """
    Usage: create_room <roomName>
    Creates a new room named <roomName> via the normal client API (room_create).
    """
    if not args:
        print("SYSTEM: Usage: create_room <roomName>")
        return

    room_name = args.strip()
    print(f"SYSTEM: Creating a new room named '{room_name}'...")

    # fut = asyncio.run_coroutine_threadsafe(
    #     luna_functions.create_room_with_clientapi(room_name, is_public=True),
    #     loop
    # )

    def on_done(f):
        try:
            msg = f.result()
            print(f"SYSTEM: {msg}")
        except Exception as e:
            print(f"SYSTEM: Error creating room => {e}")

    fut.add_done_callback(on_done)

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
    print("SYSTEM: Console screen cleared.")

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
    log_file = "server.log"
    rotated_file = f"server-{timestamp}.log"

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
    5) Prompt user to confirm if they'd like to restart Luna, which calls cmd_restart to relaunch with a fresh token.

    This is a destructive operation. Type 'y' to confirm at the start.
    """
    # Step 0: Basic confirmation
    confirm_initial = input("This will REMOVE 'homeserver.db' and local store files. Continue? (y/N): ")
    if confirm_initial.lower().strip() != 'y':
        print("Aborted.")
        return

    # Step 1: Prompt user to stop the server
    print("\nPlease STOP your Synapse server now. Type 'confirm' once it's fully stopped.")
    confirm_stop = input("> ").lower().strip()
    if confirm_stop != "confirm":
        print("Aborted: server may still be running.")
        return

    # Step 2: Remove homeserver.db
    try:
        base_dir = os.path.expanduser("~/Documents/luna2/matrix")
        db_file = "homeserver.db"
        db_path = os.path.join(base_dir, db_file)

        if os.path.exists(db_path):
            print(f"{db_path} exists. Removing it now.")
            os.remove(db_path)
            print("Removed homeserver.db.")
        else:
            print(f"{db_path} not found, skipping removal.")
    except Exception as e:
        print(f"Error removing homeserver.db: {e}")
        return

    # Step 3: Remove local store files
    local_store_files = [
        "luna_messages.csv",    # MESSAGES_CSV
        "sync_token.json",      # SYNC_TOKEN_FILE
        "director_token.json"   # Forces fresh login on next run
    ]
    for store_file in local_store_files:
        if os.path.exists(store_file):
            try:
                os.remove(store_file)
                print(f"Removed local store file: {store_file}")
            except Exception as e:
                print(f"Error removing {store_file}: {e}")
        else:
            print(f"{store_file} not found, skipping removal.")

    print("\nPurge complete (database + local store).")
    print("Now, please START your Synapse server again (e.g. `systemctl start matrix-synapse`).")
    print("Type 'confirm' once the server is running, or anything else to abort.")
    confirm_start = input("> ").lower().strip()
    if confirm_start != "confirm":
        print("Aborted: server may still be offline.")
        return

    # Step 4: Re-register admin user (needs server up)
    cmd_admin = [
        "register_new_matrix_user",
        "-c", "/Users/evanrobinson/Documents/Luna2/matrix/homeserver.yaml",
        "-u", "admin",
        "-p", "12345",
        "--admin",
        "http://localhost:8008"
    ]
    try:
        subprocess.run(cmd_admin, check=True)
        print("Registered admin:localhost.")
    except subprocess.CalledProcessError as e:
        print(f"Error registering admin: {e}")
        return

    # Step 5: Register lunabot user
    cmd_luna = [
        "register_new_matrix_user",
        "-c", "/Users/evanrobinson/Documents/Luna2/matrix/homeserver.yaml",
        "-u", "lunabot",
        "-p", "12345",
        "--admin",
        "http://localhost:8008"
    ]
    try:
        subprocess.run(cmd_luna, check=True)
        print("Registered luna:localhost.")
    except subprocess.CalledProcessError as e:
        print(f"Error registering luna: {e}")
        return

    print("\nServer has been purged and seeded with new admin + lunabot accounts.")
    print("If Luna is currently running, it will still have an old token until it restarts.")
    print("Type 'confirm' to restart Luna now (calling `cmd_restart`), or anything else to skip.")
    final_confirm = input("> ").lower().strip()
    if final_confirm == "confirm":
        print("Restarting Luna process now...")
        cmd_restart("", loop)
    else:
        print("Skipping Luna restart. If you want a fresh token, please exit or restart Luna manually.")


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
    from src.cmd_shutdown import SHOULD_SHUT_DOWN
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

    # 2) Schedule the async call to list_rooms
    future = asyncio.run_coroutine_threadsafe(
        luna_functions.list_rooms(),
        loop
    )

    # 3) Define a callback to handle results once the coroutine finishes
    def on_done(fut):
        try:
            rooms_info = fut.result()
            if not rooms_info:
                print("SYSTEM: No rooms found or DIRECTOR_CLIENT is not ready.")
                return

            if json_flag:
                # Print as JSON
                print(json.dumps(rooms_info, indent=2))
            else:
                # Print a formatted table
                _print_rooms_table(rooms_info)

        except Exception as e:
            logger.exception(f"Exception in cmd_list_rooms: {e}")
            print(f"SYSTEM: Error listing rooms: {e}")

    future.add_done_callback(on_done)
    print("SYSTEM: Fetching rooms. Please wait...")

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


def cmd_list_users_dep(args, loop):    
    """
    Usage: list_users [--json]

    Fetches a list of users (user_id, displayname, admin flag, etc.) from the Synapse server.
    If you provide '--json', it will print the output as JSON instead of a table.
    """
    # 1) Check if the user wants JSON output
    parts = args.strip().split()
    json_flag = ("--json" in parts)

    # 2) Schedule the async call to list_users
    future = asyncio.run_coroutine_threadsafe(
        luna_functions.list_users(),
        loop
    )

    # 3) Define a callback
    def on_done(fut):
        try:
            users_info = fut.result()
            if not users_info:
                print("SYSTEM: No users found or we failed to query the server.")
                return

            if json_flag:
                # Print as JSON
                print(json.dumps(users_info, indent=2))
            else:
                # Print a formatted table
                _print_users_table(users_info)

        except Exception as e:
            logger.exception(f"Exception in cmd_list_users: {e}")
            print(f"SYSTEM: Error listing users: {e}")

    future.add_done_callback(on_done)
    print("SYSTEM: Fetching users. Please wait...")

def _print_users_table_dep(users_info: list[dict]):
    """
    Helper function to print a table of user data:
      USER ID (up to ~25 chars) | ADMIN | DEACTIVATED | DISPLAYNAME
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

    Invites a user to the given room using the director client.
    """
    parts = args.strip().split()
    if len(parts) < 2:
        print("SYSTEM: Usage: invite_user <user_id> <room_id>")
        return

    user_id = parts[0]
    room_id = parts[1]

    # 1) Schedule the async call on the main loop
    future = asyncio.run_coroutine_threadsafe(
        luna_functions.invite_user_to_room(user_id, room_id),
        loop
    )

    # 2) Provide a callback to handle the result
    def on_done(fut):
        try:
            result_msg = fut.result()
            print(f"SYSTEM: {result_msg}")
        except Exception as e:
            logger.exception(f"Exception in cmd_invite_user callback: {e}")
            print(f"SYSTEM: Error inviting user: {e}")

    future.add_done_callback(on_done)
    print(f"SYSTEM: Inviting {user_id} to {room_id}... Please wait.")

def cmd_create_bot_user(args, loop):
    """
    Usage:
      create_bot <localpart> <displayname> <system_prompt> <password> [traits...]
    """
    parts = args.strip().split()
    if len(parts) < 4:
        print("SYSTEM: Usage: create_bot <localpart> <displayname> <system_prompt> <password> [traits...]")
        return

    localpart = parts[0]
    displayname = parts[1]
    system_prompt = parts[2]
    password = parts[3]
    trait_pairs = parts[4:]  # e.g. ["age=40", "color=blue"]

    # Parse traits if provided
    traits = {}
    for t in trait_pairs:
        if "=" in t:
            k, v = t.split("=", 1)
            traits[k] = v

    bot_id = f"@{localpart}:localhost"

    # Step A: Create local persona
    try:
        persona = luna_personas.create_bot(
            bot_id=bot_id,
            displayname=displayname,
            creator_user_id="@lunabot:localhost",  # or whomever
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

    # Step B: Register user with Synapse (async call)
    from src.luna_functions import create_user as matrix_create_user

    fut = asyncio.run_coroutine_threadsafe(
        matrix_create_user(localpart, password, is_admin=False),
        loop
    )

    try:
        # BLOCK here until the future completes or times out.
        # You can specify a timeout if desired, e.g. .result(timeout=10)
        result_msg = fut.result()
        print(f"SYSTEM: Matrix user creation => {result_msg}")
    except Exception as e:
        print(f"SYSTEM: Error creating matrix user => {e}")

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
    print(f"SYSTEM: Initiating Matrix user deletion for {bot_id}...")


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
    

    "create_room": cmd_create_room,
    "create_bot": cmd_create_bot_user,

    "fetch_all": cmd_fetch_all,
    "fetch_new": cmd_fetch_new,

    "list_users": cmd_list_users,
    "list_rooms": cmd_list_rooms,

    "invite_user": cmd_invite_user
}