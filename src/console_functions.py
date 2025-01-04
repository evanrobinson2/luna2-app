import os
import sys
import logging
import asyncio
from datetime import datetime


from src.luna_functions import (
    DIRECTOR_CLIENT,
    AUTO_JOIN_ENABLED,
    set_auto_join,
    console_send_message,
    director_create_room,
    director_invite_user,
    director_invite_admin,
    get_director  # <-- new import for 'who' command
)

logger = logging.getLogger(__name__)

def console_loop():
    """
    A blocking loop reading console commands in a background thread.
    Prints "Awaiting command..." then shows a date-time prompt (YYYY-MM-DD HH:MM.ss %).
    Interprets commands and calls existing logic in luna_functions.
    """
    while True:
        print("Awaiting command...")
        time_prompt = datetime.now().strftime('%Y-%m-%d %H:%M.%S') + " % "
        cmd = input(time_prompt)
        if not cmd:
            continue

        lower_cmd = cmd.strip().lower()
        logger.debug(f"Raw input is: [{repr(cmd)}]")

        if lower_cmd == "exit":
            logger.info("Console received 'exit' command. Exiting process.")
            sys.exit(0)
        elif lower_cmd == "help":
            show_help()
        elif lower_cmd == "autojoin on":
            set_auto_join(True)
            logger.info("Auto-join turned ON.")
        elif lower_cmd == "autojoin off":
            set_auto_join(False)
            logger.info("Auto-join turned OFF.")
        elif cmd.startswith("send "):
            message_text = cmd[len("send "):].strip()
            if not message_text:
                logger.warning("No message text provided for 'send' command.")
                continue

            if DIRECTOR_CLIENT:
                test_room_id = "!abc123:localhost"
                logger.info(f"(Console) Scheduling send to {test_room_id}: {message_text}")
                asyncio.run_coroutine_threadsafe(
                    console_send_message(test_room_id, message_text),
                    asyncio.get_event_loop()
                )
            else:
                logger.warning("Director client not initialized yet.")
        elif lower_cmd.startswith("create room "):
            room_name = cmd[len("create room "):].strip()
            if not room_name:
                logger.warning("No room name provided after 'create room'.")
                continue

            if DIRECTOR_CLIENT:
                logger.info(f"(Console) Scheduling creation of room '{room_name}'")
                asyncio.run_coroutine_threadsafe(
                    director_create_room(room_name),
                    asyncio.get_event_loop()
                )
            else:
                logger.warning("Director client not initialized yet.")
        elif lower_cmd.startswith("add participant "):
            parts = cmd.split()
            if len(parts) < 4:
                logger.warning("Usage: add participant <roomId> <userId>")
                continue

            room_id = parts[2]
            user_id = parts[3]

            if DIRECTOR_CLIENT:
                logger.info(f"(Console) Scheduling invite of user '{user_id}' to {room_id}")
                asyncio.run_coroutine_threadsafe(
                    director_invite_user(room_id, user_id),
                    asyncio.get_event_loop()
                )
            else:
                logger.warning("Director client not initialized yet.")
        elif lower_cmd.startswith("invite admin "):
            parts = cmd.split()
            if len(parts) < 3:
                logger.warning("Usage: invite admin <roomId>")
                continue

            room_id = parts[2]

            if DIRECTOR_CLIENT:
                logger.info(f"(Console) Scheduling invite of 'admin' to {room_id}")
                asyncio.run_coroutine_threadsafe(
                    director_invite_admin(room_id),
                    asyncio.get_event_loop()
                )
            else:
                logger.warning("Director client not initialized yet.")
        elif lower_cmd == "clear":
            clear_console()
        elif lower_cmd == "who":
            # Synchronously check the Director identity
            identity = get_director()
            print(identity)
        else:
            logger.debug(f"Unrecognized command: {cmd}")

def show_help():
    """
    Prints a help message listing all available commands.
    Update this whenever new commands are added or removed.
    """
    print("\n=== AVAILABLE COMMANDS ===\n"
          "exit                           - Exit the entire process\n"
          "help                           - Show this help listing\n"
          "autojoin on                    - Enable auto-joining new invites\n"
          "autojoin off                   - Disable auto-joining new invites\n"
          "send <message>                 - Send <message> to a predefined test room\n"
          "create room <roomName>         - Create a new room named <roomName>\n"
          "add participant <roomId> <userId> - Invite <userId> to join <roomId>\n"
          "invite admin <roomId>          - Invite an 'admin' user to <roomId>\n"
          "clear                          - Clear the console screen\n"
          "who                            - Show whether Director is None or which user it's logged in as\n"
          "\n(Type the command, press Enter.)\n")
    logger.info("Displayed help to the console user.")

def clear_console():
    """
    Clears the console screen in a cross-platform way.
    On Windows, uses 'cls'; on Linux/macOS, uses 'clear'.
    """
    if os.name == 'nt':  # Windows
        os.system('cls')
    else:
        os.system('clear')
    logger.info("Console screen cleared.")
