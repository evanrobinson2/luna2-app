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

from luna.luna_command_extensions.cmd_summarize import cmd_summarize
from luna.luna_command_extensions.image_helpers import direct_upload_image
from luna.luna_command_extensions.spawn_persona import cmd_spawn
from luna.luna_command_extensions.create_room2 import create_room2_command
from luna.luna_command_extensions.spawn_ensemble import spawn_ensemble_command
from luna.luna_command_extensions.assemble_command import assemble_command
from luna.luna_command_extensions.command_helpers import _set_power_level
from luna.luna_personas import read_bot, update_bot

CONFIG_PATH = "data/config/config.yaml"

# Import your existing 'generate_image' function
from luna.ai_functions import generate_image
# If you have a direct_upload_image helper, import it too:

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
    # 2) Generate the image via your existing ai_functions.generate_image()
    #    => returns a public image URL
    # -----------------------------------------------------------------
    try:
        image_url = await generate_image(user_prompt, size="1024x1024")
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
            return f"Image posted successfully! Prompt: '{user_prompt}'"
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
            temperature=0.7
        )
        logger.debug("[luna_gpt] GPT response: %s", gpt_response)

        # 4) Return the plain-text response to the caller
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
# COMMAND DISPATCHER
# -------------------------------------------------------------
async def handle_console_command(bot_client: AsyncClient, room_id: str, message_body: str, sender: str, event: any) -> str:
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

    elif command_name == "create_room2":
        # We want (bot_client, invoking_room_id, event.event_id, raw_args, sender)
        if not args:
            return (
                "Usage:\n"
                "!create_room2 --name=<localpart> [--invite=@user1:localhost,@user2:localhost] "
                "[--set_avatar=true] [--additional_flag='<json>'] \"<prompt>\"\n\n"
                "Examples:\n"
                "!create_room2 --name=bridgedeck \"A futuristic starship bridge\"\n"
                "!create_room2 --name=researchlab --invite=@dr_koratel:localhost --set_avatar=true "
                "\"A cutting-edge science facility on the frontier\"\n\n"
                "Details:\n"
                "  --name=<localpart>     Localpart for the new room alias, e.g. 'bridge' => #bridge:localhost.\n"
                "  --invite=<list>        Comma-separated user IDs to invite, e.g. @ensignlira:localhost.\n"
                "  --set_avatar=true      If set to 'true', generate & set a room avatar from the prompt.\n"
                "  --additional_flag='<json>'  JSON object with extra style or metadata, e.g. {\"genre\":\"starfleet\"}.\n"
                "  \"<prompt>\"           The final positional argument describing the room’s theme/context.\n"
            )
        raw_args_str = " ".join(args)
        await command_func(bot_client, room_id, event.event_id, raw_args_str, sender)
        return None
    
    elif command_name == "spawn_ensemble":
        # This command wants (bot_client, room_id, event_id, raw_args, sender).
        # If user didn't provide any leftover tokens, show usage:
        if not args:
            return (
                "Usage: !spawn_ensemble \"<high-level group instructions>\"\n\n"
                "Example:\n"
                "!spawn_ensemble \"We need 3 cunning Orion Syndicate spies, each with a unique codename.\""
            )
        # Rejoin leftover tokens into one string. 
        raw_args_str = " ".join(args)
        # Call the ensemble function. It returns None (all output is in-thread).
        await command_func(bot_client, room_id, event.event_id, raw_args_str, sender)
        return None

    elif command_name == "assemble":
        # If user typed just "!assemble" with no leftover tokens, show usage.
        if not args:
            return (
                "Usage: !assemble \"<description>\"\n\n"
                "Example:\n"
                "!assemble \"A crack squad of assassins, bring them to my headquarters\"\n"
                "GPT will generate: roomLocalpart, roomPrompt, 1-3 persona descriptors.\n"
            )
        raw_args_str = " ".join(args)
        await command_func(bot_client, room_id, event.event_id, raw_args_str, sender)
        return None

    elif command_name == "set_avatar":
        # We expect exactly two arguments: <localpart> and <mxc_uri_or_mediaID>
        if len(args) < 2:
            return "Usage: !set_avatar <localpart> <mxc_uri_or_mediaID>"
        
        localpart = args[0]
        mxc_or_media_id = args[1]

        # Pass both arguments as a single string to cmd_set_avatar
        args_string = f"{localpart} {mxc_or_media_id}"
        return await command_func(args_string)


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

    elif command_name == "summarize":

        if not args:
            return "Usage: !summarize <prompt>"

        user_prompt = " ".join(args)
        # We'll call run_summarize_pipeline(...) but not return anything; 
        # it posts results directly in the thread.

        # Because handle_console_command is an async function, we can do:
        from luna.luna_command_extensions.summarize_pipeline import run_summarize_pipeline

        # We do not "return" the summary, because we want to post partial/final messages 
        # in the same thread. So we just schedule it.
        await run_summarize_pipeline(
            bot_client, 
            room_id,
            event.event_id,  # or pass in if you have it
            user_prompt,
            bot_localpart="lunabot"
        )

        # Possibly return a short "Sure, summarizing now..." or just empty
        return None  # The user will see the actual summary in-thread

    elif command_name == "summarize_depreciated":
        # If user typed just "!summarize" with no leftover tokens, show usage
        if not args:
            return "Usage: !summarize <prompt>"

        # Otherwise, join all leftover tokens into one string
        prompt_str = " ".join(args)

        # Call the summarize function, passing bot_client, room_id, and the joined prompt
        return await command_func(bot_client, room_id, prompt_str)
    
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

async def cmd_set_avatar(args: str) -> str:
    """
    Usage:
      set_avatar <localpart> <mxc_uri_or_mediaID>

    Examples:
      set_avatar ghostbot mxc://localhost/HASH123
      set_avatar ghostbot HASH123

    This command:
      1) Looks up the persona data for @<localpart>:localhost to get password, etc.
      2) If we already have an ephemeral bot client loaded, use it; otherwise ephemeral-login.
      3) If the second argument is a raw media ID (no 'mxc://'), we prepend 'mxc://localhost/'.
      4) Calls .set_avatar(<mxc URI>).
      5) Also updates the persona's "portrait_url" trait in personalities.json (so it persists).
      6) Returns a success or error message.
    """
    tokens = shlex.split(args)
    if len(tokens) < 2:
        return "Usage: set_avatar <localpart> <mxc_uri_or_mediaID>"

    localpart = tokens[0]
    raw_avatar_arg = tokens[1]

    # 1) Build the final mxc URI
    if raw_avatar_arg.startswith("mxc://"):
        mxc_uri = raw_avatar_arg
    else:
        # Assume it's just the media ID, e.g. 'jyTMtUvNgbtLcKIvJnoQQtTj'
        # Prepend the local domain name. Adjust if your domain is not 'localhost'.
        mxc_uri = f"mxc://localhost/{raw_avatar_arg}"

    # 2) Read persona to get password, confirm it exists
    full_user_id = f"@{localpart}:localhost"
    persona = read_bot(full_user_id)
    if not persona:
        return f"No persona found for {full_user_id}. Please create one first."

    password = persona.get("password")
    if not password:
        return f"Persona for {full_user_id} has no password stored. Can't ephemeral-login."

    # 3) Attempt to find an existing ephemeral client in your BOTS dict, or ephemeral-login
    #    We'll do a minimal approach: if it's not in BOTS, ephemeral login
    from luna.core import BOTS
    bot_client = BOTS.get(localpart)

    if not bot_client:
        logger.debug(f"[set_avatar] No ephemeral client for '{localpart}' in BOTS.")
    else:
        logger.debug(f"[set_avatar] Found existing ephemeral client for '{localpart}' in BOTS.")

    # 4) Now set the avatar
    try:
        await bot_client.set_avatar(mxc_uri)
    except Exception as e:
        logger.exception("Error setting avatar =>")
        return f"Error setting avatar => {e}"

    # 5) Update the persona's traits to store 'portrait_url' or something similar
    updated_traits = persona.get("traits", {})
    updated_traits["portrait_url"] = mxc_uri
    update_bot(
        full_user_id,
        {
            "traits": updated_traits
        }
    )

    return f"Set avatar for {full_user_id} => {mxc_uri}"

# -------------------------------------------------------------
# COMMAND ROUTER
# -------------------------------------------------------------
COMMAND_ROUTER = {
    "create_room": create_room,    # async
    "create_room2": create_room2_command,
    "invite_user": invite_user,    # async
    "list_rooms":  list_rooms,     # async
    "help":        help_command,   # async
    "set_param":   set_param,      # sync
    "get_param":   get_param,      # sync,
    "list_params": list_params,
    "draw":        draw_command,   # now posts the actual image
    "luna":        luna_gpt,
    "spawn":       cmd_spawn,
    "spawn_ensemble": spawn_ensemble_command,
    "set_avatar":  cmd_set_avatar,
    "assemble":     assemble_command,
    "summarize":   cmd_summarize
}