# luna_message_handler.py

import re
import time
import logging
import asyncio
from collections import deque
from nio import RoomMessageText, RoomSendResponse

# Suppose these imports match your project structure:
from luna import bot_messages_store2         # For storing messages in SQLite
import luna.context_helper as context_helper # Your GPT context builder
from luna import ai_functions                # Your GPT call function

logger = logging.getLogger(__name__)

# We match a pattern like :some_command: in the text
COMMAND_REGEX = re.compile(r":([a-zA-Z_]\w*):")

# Keep a short command history to prevent infinite loops or spamming
# Key = sender_id, Value = deque of (commandName, timestamp)
COMMAND_HISTORY_LIMIT = 8
COMMAND_HISTORY_WINDOW = 60.0  # seconds
_command_history = {}

async def handle_luna_message(bot_client, bot_localpart, room, event):
    """
    The single “monolithic” handler for Luna's inbound messages.
    Steps:
      1) Validate inbound => must be RoomMessageText from another sender
      2) Store in DB
      3) Parse commands => :commandName:
      4) If commands are found & allowed => dispatch them. Then skip GPT.
      5) Otherwise => do mention-based or DM-based GPT logic, storing outbound.
    """

    # A) Basic checks
    if not isinstance(event, RoomMessageText):
        return  # only process text messages

    bot_full_id = bot_client.user      # e.g. "@lunabot:localhost"
    if event.sender == bot_full_id:
        logger.debug("Luna ignoring her own message.")
        return

    message_body = event.body or ""
    event_id = event.event_id

    # B) Check duplicates
    existing = bot_messages_store2.get_messages_for_bot(bot_localpart)
    if any(m["event_id"] == event_id for m in existing):
        logger.info(f"[handle_luna_message] Duplicate event_id={event_id}, skipping.")
        return

    # C) Store inbound
    bot_messages_store2.append_message(
        bot_localpart=bot_localpart,
        room_id=room.room_id,
        event_id=event_id,
        sender=event.sender,
        timestamp=event.server_timestamp,
        body=message_body
    )
    logger.debug(f"[handle_luna_message] Stored inbound => event_id={event_id}")

    # D) Parse commands (like :invite_user: or :summon_meta:)
    found_cmds = COMMAND_REGEX.findall(message_body)
    if found_cmds:
        logger.debug(f"Luna sees commands => {found_cmds}")
        skip_gpt = False

        # Rate-limit check
        for cmd_name in found_cmds:
            if not _check_command_rate(event.sender, cmd_name):
                logger.warning(f"Blocking command '{cmd_name}' from {event.sender} due to spam.")
                skip_gpt = True
                break

        if not skip_gpt:
            # Actually handle each command in sequence
            for cmd_name in found_cmds:
                await _dispatch_command(cmd_name, message_body, bot_client, room, event)
            # By design, we skip GPT after commands
            return

    # E) If no command => mention-based or DM-based GPT logic
    participant_count = len(room.users)
    mention_data = event.source.get("content", {}).get("m.mentions", {})
    mentioned_ids = mention_data.get("user_ids", [])
    should_reply = False

    if participant_count == 2:
        # DM => always respond
        should_reply = True
    else:
        # In groups => respond only if our own user ID is mentioned
        if bot_full_id in mentioned_ids:
            should_reply = True

    if not should_reply:
        logger.debug("No mention or DM => ignoring GPT logic.")
        return

    # Build GPT context
    config = {"max_history": 10}
    gpt_context = context_helper.build_context(bot_localpart, room.room_id, config)
    # Optionally load a big system file if you want:
    # e.g. system_text = load_luna_system_prompt("data/luna_system_prompt.md")
    # Then prepend to gpt_context if you prefer. For now, we skip that.

    # Call GPT
    reply_text = await ai_functions.get_gpt_response(
        messages=gpt_context,
        model="gpt-4",
        temperature=0.7,
        max_tokens=300
    )

    # Send GPT reply
    send_resp = await bot_client.room_send(
        room_id=room.room_id,
        message_type="m.room.message",
        content={"msgtype": "m.text", "body": reply_text},
    )
    # Store outbound
    if isinstance(send_resp, RoomSendResponse):
        out_id = send_resp.event_id
        bot_messages_store2.append_message(
            bot_localpart=bot_localpart,
            room_id=room.room_id,
            event_id=out_id,
            sender=bot_full_id,
            timestamp=int(time.time() * 1000),
            body=reply_text
        )
        logger.info(f"Luna posted GPT reply => event_id={out_id}")
    else:
        logger.warning("No event_id from GPT send response => cannot store outbound.")


def _check_command_rate(sender_id: str, cmd_name: str) -> bool:
    """
    Let each user run each command up to 2 times per 60sec. The third attempt is blocked.
    This helps avoid infinite loops or spam if GPT or a user quickly repeats commands.
    """
    now = time.time()
    dq = _command_history.setdefault(sender_id, deque())

    # Clear out old items
    while dq and (now - dq[0][1]) > COMMAND_HISTORY_WINDOW:
        dq.popleft()

    # Count how many times the *same* cmd_name is already in the window
    same_cmd_count = sum(1 for (cmd, t) in dq if cmd == cmd_name)
    if same_cmd_count >= 2:
        return False

    # Otherwise record & allow
    dq.append((cmd_name, now))
    if len(dq) > COMMAND_HISTORY_LIMIT:
        dq.popleft()
    return True


async def _dispatch_command(cmd_name: str, full_msg: str, bot_client, room, event):
    """
    The actual logic for recognized commands.
    If unrecognized, we post a small 'not recognized' message.

    In principle, you can parse arguments from the text (full_msg),
    or store them in a custom syntax or JSON.
    """

    logger.debug(f"Handling command => :{cmd_name}:")

    if cmd_name == "users":
        # Example: list all known user accounts
        from luna.luna_functions import list_users
        users_info = await list_users()
        lines = ["**Current Users**"]
        for u in users_info:
            user_id = u["user_id"]
            admin_flag = " (admin)" if u.get("admin") else ""
            lines.append(f" - {user_id}{admin_flag}")
        text_out = "\n".join(lines)
        await _post(bot_client, room.room_id, text_out)
        return

    elif cmd_name == "channels":
        from luna.luna_functions import list_rooms
        rooms_info = await list_rooms()
        lines = ["**Known Rooms**"]
        for rinfo in rooms_info:
            lines.append(f" - {rinfo['name']} => {rinfo['room_id']}")
        text_out = "\n".join(lines)
        await _post(bot_client, room.room_id, text_out)
        return

    elif cmd_name == "invite_user":
        # Possibly parse the user & room from the message
        # We'll do a placeholder
        # "invite_user" => try to read e.g. :invite_user: @someUser:localhost !room:localhost
        try:
            # (extremely naive parse)
            # find the substring after :invite_user:
            # you can do a real parse or ask user to type JSON, etc.
            leftover = full_msg.split(":invite_user:")[-1].strip()
            # maybe leftover = "@someUser:localhost !someRoom:localhost"
            # but let's do a stub:
            text_out = f"Ok, I'd invite {leftover} if implemented. (stubbed out)."
            await _post(bot_client, room.room_id, text_out)
        except Exception as e:
            logger.exception("Error in invite_user parse => %s", e)
            await _post(bot_client, room.room_id, "invite_user parse error. Check logs.")
        return

    elif cmd_name == "summon_meta":
        # Example: create a single persona from GPT and spawn. 
        # Or parse arguments. For demonstration, let's do a small direct call:
        from luna.luna_command_extensions.create_and_login_bot import create_and_login_bot

        # We'll do a naive approach: leftover text is the 'blueprint'
        leftover = full_msg.split(":summon_meta:")[-1].strip()
        # leftover might contain user instructions describing the persona

        # Now call GPT to produce the JSON
        # Then parse and create the user. This is up to you.
        # We'll just respond that we've recognized the command:
        text_out = f"**Pretending** to summon a persona based on => {leftover}"
        await _post(bot_client, room.room_id, text_out)
        return

    else:
        # Unrecognized
        text_out = f"I see command :{cmd_name}: but I do not know how to handle it."
        await _post(bot_client, room.room_id, text_out)


async def _post(bot_client, room_id: str, text: str):
    """
    Helper to post a text message to the same room.
    """
    try:
        resp = await bot_client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": text},
        )
        if isinstance(resp, RoomSendResponse):
            # not strictly necessary if you don't track Luna's own messages
            pass
    except Exception as e:
        logger.exception("Failed to post message => %s", e)


# (Optional) if you want a function that loads a big system prompt from disk
def load_luna_system_prompt(filepath: str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = f.read()
        logger.debug(f"Loaded system prompt from {filepath} with len={len(data)}")
        return data
    except Exception as e:
        logger.exception("Could not load system prompt => %s", e)
        return ""
