import json
import logging
import asyncio
import re
import time

logger = logging.getLogger(__name__)

def parse_and_execute(script_str, loop):
    """
    A blocking version of parse_and_execute that:
      1) Creates rooms by name (private or public).
      2) Parses the console output to grab the actual room ID.
      3) Stores the (name -> room_id) mapping in a dictionary so that future
         "invite_user" actions can use the real room ID.
      4) Waits (or optionally does a forced sync) after creation so that
         the director has fully joined the room with correct power level
         before sending invites.

    Example JSON:
    {
      "title": "BlockInviteScript",
      "actions": [
        {
          "type": "create_room",
          "args": {
            "room_name": "myTreetop",
            "private": true
          }
        },
        {
          "type": "invite_user",
          "args": {
            "user_id": "@lunabot:localhost",
            "room_id_or_alias": "myTreetop"
          }
        },
        ...
      ]
    }
    """
    try:
        data = json.loads(script_str)
    except json.JSONDecodeError as e:
        logger.debug(f"[parse_and_execute] Failed to parse JSON => {e}")
        print(f"SYSTEM: Error parsing JSON => {e}")
        return

    script_title = data.get("title", "Untitled")
    logger.debug(f"[parse_and_execute] Beginning script => {script_title}")
    print(f"SYSTEM: Running script titled '{script_title}' (blocking)...")

    actions = data.get("actions", [])
    if not actions:
        logger.debug("[parse_and_execute] No actions found in script.")
        print("SYSTEM: No actions to perform. Script is empty.")
        return

    # We'll import these on demand to avoid circular references
    from luna.console_functions import cmd_create_room
    from luna.console_functions import cmd_invite_user

    # 1) We'll keep a small map of "room_name" -> "room_id"
    #    so if user typed "myTreetop", we can transform that into e.g. "!abc123:localhost".
    name_to_id_map = {}

    # Regex to capture something like:
    # "SYSTEM: Created room 'myTreetop' => !abc123:localhost"
    room_id_pattern = re.compile(
        r"Created room '(.+)' => (![A-Za-z0-9]+:[A-Za-z0-9\.\-]+)"
    )

    for i, action_item in enumerate(actions, start=1):
        action_type = action_item.get("type")
        args_dict = action_item.get("args", {})

        logger.debug(f"[parse_and_execute] Action #{i}: {action_type}, args={args_dict}")
        print(f"SYSTEM: [#{i}] Executing '{action_type}' with args={args_dict}...")

        if action_type == "create_room":
            # e.g. "myTreetop" --private
            room_name = args_dict.get("room_name", "UntitledRoom")
            is_private = args_dict.get("private", False)

            if is_private:
                arg_string = f"\"{room_name}\" --private"
            else:
                arg_string = f"\"{room_name}\""

            # We capture the console output by temporarily redirecting stdout,
            # or we can rely on the user to see "Created room 'X' => !id".
            # For simplicity, let's just parse the log lines after cmd_create_room finishes.
            original_stdout_write = None
            output_lines = []

            def custom_write(s):
                output_lines.append(s)
                if original_stdout_write:
                    original_stdout_write(s)

            import sys
            if sys.stdout.write != custom_write:  # Only override once
                original_stdout_write = sys.stdout.write
                sys.stdout.write = custom_write

            # 1a) Create the room (blocking call)
            cmd_create_room(arg_string, loop)

            # force a sync here
            from luna.luna_functions import DIRECTOR_CLIENT
            future = asyncio.run_coroutine_threadsafe(DIRECTOR_CLIENT.sync(timeout=1000), loop)
            future.result()
          
            # 1b) Restore stdout
            sys.stdout.write = original_stdout_write

            # 1c) Parse the lines for the created room ID
            for line in output_lines:
                match = room_id_pattern.search(line)
                if match:
                    captured_name = match.group(1)  # e.g. myTreetop
                    captured_id = match.group(2)    # e.g. !abc123:localhost
                    if captured_name == room_name:
                        name_to_id_map[room_name] = captured_id
                        print(f"SYSTEM: Mapped '{room_name}' => '{captured_id}'")

            # 1d) Sleep or forced sync to ensure the user is recognized
            time.sleep(1.0)
            # Optionally: you could call a forced sync here.

        elif action_type == "invite_user":
            user_id = args_dict.get("user_id")
            user_room = args_dict.get("room_id_or_alias")

            # If user_room is in our name_to_id_map, replace it with the real ID
            if user_room in name_to_id_map:
                real_id = name_to_id_map[user_room]
                print(f"SYSTEM: Translating '{user_room}' -> '{real_id}' for invitation.")
                user_room = real_id

            arg_string = f"{user_id} {user_room}"
            cmd_invite_user(arg_string, loop)
            time.sleep(2.0)

        else:
            logger.debug(f"[parse_and_execute] Unknown action type: {action_type}")
            print(f"SYSTEM: Unrecognized action '{action_type}'. Skipping.")

    logger.debug("[parse_and_execute] Script completed.")
    print("SYSTEM: Script execution complete (blocking).")
