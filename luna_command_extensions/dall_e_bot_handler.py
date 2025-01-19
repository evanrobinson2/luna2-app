# luna_message_handler.py

import os
import time
import json
import logging
import requests
import urllib.parse
import aiohttp

from nio import (
    AsyncClient,
    RoomMessageText,
    RoomSendResponse,
)

from luna import bot_messages_store  # We’ll use this to track seen event IDs

logger = logging.getLogger(__name__)

async def direct_upload_image(
    client: AsyncClient,
    file_path: str,
    content_type: str = "image/jpeg"
) -> str:
    """
    Manually upload a file to Synapse's media repository, explicitly setting
    Content-Length (avoiding chunked requests).
    
    Returns the mxc:// URI if successful, or raises an exception on failure.
    """
    if not client.access_token or not client.homeserver:
        raise RuntimeError("AsyncClient has no access_token or homeserver set.")

    base_url = client.homeserver.rstrip("/")
    filename = os.path.basename(file_path)
    encoded_name = urllib.parse.quote(filename)
    upload_url = f"{base_url}/_matrix/media/v3/upload?filename={encoded_name}"

    file_size = os.path.getsize(file_path)
    headers = {
        "Authorization": f"Bearer {client.access_token}",
        "Content-Type": content_type,
        "Content-Length": str(file_size),
    }

    logger.debug("[direct_upload_image] POST to %s, size=%d", upload_url, file_size)

    async with aiohttp.ClientSession() as session:
        with open(file_path, "rb") as f:
            async with session.post(upload_url, headers=headers, data=f) as resp:
                if resp.status == 200:
                    body = await resp.json()
                    content_uri = body.get("content_uri")
                    if not content_uri:
                        raise RuntimeError("No 'content_uri' in response JSON.")
                    logger.debug("[direct_upload_image] Uploaded. content_uri=%s", content_uri)
                    return content_uri
                else:
                    err_text = await resp.text()
                    raise RuntimeError(
                        f"Upload failed (HTTP {resp.status}): {err_text}"
                    )


async def handle_luna_message(bot_client: AsyncClient, bot_localpart: str, room, event):
    """
    Modified so we only respond ONCE per message/event_id. If the event_id
    is already in our DB, we skip responding again.

    Steps:
      1) If from ourselves, ignore.
      2) If not a RoomMessageText or not "!draw", ignore.
      3) Check DB for existing event_id. If found, skip.
      4) Otherwise, store inbound message in DB so we don't respond to it again.
      5) Generate image via OpenAI + direct upload
      6) Post m.image + handle fallback
    """

    bot_full_id = bot_client.user

    # 1) Don’t respond to own messages
    if event.sender == bot_full_id:
        logger.debug("Ignoring message from myself: %s", event.sender)
        return

    # Must be a text event
    if not isinstance(event, RoomMessageText):
        return

    message_body = event.body or ""
    if not message_body.startswith("!draw"):
        return

    # 2) Check if we already saw this event_id in DB
    existing_msgs = bot_messages_store.get_messages_for_bot(bot_localpart)
    if any(m["event_id"] == event.event_id for m in existing_msgs):
        logger.info(
            "[handle_luna_message] We’ve already responded to event_id=%s, skipping.",
            event.event_id
        )
        return

    # 3) If this is brand new, store the inbound message so we don't respond to it twice
    bot_messages_store.append_message(
        bot_localpart=bot_localpart,
        room_id=room.room_id,
        event_id=event.event_id,
        sender=event.sender,
        timestamp=event.server_timestamp,
        body=message_body
    )

    # 4) Check for a non-empty prompt
    prompt = message_body[5:].strip()
    if not prompt:
        await bot_client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={
                "msgtype": "m.text",
                "body": "Please provide a description for me to draw!\nExample: `!draw A roaring lion in armor`"
            },
        )
        return

    # 5) Make sure we have an OpenAI API key
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    if not OPENAI_API_KEY:
        logger.error("OpenAI API key not found in environment variables.")
        await bot_client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": "Error: Missing OPENAI_API_KEY."},
        )
        return

    # 6) Indicate typing
    try:
        await bot_client.room_typing(room.room_id, typing_state=True, timeout=30000)
        logger.info("Successfully sent 'typing start' indicator to room.")
    except Exception as e:
        logger.warning(f"Could not send 'typing start' indicator => {e}")

    try:
        # (A) Generate the image from OpenAI
        try:
            logger.info("Generating image with OpenAI's API. Prompt=%r", prompt)
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
            logger.info("OpenAI returned an image URL: %s", image_url)
        except Exception as e:
            logger.exception("Error occurred while generating image from OpenAI.")
            await bot_client.room_send(
                room_id=room.room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": f"Error generating image: {e}"},
            )
            return

        # (B) Download the image
        try:
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
            logger.exception("Error occurred while downloading the image.")
            await bot_client.room_send(
                room_id=room.room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": "Error downloading the image."},
            )
            return

        # (C) Upload to Synapse (explicit Content-Length)
        try:
            logger.info("Uploading image to Matrix server (direct_upload_image).")
            mxc_url = await direct_upload_image(bot_client, filename, "image/jpeg")
            logger.info("Image upload success => %s", mxc_url)
        except Exception as e:
            logger.exception("Error occurred during direct upload to Synapse.")
            await bot_client.room_send(
                room_id=room.room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": f"Image upload error: {e}"},
            )
            return

        # (D) Send the m.image event
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
            logger.info("Sending m.image =>\n%s", json.dumps(image_content, indent=2))
            img_response = await bot_client.room_send(
                room_id=room.room_id,
                message_type="m.room.message",
                content=image_content,
            )
            if isinstance(img_response, RoomSendResponse):
                logger.info("Sent image to room. Event ID: %s", img_response.event_id)
            else:
                logger.error("Failed to send image. Response: %s", img_response)
        except Exception as e:
            logger.exception("Error sending the image to the room.")
            await bot_client.room_send(
                room_id=room.room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": "There was an error uploading the image."},
            )
            return

    finally:
        # (E) Stop typing no matter what
        try:
            await bot_client.room_typing(room.room_id, typing_state=False, timeout=0)
        except Exception as e:
            logger.warning(f"Could not send 'typing stop' indicator => {e}")
