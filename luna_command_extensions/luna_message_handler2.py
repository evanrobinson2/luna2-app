# luna_message_handler2.py

import os
import time
import json
import logging
import random
import asyncio
import sys
import io
import html
import requests
import urllib.parse
import aiohttp
from nio import (
    AsyncClient,
    RoomMessageText,
    RoomSendResponse,
)

from luna import bot_messages_store
from luna.console_functions import COMMAND_ROUTER
from luna.context_helper import build_context
from luna.ai_functions import get_gpt_response
from luna.luna_command_extensions.luna_message_handler import direct_upload_image  # Reuse the direct_upload_image helper

logger = logging.getLogger(__name__)

def run_console_command_in_memory(cmd_line: str) -> str:
    """
    Intercepts sys.stdout to capture console_functions' prints.
    Calls the appropriate function in COMMAND_ROUTER and returns all output as a single string.
    Supports both sync and async commands.
    """
    old_stdout = sys.stdout
    output_buffer = io.StringIO()

    try:
        sys.stdout = output_buffer
        parts = cmd_line.strip().split(maxsplit=1)
        if not parts:
            print("SYSTEM: No command entered.")
            return output_buffer.getvalue()

        command_name = parts[0].lower()
        argument_string = parts[1] if len(parts) > 1 else ""

        if command_name not in COMMAND_ROUTER:
            print(f"SYSTEM: Unrecognized command '{command_name}'.")
            return output_buffer.getvalue()

        command_func = COMMAND_ROUTER[command_name]
        loop = asyncio.get_event_loop()

        # If the command is an async function, await it;
        # otherwise call it as a normal sync function.
        if asyncio.iscoroutinefunction(command_func):
            loop.run_until_complete(command_func(argument_string, loop))
        else:
            command_func(argument_string, loop)

    except Exception as e:
        logger.exception("Error in run_console_command_in_memory => %s", e)
        print(f"SYSTEM: Command failed => {e}")
    finally:
        sys.stdout = old_stdout

    return output_buffer.getvalue()


def run_console_command_in_memory_dep(cmd_line: str) -> str:
    """
    Intercepts sys.stdout to capture console_functions' prints.
    Calls the appropriate function in COMMAND_ROUTER and returns all output as a single string.
    """
    old_stdout = sys.stdout
    output_buffer = io.StringIO()
    try:
        sys.stdout = output_buffer
        parts = cmd_line.strip().split(maxsplit=1)
        if not parts:
            print("SYSTEM: No command entered.")
        else:
            command_name = parts[0].lower()
            argument_string = parts[1] if len(parts) > 1 else ""

            if command_name in COMMAND_ROUTER:
                COMMAND_ROUTER[command_name](argument_string, asyncio.get_running_loop())
            else:
                print(f"SYSTEM: Unrecognized command '{command_name}'.")
    except Exception as e:
        logger.exception("Error in run_console_command_in_memory => %s", e)
        print(f"SYSTEM: Command failed => {e}")
    finally:
        sys.stdout = old_stdout

    return output_buffer.getvalue()

async def handle_luna_message2(bot_client: AsyncClient, bot_localpart: str, room, event):
    """
    Enhanced message handler with the following features:
      - Typing indicators with random delays.
      - Prevents duplicate responses.
      - Handles commands starting with '!' using existing console commands.
      - Defaults to GPT responses for unrecognized commands or regular messages.
      - Maintains thorough logging throughout the process.
    """
    bot_full_id = bot_client.user

    # -- 1) Ignore messages from self
    if event.sender == bot_full_id:
        logger.debug("Ignoring message from myself: %s", event.sender)
        return

    # -- 2) Ensure it's a text message
    if not isinstance(event, RoomMessageText):
        logger.debug("Ignoring non-text message.")
        return

    message_body = event.body or ""
    logger.info("Received message in room=%s from=%s => %r",
                room.room_id, event.sender, message_body)

    # -- 3) Check for duplicates to prevent duplication and proliferation of responses to the same message
    existing_msgs = bot_messages_store.get_messages_for_bot(bot_localpart)
    if any(m["event_id"] == event.event_id for m in existing_msgs):
        logger.info("Event %s already in DB => skipping response.", event.event_id)
        return

    # -- 4) Store inbound message now that we know it's unique
    bot_messages_store.append_message(
        bot_localpart=bot_localpart,
        room_id=room.room_id,
        event_id=event.event_id,
        sender=event.sender,
        timestamp=event.server_timestamp,
        body=message_body
    )
    logger.debug("Stored inbound event_id=%s in DB.", event.event_id)

    # -- 5) Random delay for realism
    await asyncio.sleep(random.uniform(0.5, 2.5))

    # -- 6) Start typing indicator
    try:
        await bot_client.room_typing(room.room_id, True, timeout=30000)
        logger.info("Sent 'typing start' indicator.")
    except Exception as e:
        logger.warning("Could not send 'typing start' indicator => %s", e)

    # -- 7) Determine if it's a command
    if message_body.startswith("!draw"):
        await _handle_draw_command(bot_client, bot_localpart, room, event, message_body)
    elif message_body.startswith("!"):
        # Extract command line without the leading '!'
        cmd_line = message_body[1:].strip()
        console_output = run_console_command_in_memory(cmd_line)

        if console_output and not console_output.strip().startswith("SYSTEM: Unrecognized command"):
            # Recognized command: send the console output as HTML
            await _send_formatted_text(bot_client, room.room_id, console_output)
        else:
            # Unrecognized command: fallback to GPT
            logger.debug("Unrecognized command '%s' => falling back to GPT.", cmd_line)
            await _send_formatted_text(bot_client, room.room_id, "SYSTEM:  Unrecognized Command.")        
    else:
        # Regular message: send GPT response in plain text
        gpt_reply = await _call_gpt(bot_localpart, room.room_id, message_body)
        await _send_text(bot_client, room.room_id, gpt_reply)

    # -- 8) Stop typing indicator
    try:
        await bot_client.room_typing(room.room_id, False, timeout=0)
        logger.info("Sent 'typing stop' indicator.")
    except Exception as e:
        logger.warning("Could not send 'typing stop' indicator => %s", e)

async def _handle_draw_command(bot_client, bot_localpart, room, event, message_body: str):
    """
    Handles the '!draw' command: generates an image via DALL·E, uploads it,
    and sends it to the room along with a fallback text message.
    """
    
    prompt = message_body[5:].strip()
    if not prompt:
        logger.debug("No prompt provided to !draw.")
        await bot_client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={
                "msgtype": "m.text",
                "body": "Please provide a description for me to draw!\nExample: `!draw A roaring lion in armor`"
            },
        )
        return

    # Check for OpenAI API Key
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    if not OPENAI_API_KEY:
        logger.error("Missing OPENAI_API_KEY for !draw.")
        await bot_client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": "Error: Missing OPENAI_API_KEY."},
        )
        return

    try:
        # Generate image from DALL·E
        logger.info("Generating image from prompt => %r", prompt)
        url = "https://api.openai.com/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
        }
        resp = requests.post(url, headers=headers, json=data)
        resp.raise_for_status()
        result_data = resp.json()
        image_url = result_data["data"][0]["url"]
        logger.info("OpenAI returned image_url=%s", image_url)
    except Exception as e:
        logger.exception("Error generating image from OpenAI.")
        await bot_client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": f"Error generating image: {e}"},
        )
        return

    try:
        # Download the image
        logger.info("Downloading image from URL: %s", image_url)
        os.makedirs("data/images", exist_ok=True)
        timestamp = int(time.time())
        filename = f"data/images/generated_image_{timestamp}.jpg"

        dl_resp = requests.get(image_url)
        dl_resp.raise_for_status()

        with open(filename, "wb") as f:
            f.write(dl_resp.content)

        logger.info("Image downloaded => %s", filename)
    except Exception as e:
        logger.exception("Error downloading the image.")
        await bot_client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": "Error downloading the image."},
        )
        return

    try:
        # Upload to Synapse
        logger.info("Uploading image to Matrix server (direct_upload_image).")
        mxc_url = await direct_upload_image(bot_client, filename, "image/jpeg")
        logger.info("Image upload success => %s", mxc_url)
    except Exception as e:
        logger.exception("Error uploading image to Synapse.")
        await bot_client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": f"Image upload error: {e}"},
        )
        return

    try:
        # Send the image
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
        logger.debug("Sending image content => %s", json.dumps(image_content, indent=2))
        img_response = await bot_client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content=image_content,
        )
        if isinstance(img_response, RoomSendResponse):
            logger.info("Image sent => event_id=%s", img_response.event_id)
            # Optionally, store the outbound image message
            bot_messages_store.append_message(
                bot_localpart=bot_localpart,
                room_id=room.room_id,
                event_id=img_response.event_id,
                sender=bot_client.user_id,
                timestamp=int(time.time() * 1000),
                body=json.dumps(image_content)
            )
        else:
            logger.warning("Failed to send image => %s", img_response)
    except Exception as e:
        logger.exception("Error sending the image to the room.")
        await bot_client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": "There was an error uploading the image."},
        )


async def _send_formatted_text(bot_client: AsyncClient, room_id: str, text: str):
    """
    Escape & wrap text in <pre> for a minimal approach.
    """
    safe_text = html.escape(text)
    html_body = f"<pre>{safe_text}</pre>"

    content = {
        "msgtype": "m.text",
        "body": text,  # Fallback
        "format": "org.matrix.custom.html",
        "formatted_body": html_body
    }
    resp = await bot_client.room_send(
        room_id=room_id,
        message_type="m.room.message",
        content=content
    )
    if isinstance(resp, RoomSendResponse):
        logger.info("Sent formatted text => event_id=%s", resp.event_id)
    else:
        logger.warning("Failed to send formatted text => %s", resp)

async def _send_text(bot_client: AsyncClient, room_id: str, text: str):
    """
    Sends plain text (no HTML formatting) to the given room.
    """
    content = {
        "msgtype": "m.text",
        "body": text,
    }
    resp = await bot_client.room_send(
        room_id=room_id,
        message_type="m.room.message",
        content=content
    )
    return resp

async def _call_gpt(bot_localpart: str, room_id: str, user_message: str) -> str:
    """
    Build context (including system prompt) + user message => GPT call.
    Returns the text reply from GPT.
    """
    logger.debug("_call_gpt => building context for localpart=%s, room_id=%s", bot_localpart, room_id)
    context_config = {"max_history": 10}
    gpt_context = build_context(bot_localpart, room_id, context_config)

    # Append the new user message
    gpt_context.append({"role": "user", "content": user_message})

    logger.debug("GPT context => %s", gpt_context)
    reply = await get_gpt_response(
        messages=gpt_context,
        model="gpt-4",
        temperature=0.7,
        max_tokens=300
    )
    return reply
