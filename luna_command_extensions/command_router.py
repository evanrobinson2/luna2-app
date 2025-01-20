"""
command_router.py

Defines:
  - Command functions (create_room, invite_user, etc.) each with docstrings.
  - A help command that builds an HTML table from these docstrings.
  - A router that maps command strings to their respective functions.
  - The handle_console_command() dispatcher that interprets and calls them.
"""

import logging
import asyncio
import inspect
import shlex
import os
import time
import requests
from nio import AsyncClient, RoomSendResponse
import yaml
import os

from luna.luna_command_extensions.spawn_persona import cmd_spawn

CONFIG_PATH = "data/config/config.yaml"

# Import your existing 'generate_image' function
from luna.ai_functions import generate_image
# If you have a direct_upload_image helper, import it too:
from luna.luna_command_extensions.luna_message_handler import direct_upload_image

logger = logging.getLogger(__name__)

# -------------------------------------------------------------
# GLOBAL PARAM STORE (for set_param / get_param)
# -------------------------------------------------------------
GLOBAL_PARAMS = {}

# -------------------------------------------------------------
# COMMAND FUNCTIONS
# -------------------------------------------------------------

async def create_room(
    bot_client: AsyncClient,
    sender: str,
    localpart: str,
    topic: str = None,
    is_public: bool = True,
) -> str:
    """
    Usage:
      !create_room <localpart> [topic="..."] [public|private]

    Create a new room using the given localpart (e.g. '#myroom').
    Invites the sender with power level 100, sets optional topic,
    and sets visibility (public or private).
    """
    domain = "localhost"
    full_alias = f"{localpart}:{domain}"
    visibility = "public" if is_public else "private"

    try:
        logger.info(f"[create_room] Creating room alias={full_alias}, topic={topic}, visibility={visibility}")
        resp = await bot_client.room_create(
            visibility=visibility,
            alias=full_alias,
            name=localpart.strip("#"),  # display name
            topic=topic,
        )
        if not resp.room_id:
            return f"Error: Could not create room {full_alias} => {resp}"
        room_id = resp.room_id

        # Invite the user who issued the command
        invite_resp = await bot_client.room_invite(room_id, sender)
        if not (invite_resp and invite_resp.transport_response.ok):
            return f"Warning: Could not invite {sender} => {invite_resp}"

        # Elevate them to PL100
        await _set_power_level(bot_client, room_id, sender, 100)
        return f"Room created: {full_alias} (ID: {room_id}), invited {sender} with PL100."
    except Exception as e:
        logger.exception("[create_room] Error =>")
        return f"Error creating room => {e}"


async def _set_power_level(bot_client: AsyncClient, room_id: str, user_id: str, power: int):
    """Helper to set a user's power level in a given room."""
    state_resp = await bot_client.room_get_state_event(room_id, "m.room.power_levels", "")
    current_content = state_resp.event.source.get("content", {})

    users_dict = current_content.get("users", {})
    users_dict[user_id] = power
    current_content["users"] = users_dict

    await bot_client.room_send_state(
        room_id=room_id,
        event_type="m.room.power_levels",
        state_key="",
        content=current_content,
    )


async def invite_user(bot_client: AsyncClient, user_id: str, room_localpart: str) -> str:
    """
    Usage:
      !invite_user <user_id> <room_localpart>

    Invite the given user to the specified room localpart
    (e.g. '#observation_deck').
    """
    domain = "localhost"
    full_alias = f"{room_localpart}:{domain}"

    try:
        resolve_resp = await bot_client.room_resolve_alias(full_alias)
        if not resolve_resp.room_id:
            return f"Error: Could not resolve alias => {full_alias}"
        room_id = resolve_resp.room_id

        invite_resp = await bot_client.room_invite(room_id, user_id)
        if invite_resp and invite_resp.transport_response.ok:
            return f"Invited {user_id} to {full_alias} (ID: {room_id})."
        else:
            return f"Error: Could not invite => {invite_resp}"
    except Exception as e:
        logger.exception("[invite_user] Error =>")
        return f"Error => {e}"


async def list_rooms(bot_client: AsyncClient) -> str:
    """
    Usage:
      !list_rooms

    Return a list of rooms the bot is currently in, formatted as an HTML table,
    with columns in the order: (Name, Alias, Room ID).
    """
    # Collect info in a list of (room_id, alias, name)
    room_info = []
    for room_id, room_obj in bot_client.rooms.items():
        alias = getattr(room_obj, "canonical_alias", None) or ""
        name = room_obj.name or ""
        room_info.append((room_id, alias, name))

    if not room_info:
        return "<p>No rooms found.</p>"

    # Build a table with columns: Name, Alias, Room ID
    rows = []
    for r_id, r_alias, r_name in room_info:
        row_html = (
            "<tr>"
            f"<td>{r_name}</td>"    # Name
            f"<td>{r_alias}</td>"   # Alias
            f"<td>{r_id}</td>"      # Room ID
            "</tr>"
        )
        rows.append(row_html)

    # Combine rows into a table
    table_html = (
        "<p><strong>Rooms the bot is currently in:</strong></p>"
        "<table border='1' style='border-collapse:collapse; margin:1em 0;'>"
        "<thead>"
        "<tr><th>Name</th><th>Alias</th><th>Room ID</th></tr>"
        "</thead>"
        "<tbody>"
        + "".join(rows) +
        "</tbody>"
        "</table>"
    )

    return table_html


async def draw_command(bot_client: AsyncClient, room_id: str, user_prompt: str) -> str:
    """
    Usage:
      !draw <prompt>

    Generates an image from the user's prompt, appending a global
    style (found in GLOBAL_PARAMS['global_draw_prompt_appendix']) if present,
    then uploads the image to Matrix and sends it to the given room.
    Returns a success or error message.
    """
    # -----------------------------------------------------------------
    # 1) Merge the global style with the user's prompt
    # -----------------------------------------------------------------
    style = GLOBAL_PARAMS.get("global_draw_prompt_appendix", "").strip()
    if style:
        final_prompt = f"{user_prompt.strip()}. {style}"
    else:
        final_prompt = user_prompt.strip()

    # -----------------------------------------------------------------
    # 2) Generate the image via your existing ai_functions.generate_image()
    #    => returns a public image URL
    # -----------------------------------------------------------------
    try:
        image_url = generate_image(final_prompt, size="1024x1024")
    except Exception as e:
        logger.exception("[draw_command] Error generating image.")
        return f"Error generating image => {e}"

    logger.info("[draw_command] Image generated, URL => %s", image_url)

    # -----------------------------------------------------------------
    # 3) Download the image to disk
    # -----------------------------------------------------------------
    try:
        logger.debug("[draw_command] Downloading image from %s", image_url)
        os.makedirs("data/images", exist_ok=True)
        timestamp = int(time.time())
        filename = f"data/images/generated_image_{timestamp}.jpg"

        dl_resp = requests.get(image_url)
        dl_resp.raise_for_status()

        with open(filename, "wb") as f:
            f.write(dl_resp.content)

        logger.debug("[draw_command] Image saved to %s", filename)
    except Exception as e:
        logger.exception("[draw_command] Error downloading image.")
        return f"Error downloading the image => {e}"

    # -----------------------------------------------------------------
    # 4) Upload to Matrix (direct_upload_image or client.upload)
    # -----------------------------------------------------------------
    try:
        logger.debug("[draw_command] Uploading image to Matrix.")
        mxc_url = await direct_upload_image(bot_client, filename, "image/jpeg")
        logger.debug("[draw_command] Upload success => %s", mxc_url)
    except Exception as e:
        logger.exception("[draw_command] Error uploading image to Matrix.")
        return f"Error uploading image => {e}"

    # -----------------------------------------------------------------
    # 5) Send the m.image event to the room
    # -----------------------------------------------------------------
    try:
        file_size = os.path.getsize(filename)
        image_content = {
            "msgtype": "m.image",
            "body": os.path.basename(filename),
            "url": mxc_url,
            "info": {
                "mimetype": "image/jpeg",
                "size": file_size,
                "w": 1024,
                "h": 1024
            },
        }
        logger.debug("[draw_command] Sending image content => %s", image_content)

        img_response = await bot_client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content=image_content,
        )

        if isinstance(img_response, RoomSendResponse):
            return f"Image posted successfully! Prompt: '{final_prompt}'"
        else:
            logger.warning("[draw_command] Unexpected response => %s", img_response)
            return "Failed to send the image to the room."
    except Exception as e:
        logger.exception("[draw_command] Error sending the image event.")
        return f"Error sending the image => {e}"

def get_param(param_name: str) -> str:
    """
    1) Check in-memory GLOBAL_PARAMS first (quick read).
    2) If not found, load from config.yaml -> 'globals' -> param_name.
    3) Return the string value or a "not found" message.
    """
    # Check in-memory
    if param_name in GLOBAL_PARAMS:
        return str(GLOBAL_PARAMS[param_name])

    # Otherwise, load from config
    cfg = load_config()
    globals_section = cfg.get("globals", {})
    val = globals_section.get(param_name)
    if val is not None:
        # Store it in memory so next time we don't have to reload
        GLOBAL_PARAMS[param_name] = val
        return str(val)

    return f"No param set for '{param_name}'."

def set_param(param_name: str, value: str) -> str:
    """
    1) Update in-memory GLOBAL_PARAMS.
    2) Also persist to config.yaml in the 'globals' section.
    3) Return a confirmation message.
    """
    # Update in-memory
    GLOBAL_PARAMS[param_name] = value

    # Persist to config.yaml
    cfg = load_config()
    if "globals" not in cfg:
        cfg["globals"] = {}
    cfg["globals"][param_name] = value
    save_config(cfg)

    return f"Set {param_name} => {value}"

async def help_command(*args, **kwargs) -> str:
    """
    Usage:
      !help

    Show help for all available commands, displaying usage and description
    in a beautiful HTML table.
    """
    table_html = build_help_table()
    return table_html

def list_params() -> str:
    """
    Usage:
      !list_params

    Lists all key-value pairs in the GLOBAL_PARAMS dictionary, formatted as an HTML table.
    """
    if not GLOBAL_PARAMS:
        return "<p>No parameters have been set.</p>"

    rows = []
    for key, val in GLOBAL_PARAMS.items():
        row = (
            "<tr>"
            f"<td>{key}</td>"
            f"<td>{val}</td>"
            "</tr>"
        )
        rows.append(row)

    table_html = (
        "<p><strong>Current Global Parameters</strong></p>"
        "<table border='1' style='border-collapse:collapse; margin:1em 0;'>"
        "<thead><tr><th>Param Name</th><th>Value</th></tr></thead>"
        "<tbody>"
        + "".join(rows) +
        "</tbody></table>"
    )

    return table_html

async def luna_gpt(bot_client: AsyncClient, room_id: str, raw_args: str) -> str:
    """
    Usage:
      !luna <prompt>

    Sends the user's prompt through GPT with a full context build for Luna,
    using `context_helper.build_context`. Returns GPT's plain-text response.

    Handles both quoted and non-quoted inputs by stripping leading/trailing quotes.
    Examples:
      !luna "Hello world"
      !luna Hello world
    """
    # 1) Strip leading/trailing quotes or whitespace.
    #    If raw_args is something like '"Hello world"', we remove the quotes.
    #    If it's unquoted (e.g. 'Hello world'), we still trim leading/trailing spaces.
    prompt = raw_args.strip().strip('"\'')
    if not prompt:
        return "Usage: !luna <prompt>"

    from luna.context_helper import build_context  # Ensure correct import path
    from luna.ai_functions import get_gpt_response  # Ensure correct import path

    # 2) Build Luna’s GPT context for this room
    try:
        context_config = {"max_history": 20}
        gpt_context = build_context("lunabot", room_id, context_config)
        gpt_context.append({"role": "user", "content": prompt})

        logger.debug("[luna_gpt] GPT context built: %s", gpt_context)

        # 3) Call GPT with the context and user’s final prompt
        gpt_response = await get_gpt_response(
            messages=gpt_context,
            model="chatgpt-4o-latest",
            temperature=0.7,
            max_tokens=300
        )
        logger.debug("[luna_gpt] GPT response: %s", gpt_response)

        # 4) Return the plain-text response to the caller
        return gpt_response

    except Exception as e:
        logger.exception("[luna_gpt] Error generating response:")
        return f"Error generating response: {e}"


async def luna_gpt_dep(bot_client: AsyncClient, room_id: str, args: str) -> str:
    """
    Usage:
      !luna <prompt>

    Sends the user's prompt through GPT with a full context build for Luna,
    using `context_helper.build_context`. Returns GPT's plain-text response.
    """
    from luna.context_helper import build_context  # Ensure correct import path
    from luna.ai_functions import get_gpt_response  # Ensure correct import path

    if not args:
        return "Usage: !luna <prompt>"

    # 1) Build Luna's context for this room
    try:
        context_config = {"max_history": 20}
        gpt_context = build_context("lunabot", room_id, context_config)
        gpt_context.append({"role": "user", "content": args})

        logger.debug("[luna_gpt] GPT context built: %s", gpt_context)

        # 2) Call GPT with the context and user's prompt
        gpt_response = await get_gpt_response(
            messages=gpt_context,
            model="chatgpt-4o-latest",
            temperature=0.7,
            max_tokens=300
        )
        logger.debug("[luna_gpt] GPT response: %s", gpt_response)

        return gpt_response

    except Exception as e:
        logger.exception("[luna_gpt] Error generating response:")
        return f"Error generating response: {e}"


# -------------------------------------------------------------
# BUILD HELP TABLE
# -------------------------------------------------------------
def build_help_table() -> str:
    """
    Dynamically build an HTML table showing [Command | Usage | Description]
    by parsing docstrings from each command.
    """
    rows = []
    sorted_commands = sorted(COMMAND_ROUTER.items())

    for cmd_name, func in sorted_commands:
        usage, description = parse_command_doc(func)
        row = (
            f"<tr>"
            f"<td><b>{cmd_name}</b></td>"
            f"<td>{usage}</td>"
            f"<td>{description}</td>"
            f"</tr>"
        )
        rows.append(row)

    table = (
        "<table border='1' style='border-collapse: collapse; margin:1em 0;'>"
        "<thead><tr><th>Command</th><th>Usage</th><th>Description</th></tr></thead>"
        "<tbody>"
        + "".join(rows) +
        "</tbody></table>"
    )

    html = (
        "<p><strong>Available Commands</strong></p>"
        + table
    )
    return html


def parse_command_doc(func) -> tuple[str, str]:
    """
    Extract usage and a short description from a function's docstring.
    Expects docstring lines like:
        Usage:
          !command_name <args>

        A longer description...
    """
    doc = inspect.getdoc(func) or ""
    lines = doc.splitlines()
    usage_line = ""
    description_lines = []

    for line in lines:
        line_stripped = line.strip()
        if line_stripped.lower().startswith("usage:"):
            usage_line = line_stripped[len("usage:"):].strip()
        else:
            description_lines.append(line_stripped)

    usage = usage_line
    description = " ".join(description_lines).strip()
    return usage, description


# -------------------------------------------------------------
# COMMAND ROUTER
# -------------------------------------------------------------
COMMAND_ROUTER = {
    "create_room": create_room,    # async
    "invite_user": invite_user,    # async
    "list_rooms":  list_rooms,     # async
    "help":        help_command,   # async
    "set_param":   set_param,      # sync
    "get_param":   get_param,      # sync,
    "list_params": list_params,
    "draw":        draw_command,   # now posts the actual image
    "luna":        luna_gpt,
    "spawn":       cmd_spawn
}


# -------------------------------------------------------------
# COMMAND DISPATCHER
# -------------------------------------------------------------
async def handle_console_command(bot_client: AsyncClient, room_id: str, message_body: str, sender: str) -> str:
    """
    Parse the message (which starts with '!'), extract command name & args,
    invoke the appropriate function from COMMAND_ROUTER, and return the result.
    Now we pass 'room_id' into commands like 'draw_command' so it can post images.
    """
    cmd_line = message_body[1:].strip()

    try:
        parts = shlex.split(cmd_line)
    except ValueError as e:
        return f"SYSTEM: Error parsing command => {e}"

    if not parts:
        return "SYSTEM: No command entered."

    command_name = parts[0].lower()
    args = parts[1:]

    if command_name not in COMMAND_ROUTER:
        return f"SYSTEM: Unrecognized command '{command_name}'."

    command_func = COMMAND_ROUTER[command_name]

    # Dispatch to the correct function
    if command_name == "create_room":
        if not args:
            return "Usage: !create_room <localpart> [topic=\"...\"] [public|private]"
        localpart = args[0]
        topic = None
        is_public = True

        for extra in args[1:]:
            if extra.startswith("topic="):
                topic_val = extra.split("=", 1)[1].strip('"')
                topic = topic_val
            elif extra.lower() in ["public", "private"]:
                is_public = (extra.lower() == "public")

        return await command_func(bot_client, sender, localpart, topic, is_public)

    elif command_name == "invite_user":
        if len(args) < 2:
            return "Usage: !invite_user <user_id> <room_localpart>"
        user_id = args[0]
        localpart = args[1]
        return await command_func(bot_client, user_id, localpart)

    elif command_name == "list_params":
        # No arguments expected
        if args:
            return "Usage: !list_params  (no arguments needed)"
        return command_func()

    elif command_name == "luna":
        if not args:
            return "Usage: !luna <prompt>"
        prompt = " ".join(args)
        return await command_func(bot_client, room_id, prompt)
    
    elif command_name == "draw":
        # Now pass in the 'room_id' so we can post the image there
        if not args:
            return "Usage: !draw <prompt>"
        prompt = " ".join(args)
        return await command_func(bot_client, room_id, prompt)

    elif command_name == "list_rooms":
        return await command_func(bot_client)

    elif command_name == "spawn":
        if not args:
            return "Usage: !spawn <descriptor>"
        descriptor = " ".join(args)
        return await command_func(bot_client, descriptor)

    elif command_name == "help":
        return await command_func()

    elif command_name == "set_param":
        if len(args) < 2:
            return "Usage: !set_param <param_name> <value>"
        param_name = args[0]
        value = " ".join(args[1:])
        return command_func(param_name, value)

    elif command_name == "get_param":
        if len(args) < 1:
            return "Usage: !get_param <param_name>"
        param_name = args[0]
        return command_func(param_name)

    # fallback if not handled above
    return f"SYSTEM: Command '{command_name}' is recognized but not handled."

def load_config() -> dict:
    """
    Loads the YAML config from disk into a dict.
    Returns an empty dict if file not found or invalid.
    """
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def save_config(config_data: dict) -> None:
    """
    Writes the config_data dict back to config.yaml, overwriting existing content.
    """
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_data, f)