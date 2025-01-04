# console_functions.py
import os
import sys
import logging
import asyncio
from datetime import datetime

import src.luna_functions
from src.luna_functions import (
    AUTO_JOIN_ENABLED,
    set_auto_join,
    console_send_message,
    director_create_room,
    director_invite_user,
    director_invite_admin,
    get_director,
    DIRECTOR_CLIENT
)

logger = logging.getLogger(__name__)

LOGFILE_PATH = "server.log"  
# Adjust if your log file is in a different location.

def console_loop(loop):
    """
    A blocking loop reading console commands in a background thread.
    We'll schedule all coroutines on `loop` via asyncio.run_coroutine_threadsafe().
    """
    while True:
        time_prompt = datetime.now().strftime('%Y-%m-%d %H:%M.%S') + " % "
        cmd = input(time_prompt)
        if not cmd:
            continue

        lower_cmd = cmd.strip().lower()
        logger.debug(f"Raw input is: [{repr(cmd)}]")

        # Just logs to file, but also show the user what command was entered, prefixed with SYSTEM:
        print(f"SYSTEM: Command entered => '{lower_cmd}'. Current Director is: {src.luna_functions.DIRECTOR_CLIENT}")

        if lower_cmd == "exit":
            logger.info("Console received 'exit' command. Exiting process.")
            sys.exit(0)

        # ----------------------------------------------------------------------
        # NEW RESTART COMMAND
        # ----------------------------------------------------------------------
        elif lower_cmd == "restart":
            logger.info("Console received 'restart' command. Restarting process.")
            print("SYSTEM: Attempting to restart the entire process...")

            python_executable = sys.executable
            script = sys.argv[0]
            args = sys.argv[1:]  # Any additional arguments used to start this script

            # os.execl replaces the current process with a new process running
            # the same script. This call does not return if successful.
            os.execl(python_executable, python_executable, script, *args)
        # ----------------------------------------------------------------------

        elif lower_cmd == "help":
            show_help()

        elif lower_cmd == "autojoin on":
            set_auto_join(True)
            logger.info("Auto-join turned ON.")
            print("SYSTEM: Auto-join turned ON.")

        elif lower_cmd == "autojoin off":
            set_auto_join(False)
            logger.info("Auto-join turned OFF.")
            print("SYSTEM: Auto-join turned OFF.")

        elif lower_cmd == "log":
            # Show the log file path to the user
            print(f"SYSTEM: Log file is located at: {LOGFILE_PATH}\n"
                  "SYSTEM: Check that file for all logs, since console output is disabled.")

        elif cmd.startswith("send "):
            message_text = cmd[len("send "):].strip()
            if not message_text:
                logger.warning("No message text provided for 'send' command.")
                print("SYSTEM: No message text provided. Usage: send <message>")
                continue

            if src.luna_functions.DIRECTOR_CLIENT:
                test_room_id = "!abc123:localhost"
                logger.info(f"(Console) Scheduling send to {test_room_id}: {message_text}")
                print(f"SYSTEM: Sending your message to {test_room_id} ...")
                asyncio.run_coroutine_threadsafe(
                    console_send_message(test_room_id, message_text),
                    loop
                )
            else:
                logger.warning("Director client not initialized yet.")
                print("SYSTEM: Director client not initialized yet. Cannot send.")

        elif lower_cmd.startswith("create room "):
            # e.g. "create room my-test-channel"
            room_name = cmd[len("create room "):].strip()
            if not room_name:
                logger.warning("No room name provided after 'create room'.")
                print("SYSTEM: Usage: create room <roomName>")
                continue

            if src.luna_functions.DIRECTOR_CLIENT:
                logger.info(f"(Console) Scheduling creation of room '{room_name}'")
                print(f"SYSTEM: Creating a new room named '{room_name}'...")

                # Schedule the coroutine on the main loop
                future = asyncio.run_coroutine_threadsafe(
                    director_create_room(room_name),
                    loop
                )

                # Attach a callback to print the result once it's done
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
            else:
                logger.warning("Director client not initialized yet.")
                print("SYSTEM: Director client not initialized yet. Cannot create room.")

        elif lower_cmd.startswith("add participant "):
            # e.g. "add participant !abc123:localhost @bob:localhost"
            parts = cmd.split()
            if len(parts) < 4:
                logger.warning("Usage: add participant <roomId> <userId>")
                print("SYSTEM: Usage: add participant <roomId> <userId>")
                continue

            room_id = parts[2]
            user_id = parts[3]

            if src.luna_functions.DIRECTOR_CLIENT:
                logger.info(f"(Console) Scheduling invite of user '{user_id}' to {room_id}")
                print(f"SYSTEM: Inviting user '{user_id}' to room {room_id}...")
                asyncio.run_coroutine_threadsafe(
                    director_invite_user(room_id, user_id),
                    loop
                )
            else:
                logger.warning("Director client not initialized yet.")
                print("SYSTEM: Director client not initialized yet. Cannot add participant.")

        elif lower_cmd.startswith("invite admin "):
            # e.g. "invite admin !abc123:localhost"
            parts = cmd.split()
            if len(parts) < 3:
                logger.warning("Usage: invite admin <roomId>")
                print("SYSTEM: Usage: invite admin <roomId>")
                continue

            room_id = parts[2]

            if src.luna_functions.DIRECTOR_CLIENT:
                logger.info(f"(Console) Scheduling invite of 'admin' to {room_id}")
                print(f"SYSTEM: Inviting 'admin' to room {room_id}...")
                asyncio.run_coroutine_threadsafe(
                    director_invite_admin(room_id),
                    loop
                )
            else:
                logger.warning("Director client not initialized yet.")
                print("SYSTEM: Director client not initialized yet. Cannot invite admin.")

        elif lower_cmd == "clear":
            clear_console()

        elif lower_cmd == "who":
            # Show whether Director is None or which user it's logged in as
            identity = get_director()
            if identity:
                print(f"SYSTEM: Director is => {identity.user_id}")
                print(f"SYSTEM: Object => {identity}")
            else:
                print("SYSTEM: No Director Found")

        else:
            logger.debug(f"Unrecognized command: {cmd}")
            print(f"SYSTEM: Unrecognized command: {cmd}. Type 'help' for a list of commands.")

def show_help():
    print("SYSTEM: \n"
          "=== AVAILABLE COMMANDS ===\n"
          "exit                           - Exit the entire process\n"
          "restart                        - Kill & re-launch the process with the same arguments\n"
          "help                           - Show this help listing\n"
          "autojoin on                    - Enable auto-joining new invites\n"
          "autojoin off                   - Disable auto-joining new invites\n"
          "send <message>                 - Send <message> to a predefined test room\n"
          "create room <roomName>         - Create a new room named <roomName>\n"
          "add participant <roomId> <userId> - Invite <userId> to join <roomId>\n"
          "invite admin <roomId>          - Invite an 'admin' user to <roomId>\n"
          "clear                          - Clear the console screen\n"
          "who                            - Show whether Director is None or which user it's logged in as\n"
          "log                            - Show the path of the logfile\n"
          "\n(Type the command, then press Enter.)\n")
    logger.info("Displayed help to the console user.")

def clear_console():
    if os.name == 'nt':  # Windows
        os.system('cls')
    else:
        os.system('clear')
    logger.info("Console screen cleared.")
    print("SYSTEM: Console screen cleared.")
