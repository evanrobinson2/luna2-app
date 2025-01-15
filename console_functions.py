import os
import sys
import logging
import subprocess
import shlex
import asyncio
import textwrap
import json
import aiohttp
from datetime import datetime
from nio import AsyncClient
from asyncio import CancelledError
import json
from luna import luna_personas
from luna import luna_functions
from nio.api import RoomVisibility
from luna.luna_functions import DIRECTOR_CLIENT
import asyncio
from luna.luna_command_extensions.create_room import create_room
from luna.luna_command_extensions.cmd_remove_room import cmd_remove_room
from luna.luna_personas import get_system_prompt_by_localpart, set_system_prompt_by_localpart
from luna.luna_command_extensions.cmd_shutdown import request_shutdown
from luna.luna_command_extensions.ascii_art import show_ascii_banner

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

    Displays the log file path by inspecting the logging configuration
    to find a FileHandler. If found, we print that file’s path; if not,
    we mention that no file-based logging is detected.
    """
    logger = logging.getLogger()  # The root logger
    file_handler_found = False

    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            log_path = getattr(handler, "baseFilename", None)
            if log_path:
                print(f"SYSTEM: Log file is located at: {log_path}")
                file_handler_found = True
                break
    
    if not file_handler_found:
        print("SYSTEM: No file-based logger was found. Logs may be console-only.")

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
    from luna_functions import DIRECTOR_CLIENT
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

def cmd_rotate_logs(args, loop):
    """
    Usage: rotate_logs

    Renames 'server.log' to a timestamped file (e.g. server-20250105-193045.log),
    then reinitializes the logger so new logs go into a fresh file.
    """
    logger.info("Rotating logs...")

    from datetime import datetime
    import os
    import logging

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    log_file = "data/logs/server.log"
    archive_dir = "data/logs/archive"
    rotated_file = f"{archive_dir}/server-{timestamp}.log"

    # 1) Ensure the archive directory exists
    try:
        os.makedirs(archive_dir, exist_ok=True)
    except Exception as e:
        print(f"SYSTEM: Error creating archive directory '{archive_dir}': {e}")
        return

    # 2) Rotate the current file
    if os.path.exists(log_file):
        try:
            os.rename(log_file, rotated_file)
            print(f"SYSTEM: Rotated {log_file} -> {rotated_file}")
        except Exception as e:
            print(f"SYSTEM: Error rotating logs: {e}")
            return
    else:
        print("SYSTEM: No server.log found to rotate.")

    # 3) Create a fresh server.log
    try:
        with open(log_file, "w") as f:
            pass
        print("SYSTEM: New server.log created.")
    except Exception as e:
        print(f"SYSTEM: Error creating new server.log: {e}")

    # 4) Re-init logging so future logs go into the new file
    #    (Close the old handler, create a new FileHandler, attach it, etc.)
    root_logger = logging.getLogger()

    # Remove old file handlers
    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)
            handler.close()

    # Create a new file handler for "server.log"
    new_handler = logging.FileHandler(log_file)
    new_handler.setLevel(logging.DEBUG)  # adjust as preferred
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    new_handler.setFormatter(formatter)
    root_logger.addHandler(new_handler)

    logger.info(f"Log rotation complete. Logging to {log_file} again.")
    print(f"SYSTEM: Logging has been reinitialized to {log_file}.")

def cmd_purge_and_seed(args, loop):
    """
    Usage: purge_and_seed

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

    This version BLOCKS the console thread until the fetch completes.
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

    try:
        # BLOCK until the fetch completes
        future.result()  # you could pass a timeout here if desired
        print("SYSTEM: Successfully fetched all historical messages.")
    except Exception as e:
        logger.exception(f"Error in fetch_all: {e}")
        print(f"SYSTEM: Error in fetch_all: {e}")

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

    Parses console arguments, then calls create_and_login_bot(...).
    This ensures the new user is created on Synapse and ephemeral-logged into BOTS.
    """
    import logging
    from luna.luna_command_extensions.create_and_login_bot import create_and_login_bot

    logger = logging.getLogger(__name__)

    parts = args.strip().split()
    if len(parts) < 2:
        print("Usage: create_user <username> <password> [--admin]")
        return

    username, password = parts[:2]
    is_admin = False
    if len(parts) > 2 and parts[2].lower() == "--admin":
        is_admin = True

    # Wrap in an async function so we can run it on the event loop:
    async def create_and_login():
        return await create_and_login_bot(username, password, is_admin)

    future = asyncio.run_coroutine_threadsafe(create_and_login(), loop)

    def on_done(fut):
        try:
            result = fut.result()
            # For example: "Successfully created & logged in bot => @alice:localhost"
            print(f"SYSTEM: {result}")
        except Exception as e:
            print(f"Error while creating user '{username}': {e}")
            logger.exception("Exception in cmd_create_user callback.")

    future.add_done_callback(on_done)
    print(f"SYSTEM: Creating & logging in user '{username}' (admin={is_admin})...")


def cmd_show_shutdown(args, loop):
    """
    Usage: show_shutdown

    Prints the current value of SHOULD_SHUT_DOWN (a boolean).
    """
    from luna_command_extensions.cmd_shutdown import SHOULD_SHUT_DOWN
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
    Usage: invite_user <user_id> <room_id_or_alias>

    Example:
      invite_user @bob:localhost !testRoom:localhost
      invite_user @spyclops:localhost #mychannel:localhost

    Sends a normal invite to the specified user_id, so they can accept
    and join the given room or room alias. This requires that the user
    executing this command (Luna's director) has sufficient power level
    in the room to invite new participants.
    """

    parts = args.strip().split()
    if len(parts) < 2:
        print("SYSTEM: Usage: invite_user <user_id> <room_id_or_alias>")
        return

    user_id = parts[0]
    room_id_or_alias = parts[1]

import logging
import asyncio
import aiohttp
import time
from luna import luna_functions

logger = logging.getLogger(__name__)

async def do_invite_user(user: str, room: str) -> str:
    """
    Asynchronous subroutine to invite 'user' to 'room' (which might be
    a raw room ID like "!abc123:localhost" or possibly a name or alias).
    1) Forces a short sync to ensure the client sees the correct power levels.
    2) Invokes client.room_invite(...).
    3) If M_FORBIDDEN occurs, we provide a more detailed message.
    """

    client = luna_functions.getClient()
    if not client:
        return "Error: No DIRECTOR_CLIENT set."

    # 1) Force a short sync so our client state is up-to-date:
    try:
        # Run a blocking sync in the current thread
        sync_future = asyncio.run_coroutine_threadsafe(
            client.sync(timeout=1000),  # 1-second sync
            luna_functions.MAIN_LOOP  # or your existing loop reference
        )
        sync_future.result()
        logger.debug("[do_invite_user] Sync completed before invite.")
    except Exception as sync_e:
        logger.exception("Sync error before inviting user:")
        return f"Error syncing before invite => {sync_e}"
    try:
        resp = await client.room_invite(room, user)
        logger.debug(f"[do_invite_user] room_invite returned => {resp}")

        if resp and hasattr(resp, "status_code"):
            code = resp.status_code
            if code in (200, 202):
                return f"Invited {user} to {room}."
            else:
                # If we see 403 or 401, typically it's M_FORBIDDEN or not enough power
                if code == 403:  
                    return (
                        f"Error inviting {user} => M_FORBIDDEN. "
                        "Possible cause: insufficient power level or not recognized in the room. "
                        "Ensure you (the inviter) are joined & have the right power level."
                    )
                return f"Error inviting {user} => {code} (Check logs for details.)"
        else:
            # If resp is None or not recognized
            return "Invite returned an unexpected or null response."
    except Exception as e:
        logger.exception("[do_invite_user] Exception in room_invite:")
        # If e is a matrix-nio error (e.g., RoomInviteError), we can handle it specifically
        return f"Exception inviting user => {e}" 

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
    from luna_functions import delete_matrix_user
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
    
def cmd_create_room(args, loop):
    """
    Usage: create_room "<roomName>" [--private]

    Example:
      create_room "My Room With Spaces" --private

    We'll pass the entire 'args' to create_room(...) so it can parse
    out the room name and flags with shlex.
    """

    future = asyncio.run_coroutine_threadsafe(
        create_room(args),  # <== note: just 'args'
        loop
    )

    def on_done(fut):
        try:
            result_msg = fut.result()
            print(f"SYSTEM: {result_msg}")
        except Exception as e:
            print(f"SYSTEM: Error creating room => {e}")

    future.add_done_callback(on_done)

def cmd_get_bot_system_prompt(args, loop):
    """
    Usage: get_bot_sp <bot_localpart>

    Example:
      get_bot_sp inky

    Retrieves the current system_prompt for a bot with the given localpart,
    e.g. "inky" => bot ID "@inky:localhost".
    Prints it to the console or a warning if not found.
    """
    parts = args.strip().split()
    if len(parts) < 1:
        print("Usage: get_bot_sp <bot_localpart>")
        return

    localpart = parts[0]

    # Just call get_system_prompt_by_localpart right away
    system_prompt = get_system_prompt_by_localpart(localpart)
    if system_prompt is None:
        print(f"SYSTEM: No bot found for localpart='{localpart}'.")
    else:
        print(f"SYSTEM: The system_prompt for '{localpart}' =>\n\n{system_prompt}")

def cmd_set_bot_system_prompt(args, loop):
    """
    Usage: set_bot_sp <bot_localpart> "<new system prompt>"

    Example:
      set_bot_sp inky "You are Inky, the fastest ghost in Pac-Man!"

    Sets (overwrites) the system_prompt for the given localpart.
    Must wrap the new prompt in quotes if it contains spaces.
    """
    # We'll parse args with shlex so we can capture quoted text properly
    try:
        tokens = shlex.split(args.strip())
    except ValueError as e:
        print(f"SYSTEM: Error parsing arguments => {e}")
        return

    if len(tokens) < 2:
        print("Usage: set_bot_sp <bot_localpart> \"<new system prompt>\"")
        return

    localpart = tokens[0]
    new_prompt = tokens[1]  # This might be already unquoted by shlex

    # If there's leftover beyond tokens[1], we might want to re-join them,
    # or your usage pattern might always require quotes around new_prompt.
    # For a minimal approach, assume the user has put the entire prompt in quotes:
    #   set_bot_sp inky "Hello world, I'm your ghost"
    # then tokens should be ["inky", "Hello world, I'm your ghost"].

    updated_persona = set_system_prompt_by_localpart(localpart, new_prompt)
    if updated_persona is None:
        print(f"SYSTEM: No bot found for localpart='{localpart}'.")
    else:
        # Confirm success
        print(f"SYSTEM: Updated system_prompt for '{localpart}' =>\n\n{new_prompt}")

def cmd_who_is(args, loop):
    """
    Usage: who_is <localpart>

    Retrieves and displays persona info from personalities.json for
    the bot with that <localpart>, in a table with wrapped text for
    each field's value.

    Example:
      who_is inky
    """

    parts = args.strip().split()
    if len(parts) < 1:
        print("Usage: who_is <localpart>")
        return

    localpart = parts[0]
    full_user_id = f"@{localpart}:localhost"

    # Attempt to read the persona from personalities.json
    persona = luna_personas.read_bot(full_user_id)
    if not persona:
        print(f"SYSTEM: No persona found for '{full_user_id}' in personalities.json.")
        return

    # Print header
    print(f"\nSYSTEM: Persona for bot => {full_user_id}\n")

    # Determine how wide the left (key) column should be
    # so everything lines up neatly
    max_key_len = max(len(k) for k in persona.keys())

    # Choose a wrapping width for values
    wrap_width = 60

    # Print each key-value pair in a nicely formatted table
    for key, raw_value in persona.items():
        # If the value is a dict or list, JSON-serialize for display
        if isinstance(raw_value, (dict, list)):
            value_str = json.dumps(raw_value, indent=2)
        else:
            # Otherwise, just convert to string
            value_str = str(raw_value)

        # Wrap the text at wrap_width characters
        lines = textwrap.wrap(value_str, width=wrap_width) or ["(empty)"]

        # Print the first line with the key
        print(f"{key.ljust(max_key_len)} : {lines[0]}")
        
        # For any additional lines, align them under the value column
        for line in lines[1:]:
            print(" " * (max_key_len + 3) + line)

    print()

def cmd_summon_long_prompt(args, loop):
    """
    Usage: summon_long_prompt "<giant blueprint text>"

    We'll feed that blueprint to GPT with a small system instruction telling
    it to create a well-formed persona definition, which we then parse + spawn.
    """

    import shlex
    tokens = shlex.split(args, posix=True)
    if not tokens:
        print("Usage: summon_long_prompt \"<blueprint text>\"")
        return

    blueprint_text = tokens[0]  # Or re-join tokens if you allow multiple quoted sections

    async def do_summon():
        from luna.ai_functions import get_gpt_response  # or your new GPT call
        # 1) Build the short instruction
        system_inst = (
            "You will receive a 'blueprint' text that describes how a new persona should behave.\n"
            "You must return a JSON object with the following keys:\n"
            "  localpart (string), displayname (string), system_prompt (string), traits (object)\n"
            "No extra keys, no markdown.\n"
            "If user does not specify a localpart, create one from the blueprint.\n"
            "If user does not specify a displayname, guess it or do something generic.\n"
            "Be as versose and dirctive as possible in your creation of the system prompt.\n"
            "Instruct the bot to be absolutely willing to talk about prior messages and conversation history.\n"
        )

        # 2) GPT conversation array
        conversation = [
            {"role": "system", "content": system_inst},
            {
                "role": "user",
                "content": (
                    f"Below is the blueprint. Please parse it and produce your JSON:\n\n"
                    f"{blueprint_text}"
                ),
            },
        ]

        # 3) Make GPT call
        gpt_reply = await get_gpt_response(
            messages=conversation,
            model="gpt-4",
            temperature=0.7,
            max_tokens=500
        )

        # 4) Parse JSON, handle errors
        import json
        try:
            persona_data = json.loads(gpt_reply)
        except json.JSONDecodeError as e:
            return f"GPT returned invalid JSON => {e}\n\n{gpt_reply}"

        # 5) Validate required keys
        for needed in ["localpart", "displayname", "system_prompt", "traits"]:
            if needed not in persona_data:
                return f"Missing required field '{needed}' in GPT output => {persona_data}"

        # 6) Summon the bot
        from luna.luna_command_extensions.create_and_login_bot import create_and_login_bot
        new_bot_id = f"@{persona_data['localpart']}:localhost"
        password = "somePassword123"  # or randomly generate

        result_msg = await create_and_login_bot(
            bot_id=new_bot_id,
            password=password,
            displayname=persona_data["displayname"],
            system_prompt=persona_data["system_prompt"],
            traits=persona_data["traits"]
        )
        return result_msg

    future = asyncio.run_coroutine_threadsafe(do_summon(), loop)

    def on_done(fut):
        try:
            outcome = fut.result()
            print(f"SYSTEM: {outcome}")
        except Exception as e:
            print(f"SYSTEM: Summon error => {e}")

    future.add_done_callback(on_done)
    print("SYSTEM: Summoning a bot from your blueprint... please wait.")

def cmd_spawn_squad(args, loop):
    """
    Usage: spawn <numBots> "<theme or style>"

    Example:
      spawn_squad 3 "A jazzy trio of improvisational bots"
    """
    # Import inside the function to avoid circular imports or to keep it minimal:
    from luna.luna_command_extensions.spawner import cmd_spawn_squad as spawner_impl

    # Just delegate all logic:
    spawner_impl(args, loop)

def cmd_run_json_script(args, loop):
    """
    Usage: run_script <script_file>

    Reads a JSON-based script from <script_file>, then parses and executes it.
    The script can contain actions like:
      - create_room
      - create_user
      - add_user_to_channel
      ... etc.

    Example:
      run_script my_script.json

    The command will load 'my_script.json' from disk, parse it,
    then execute the actions in order, printing logs along the way.
    """
    import os
    import logging
    import json
    from luna.luna_command_extensions.parse_and_execute import parse_and_execute

    logger = logging.getLogger(__name__)
    logger.debug("[cmd_run_json_script] Called with args='%s'", args)

    # 1) Parse console arguments
    parts = args.strip().split()
    if len(parts) < 1:
        print("Usage: run_script <script_file>")
        return

    script_file = parts[0]
    logger.debug("User provided script_file='%s'", script_file)

    # 2) Check if the file exists
    if not os.path.exists(script_file):
        msg = f"[cmd_run_json_script] File not found: {script_file}"
        logger.error(msg)
        print(f"SYSTEM: {msg}")
        return

    # 3) Read the file contents
    try:
        with open(script_file, "r", encoding="utf-8") as f:
            script_str = f.read()
        logger.debug("[cmd_run_json_script] Successfully read %d bytes from '%s'.",
                     len(script_str), script_file)
    except Exception as e:
        logger.exception("[cmd_run_json_script] Failed to read file '%s': %s", script_file, e)
        print(f"SYSTEM: Error reading file '{script_file}': {e}")
        return

    # 4) Execute the script
    print(f"SYSTEM: Executing script from '{script_file}'...")
    logger.debug("[cmd_run_json_script] Invoking parse_and_execute(...)")
    try:
        parse_and_execute(script_str, loop)
        logger.debug("[cmd_run_json_script] parse_and_execute completed.")
    except Exception as e:
        logger.exception("[cmd_run_json_script] parse_and_execute threw an exception: %s", e)
        print(f"SYSTEM: Error executing script: {e}")
        return

    # 5) Confirm success
    print("SYSTEM: Script execution command finished.")

########################################################
# THE COMMAND ROUTER DICTIONARY
########################################################

COMMAND_ROUTER = {
    # System or meta-commands
    "help": cmd_help,
    "restart": cmd_restart,
    "exit": cmd_exit,
    
    "logfile": cmd_log,
    "rotate_logs": cmd_rotate_logs,
    
    "clear": cmd_clear,
    "purge_and_seed": cmd_purge_and_seed, # stub-only
    
    "create_room": cmd_create_room,
    "remove_room" : cmd_remove_room,
    "list_rooms": cmd_list_rooms,
    "fetch_all": cmd_fetch_all,

    "list_users": cmd_list_users,
    "whois":cmd_who_is,
    "whois_director": cmd_who,
    "get_system_prompt_for": cmd_get_bot_system_prompt,
    "set_system_prompt_for": cmd_set_bot_system_prompt,

    "invite": cmd_invite_user,
    "spawn": cmd_spawn_squad,
    "run_script": cmd_run_json_script,
}