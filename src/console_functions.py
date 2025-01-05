import os
import sys
import logging
import subprocess
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)




########################################################
# 1) COMMAND HANDLER FUNCTIONS
########################################################

def cmd_help(args, loop):
    """
    Usage: help

    Show usage for all known commands in a single-line, tab-separated format.
    """
    logger.debug("Showing help to user.")
    print("SYSTEM: Available commands (condensed):\n")
    for cmd_name, cmd_func in COMMAND_ROUTER.items():
        doc = (cmd_func.__doc__ or "").strip()
        if not doc:
            # If no docstring, just note that usage is unknown
            print(f"{cmd_name}\t(No usage info)\t(No description)")
            continue

        # Break the docstring into lines
        lines = doc.splitlines()
        usage_line = ""
        description = ""

        # We'll look for a line that starts with "Usage:"
        # Then everything else is the short description
        if lines:
            usage_candidate = lines[0].strip()
            if usage_candidate.startswith("Usage:"):
                usage_line = usage_candidate
                if len(lines) > 1:
                    # Join all subsequent lines as description
                    description = " ".join(l.strip() for l in lines[1:] if l.strip())
            else:
                # If the first line doesn't start with "Usage:", treat it as description
                usage_line = "(No usage)"
                description = " ".join(l.strip() for l in lines if l.strip())

        # Print on one line, separated by tabs
        # Example output:
        # create       Usage: create <roomName>     Creates a new room named <roomName>.
        print(f"{cmd_name}\t{usage_line}\t{description}")

    print()  # A blank line after the listing

def cmd_exit(args, loop):
    """
    Usage: exit

    Exits the entire process.
    """
    logger.info("Console received 'exit' command; calling sys.exit(0).")
    sys.exit(0)

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
    Usage: create <roomName>

    Creates a new room named <roomName>.
    """
    if not args:
        print("SYSTEM: Usage: create <roomName>")
        return

    room_name = args.strip()
    logger.info(f"(Console) Scheduling creation of room '{room_name}'")
    print(f"SYSTEM: Creating a new room named '{room_name}'...")

    # Here you'd call the actual async logic (e.g. from luna_functions)
    future = asyncio.run_coroutine_threadsafe(
        mock_async_create_room(room_name),
        loop
    )

    def on_done(fut):
        try:
            room_id = fut.result()
            if room_id:
                print(f"SYSTEM: Created room '{room_name}' => {room_id}")
            else:
                print(f"SYSTEM: Failed to create room '{room_name}'")
        except Exception as e:
            print(f"SYSTEM: Error creating room '{room_name}': {e}")

    future.add_done_callback(on_done)

async def mock_async_create_room(room_name):
    """
    A placeholder async function that simulates creating a room.
    In real usage, you'd call something like `director_create_room(room_name)`
    from `luna_functions.py`.
    """
    await asyncio.sleep(0.1)  # simulate network
    return "!mockRoomId:localhost"

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
    then creates a new empty 'server.log'. This ensures old logs are preserved.
    """
    # Build a timestamp
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    log_file = "server.log"
    rotated_file = f"server-{timestamp}.log"

    # Check if server.log exists
    if os.path.exists(log_file):
        try:
            os.rename(log_file, rotated_file)
            print(f"SYSTEM: Rotated {log_file} -> {rotated_file}")
        except Exception as e:
            print(f"SYSTEM: Error rotating logs: {e}")
            return
    else:
        print("SYSTEM: No server.log found to rotate.")

    # Create a fresh server.log
    try:
        with open(log_file, "w") as f:
            pass  # just create an empty file
        print("SYSTEM: New server.log created.")
    except Exception as e:
        print(f"SYSTEM: Error creating new server.log: {e}")

def cmd_purge_and_seed(args, loop):
    """
    Usage: purge_and_seed

    Removes 'homeserver.db', re-registers the admin/luna accounts,
    creates a new 'Test' channel, and invites @evan:localhost + @luna:localhost.

    Type 'y' to confirm and proceed.
    """
    confirmation = input("This will REMOVE 'homeserver.db' and re-seed the database. Continue? (y/N): ")
    if confirmation.lower().strip() != 'y':
        print("Aborted.")
        return

    # 1) Remove homeserver.db
    try:
        # Define the base directory and file name
        base_dir = os.path.expanduser("~/Documents/luna2/matrix")
        db_file = "homeserver.db"

        # Compose the full path
        db_path = os.path.join(base_dir, db_file)

        # Define the base directory and file name
        base_dir = os.path.expanduser("~/Documents/luna2/matrix")
        db_file = "homeserver.db"
        db_path = os.path.join(base_dir, db_file)

        # Check if the file exists and handle its removal
        if os.path.exists(db_path):
            print(f"{db_path} exists.")
            os.remove(db_path)
            print("Removed homeserver.db.")
        else:
            print(f"{db_path} not found, skipping removal.")
    except Exception as e:
        print(f"Error removing homeserver.db: {e}")
        return

    # 2) Register admin user
    cmd_admin = [
        "register_new_matrix_user",
        "-c", "/Users/evanrobinson/Documents/Luna2/matrix/homeserver.yaml",
        "-u", "admin:localhost",
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

    # 3) Register luna user
    cmd_luna = [
        "register_new_matrix_user",
        "-c", "/Users/evanrobinson/Documents/Luna2/matrix/homeserver.yaml",
        "-u", "luna:localhost",
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

    print("Purge, re-seed, and channel setup complete!")


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
    "purge_and_seed": cmd_purge_and_seed,

    # Business or “bot” commands
    "create": cmd_create_room,
    "who": cmd_who,
    "clear": cmd_clear,
    # Add more as needed...
}

