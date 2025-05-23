# create_room2.py

import luna.GLOBALS as g
import asyncio
import json
import logging
import shlex
import os
import time
import requests
from typing import Optional, Dict, Any

from nio import AsyncClient, RoomSendResponse
from nio.api import RoomVisibility
from nio.responses import (
    RoomCreateResponse,
    RoomCreateError,
    RoomSendResponse as NioRoomSendResponse
)

# Import your helper functions
from luna.luna_command_extensions.command_helpers import (
    _post_in_thread,
    _keep_typing,
    _set_power_level
)
from luna.ai_functions import generate_image  # or generate_image_save_and_post
from luna.luna_command_extensions.image_helpers import direct_upload_image

logger = logging.getLogger(__name__)

async def create_room2_command(
    bot_client: AsyncClient,
    invoking_room_id: str,
    parent_event_id: str,
    raw_args: str,
    sender: str
) -> None:
    """
    A command that creates a new Matrix room (public) using the specified flags:
      --name=<localpart>
      --invite=@user1:localhost,@user2:localhost
      --set_avatar=true
      --additional_flag='{"key": "..."}'
      <prompt>  (positional argument)

    The final room alias is #<name>:localhost. We set the topic to <prompt>.
    If set_avatar=true, we generate an image from the prompt and set that as the room's avatar.
    We invite any users from --invite=..., plus the command sender, and set the sender to PL100.

    We post partial status updates in-thread (using _post_in_thread).
    In the event of errors, we proceed as best we can, then summarize the results.

    The function uses _keep_typing() to show a typing indicator and cancels it at the end.
    All messages are posted in the same thread as 'parent_event_id'.
    """

    logger.info ("Entered create_room2_command...")
    steps_status = {
        "parse_args": None,
        "room_created": None,
        "set_topic": None,
        "avatar_generated": None,
        "invites_sent": None
    }

    # 1) Start a keep-typing background task
    typing_task = asyncio.create_task(_keep_typing(bot_client, invoking_room_id))

    # Post initial status
    await _post_in_thread(
        bot_client,
        invoking_room_id,
        parent_event_id,
        "<p><strong>Received your create_room2 request.</strong><br/>Processing...</p>",
        is_html=True
    )

    # ----------------------------------------------------------------
    # 2) Parse raw_args
    # ----------------------------------------------------------------
    try:
        args = shlex.split(raw_args)
    except ValueError as e:
        steps_status["parse_args"] = False
        error_msg = f"Error parsing arguments => {e}"
        logger.warning(error_msg)
        await _post_in_thread(
            bot_client,
            invoking_room_id,
            parent_event_id,
            f"<p><strong>Oops!</strong> {error_msg}</p>",
            is_html=True
        )
        typing_task.cancel()
        return

    invite_list = []
    set_avatar_flag = False
    additional_data = {}
    name_localpart: Optional[str] = None
    user_prompt = ""

    remainder = []
    idx = 0
    while idx < len(args):
        token = args[idx]
        if token.startswith("--invite="):
            # e.g. --invite=@user1:localhost,@user2:localhost
            val = token.split("=", 1)[1].strip()
            if val:
                invite_list = [u.strip() for u in val.split(",") if u.strip()]
        elif token.startswith("--set_avatar="):
            val = token.split("=", 1)[1].strip().lower()
            set_avatar_flag = (val == "true")
        elif token.startswith("--additional_flag="):
            raw_json = token.split("=", 1)[1].strip()
            try:
                additional_data = json.loads(raw_json)
            except json.JSONDecodeError as je:
                logger.warning(f"Could not parse additional_flag JSON => {je}")
                additional_data = {}
        elif token.startswith("--name="):
            name_localpart = token.split("=", 1)[1].strip()
        else:
            remainder.append(token)
        idx += 1

    user_prompt = " ".join(remainder).strip()

    # Mark parse_args success or fail
    if not name_localpart:
        steps_status["parse_args"] = False
        err = "Missing required --name= parameter."
        logger.warning(err)
        await _post_in_thread(
            bot_client,
            invoking_room_id,
            parent_event_id,
            f"<p><strong>Error:</strong> {err}</p>",
            is_html=True
        )
        typing_task.cancel()
        return
    else:
        steps_status["parse_args"] = True

    if not user_prompt:
        logger.info("No user prompt was provided. We'll keep going with no specific topic or avatar prompt if requested.")

    # ----------------------------------------------------------------
    # 3) Create the room (public)
    # ----------------------------------------------------------------
    await _post_in_thread(
        bot_client,
        invoking_room_id,
        parent_event_id,
        f"Creating a public room with alias `#{name_localpart}:localhost`...",
        is_html=False
    )

    g.LOGGER.info(f"Creating a public room with alias `#{name_localpart}:localhost`...")
    new_room_id = None
    alias = name_localpart
    try:
        resp = await bot_client.room_create(
            alias=alias,
            name=name_localpart,
            topic=user_prompt,
            visibility=RoomVisibility.public
        )

        if isinstance(resp, RoomCreateError):
            # The library returned an error object
            steps_status["room_created"] = False
            err_msg = (
                f"Room creation error => {resp.message or 'Unknown reason'} "
                f"(status={resp.status_code})"
            )
            logger.error(err_msg)
            await _post_in_thread(
                bot_client,
                invoking_room_id,
                parent_event_id,
                f"<p><strong>Oops!</strong> {err_msg}</p>",
                is_html=True
            )
            typing_task.cancel()
            return

        elif isinstance(resp, RoomCreateResponse):
            # Success
            new_room_id = resp.room_id
            steps_status["room_created"] = True
            await _post_in_thread(
                bot_client,
                invoking_room_id,
                parent_event_id,
                f"Room created successfully! (ID: {new_room_id})",
                is_html=False
            )
        else:
            # Some unexpected type
            steps_status["room_created"] = False
            err_msg = f"Unexpected response type from room_create => {type(resp)}"
            logger.error(err_msg)
            await _post_in_thread(
                bot_client,
                invoking_room_id,
                parent_event_id,
                f"<p><strong>Oops!</strong> {err_msg}</p>",
                is_html=True
            )
            typing_task.cancel()
            return

    except Exception as e:
        steps_status["room_created"] = False
        err = f"Exception while creating room => {e}"
        logger.exception(err)
        await _post_in_thread(
            bot_client,
            invoking_room_id,
            parent_event_id,
            f"<p><strong>Oops!</strong> {err}</p>",
            is_html=True
        )
        typing_task.cancel()
        return

    # ----------------------------------------------------------------
    # 4) (Optional) Reset the topic explicitly, in case user_prompt changed
    # ----------------------------------------------------------------
    if user_prompt and new_room_id:
        try:
            await bot_client.room_put_state(
                new_room_id,
                event_type="m.room.topic",
                state_key="",
                content={"topic": user_prompt}
            )
            steps_status["set_topic"] = True
            await _post_in_thread(
                bot_client,
                invoking_room_id,
                parent_event_id,
                "Topic set to your provided prompt.",
                is_html=False
            )
        except Exception as e:
            steps_status["set_topic"] = False
            logger.warning(f"Could not set topic => {e}")
            await _post_in_thread(
                bot_client,
                invoking_room_id,
                parent_event_id,
                f"Warning: Could not set topic => {e}",
                is_html=False
            )

    # ----------------------------------------------------------------
    # 5) If set_avatar==True, generate & set the room avatar
    # ----------------------------------------------------------------
    if set_avatar_flag and new_room_id:
        steps_status["avatar_generated"] = False
        try:
            final_prompt = user_prompt if user_prompt else "A general chat room."
            style_snippet = ""
            if additional_data:
                style_snippet = " ".join(f"{k}={v}" for k, v in additional_data.items())
            if style_snippet:
                final_prompt = f"{final_prompt} {style_snippet}"

            if len(final_prompt) > 4000:
                logger.debug("Truncating image prompt to 4000 chars.")
                final_prompt = final_prompt[:4000]

            await _post_in_thread(
                bot_client,
                invoking_room_id,
                parent_event_id,
                "Generating a room avatar, please wait...",
                is_html=False
            )

            image_url = await generate_image(final_prompt, size="1024x1024")
            logger.info(f"[create_room2] Received image_url => {image_url}")

            filename = f"data/images/room_avatar_{int(time.time())}.jpg"
            os.makedirs("data/images", exist_ok=True)

            dl_resp = requests.get(image_url)
            dl_resp.raise_for_status()
            with open(filename, "wb") as f:
                f.write(dl_resp.content)

            mxc_url = await direct_upload_image(bot_client, filename, "image/jpeg")

            await bot_client.room_put_state(
                new_room_id,
                event_type="m.room.avatar",
                state_key="",
                content={"url": mxc_url}
            )
            
            steps_status["avatar_generated"] = True
            await _post_in_thread(
                bot_client,
                invoking_room_id,
                parent_event_id,
                "Avatar generated and set successfully!",
                is_html=False
            )
        except Exception as e:
            logger.exception(f"Avatar generation failed => {e}")
            await _post_in_thread(
                bot_client,
                invoking_room_id,
                parent_event_id,
                f"Avatar generation failed: {e}. Continuing...",
                is_html=False
            )
    else:
        steps_status["avatar_generated"] = None  # Means not requested or no room

    # ----------------------------------------------------------------
    # 6) Invite the user who invoked the command + any --invite= list
    # ----------------------------------------------------------------
    steps_status["invites_sent"] = True
    if new_room_id:
        try:
            # Invite the command sender
            inv_resp = await bot_client.room_invite(new_room_id, sender)
            if not (inv_resp and inv_resp.transport_response and inv_resp.transport_response.ok):
                logger.warning(f"Could not invite the command sender {sender} => {inv_resp}")

            # Elevate them to PL100
            await _set_power_level(bot_client, new_room_id, sender, 100)

            # Invite the rest from invite_list
            for user_id in invite_list:
                try:
                    iresp = await bot_client.room_invite(new_room_id, user_id)
                    if not (iresp and iresp.transport_response and iresp.transport_response.ok):
                        logger.warning(f"Could not invite {user_id} => {iresp}")
                except Exception as e:
                    logger.warning(f"Invite failed for {user_id} => {e}")

            await _post_in_thread(
                bot_client,
                invoking_room_id,
                parent_event_id,
                f"Invited {len(invite_list)+1} users. Promoted {sender} to PL100.",
                is_html=False
            )
        except Exception as e:
            steps_status["invites_sent"] = False
            logger.exception(f"Error inviting or promoting => {e}")
            await _post_in_thread(
                bot_client,
                invoking_room_id,
                parent_event_id,
                f"Error inviting or promoting => {e}",
                is_html=False
            )
    else:
        steps_status["invites_sent"] = False
        logger.warning("No valid room_id => skipping invite logic.")

    # ----------------------------------------------------------------
    # 7) Final summary in-thread
    # ----------------------------------------------------------------
    summary_lines = []
    summary_lines.append("<p><strong>Done!</strong> Here’s the outcome:</p><ul>")

    def li(msg): return f"<li>{msg}</li>"

    # parse_args
    if steps_status["parse_args"] is False:
        summary_lines.append(li("Argument parsing => **FAILED**."))
    else:
        summary_lines.append(li("Argument parsing => Success."))

    # room_created
    if steps_status["room_created"]:
        summary_lines.append(li(f"Room created => `#{name_localpart}:localhost`"))
    else:
        summary_lines.append(li("Room creation => **FAILED**."))

    # set_topic
    if steps_status["set_topic"] is True:
        summary_lines.append(li("Topic set => OK."))
    elif steps_status["set_topic"] is False:
        summary_lines.append(li("Topic => **FAILED**."))

    # avatar_generated
    if steps_status["avatar_generated"] is True:
        summary_lines.append(li("Room avatar => generated successfully."))
    elif steps_status["avatar_generated"] is False:
        summary_lines.append(li("Room avatar => attempted, but **FAILED**."))
    elif steps_status["avatar_generated"] is None:
        summary_lines.append(li("Room avatar => not requested."))

    # invites_sent
    if steps_status["invites_sent"]:
        summary_lines.append(li("Invites => OK (sender was also promoted to PL100)."))
    else:
        summary_lines.append(li("Invites => **FAILED** or partial issues."))

    summary_lines.append("</ul>")

    final_html = "\n".join(summary_lines)

    await _post_in_thread(
        bot_client,
        invoking_room_id,
        parent_event_id,
        final_html,
        is_html=True
    )

    # 8) Done. Stop typing, return.
    typing_task.cancel()
    logger.info("[create_room2_command] Completed all steps.")
    return new_room_id

logger = logging.getLogger(__name__)

async def create_room2_node(state: Dict) -> Dict:
    """
    Node that calls create_room2_command, using g.LUNA_CLIENT if no 'bot_client' is provided in state.

    Expects in `state`:
      - raw_args: str, the CLI-style string of arguments. If not provided and dictionary keys
                  (e.g. "--name", "prompt") exist, these will be used to build raw_args.
      - room_id: str, the room ID where the command was invoked (e.g. "!abc123:localhost")
      - parent_event_id: str, the event ID for threading.
      - sender: str, the user's Matrix ID (e.g. "@someone:localhost")
    
    If any of these are missing, the node will attempt to fallback or skip partial features.
    """
    logger.info("Entering create_room2_node...")

    # Retrieve required fields from state
    room_id = state.get("room_id")
    sender = state.get("sender")
    raw_args = state.get("raw_args", "")
    parent_event_id = state.get("parent_event_id", "")

    # Fallback to dictionary values if raw_args is empty.
    if not raw_args and "--name" in state:
        tokens = []
        for key in ["--name", "--set_avatar", "--additional_flag"]:
            if key in state:
                tokens.append(f"{key}={state[key]}")
        # Append a positional argument for the prompt if available.
        if "prompt" in state:
            tokens.append(state["prompt"])
        raw_args = " ".join(tokens)
        state["raw_args"] = raw_args  # Optionally update the state with the constructed raw_args.
        logger.info("Constructed raw_args from state: %r", raw_args)

    g.LOGGER.info(
        "create_room2_node: room_id=%r, sender=%r, raw_args=%r, parent_event_id=%r",
        room_id, sender, raw_args, parent_event_id
    )

    # Fallback to the global LUNA_CLIENT if no bot_client is provided.
    bot_client = state.get("bot_client") or g.LUNA_CLIENT
    if not bot_client:
        err = "No 'bot_client' in state and g.LUNA_CLIENT is None. Can't proceed."
        logger.error(err)
        return {
            "error": err,
            "__next_node__": "chatbot_node"
        }

    logger.debug("Using bot_client: %s", bot_client)
    logger.debug("raw_args: %r", raw_args)

    # Warn if essential fields are missing.
    if not sender:
        logger.warning("Missing 'sender' in state; invites will be skipped.")
    if not room_id:
        logger.warning("Missing 'room_id' in state; in-thread updates will be skipped.")

    # Call the underlying create_room2_command function.
    try:
        await create_room2_command(
            bot_client=bot_client,
            invoking_room_id=room_id,
            parent_event_id=parent_event_id,
            raw_args=raw_args,
            sender=sender
        )
    except Exception as e:
        logger.exception("Exception in create_room2_node: %s", e)
        return {
            "error": str(e),
            "__next_node__": "chatbot_node"
        }

    logger.info("Completed create_room2_node.")
    return {"__next_node__": "chatbot_node"}
