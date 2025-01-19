"""
ai_functions.py

Provides an interface for sending prompts to the OpenAI API
and receiving responses. Now with extra-verbose logging to help debug
context input, response output, and timings.
"""

import os
import logging
import openai
import time
from nio import AsyncClient, UploadResponse
import requests
from dotenv import load_dotenv
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)
# You can adjust to DEBUG or more granular if you prefer:
logger.setLevel(logging.DEBUG)

# Optionally, if you want to see every single detail from openai or matrix-nio:
# logging.getLogger("openai").setLevel(logging.DEBUG)
logging.getLogger("nio.responses").setLevel(logging.CRITICAL)  # Usually keep quiet

# Load environment variables from a .env file (if present)
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
openai.api_key = OPENAI_API_KEY
if not OPENAI_API_KEY:
    logger.warning("[ai_functions] No OPENAI_API_KEY found in env variables.")

# We typically create an AsyncOpenAI client if using the async approach:
try:
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
except Exception as e:
    logger.exception("[ai_functions] Could not instantiate AsyncOpenAI client => %s", e)
    client = None


async def get_gpt_response(
    messages: list,
    model: str = "gpt-4",
    temperature: float = 0.7,
    max_tokens: int = 300
) -> str:
    """
    Sends `messages` (a conversation array) to GPT and returns the text
    from the first choice. We log everything at DEBUG level:
      - The final messages array
      - The model, temperature, max_tokens
      - Any errors or exceptions
      - The entire GPT response JSON (only if you want full debugging).
    """

    logger.debug("[get_gpt_response] Starting call to GPT with the following parameters:")
    logger.debug("   model=%s, temperature=%.2f, max_tokens=%d", model, temperature, max_tokens)
    logger.debug("   messages (length=%d): %s", len(messages), messages)

    if not client:
        err_msg = "[get_gpt_response] No AsyncOpenAI client is available!"
        logger.error(err_msg)
        return "I'm sorry, but my AI backend is not available right now."

    t0 = time.time()
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        elapsed = time.time() - t0

        # If you'd like, log the entire response object. CAUTION: can be huge.
        logger.debug("[get_gpt_response] Raw GPT response (truncated or full): %s", response)

        choice = response.choices[0]
        text = choice.message.content
        logger.debug("[get_gpt_response] Received GPT reply (%.3fs). Text length=%d",
                     elapsed, len(text))

        return text

    except openai.error.APIConnectionError as e:
        logger.exception("[get_gpt_response] Network problem connecting to OpenAI => %s", e)
        return (
            "I'm sorry, but I'm having network troubles at the moment. "
            "Could you check your internet connection and try again soon?"
        )

    except openai.error.RateLimitError as e:
        logger.exception("[get_gpt_response] OpenAI rate limit error => %s", e)
        return (
            "I'm sorry, I'm a bit overwhelmed right now and have hit my usage limits. "
            "Please try again in a little while!"
        )

    except Exception as e:
        # This catches any other error type
        logger.exception("[get_gpt_response] Unhandled exception calling GPT => %s", e)
        return (
            "I'm sorry, something went wrong on my end. "
            "Could you try again later?"
        )
    
logger = logging.getLogger(__name__)

def generate_image(prompt: str, size: str = "1024x1024") -> str:
    """
    Generates an image using OpenAI's API and returns the URL of the generated image.
    """
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    if not OPENAI_API_KEY:
        logger.error("OpenAI API key not found.")
        raise ValueError("Missing OpenAI API key.")

    try:
        url = "https://api.openai.com/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": size,
        }

        logger.debug("Sending request to OpenAI: %s", data)
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        image_url = response.json()["data"][0]["url"]
        logger.info("Generated image URL: %s", image_url)
        return image_url
    except Exception as e:
        logger.exception("Failed to generate image.")
        raise e

async def generate_image_save_and_post(
    prompt: str,
    client: AsyncClient,
    evan_room_id: str,
    size: str = "1024x179"
) -> None:
    """
    1) Generates an image using OpenAI's newer /v1/images/generations endpoint.
    2) Saves the image to disk in data/images/.
    3) Uploads the image to Matrix and sends it to Evan's room (evan_room_id).
    """

    # Fetch API Key from environment
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    if not OPENAI_API_KEY:
        logger.warning("[ai_functions] No OPENAI_API_KEY found in env variables.")
        return

    # 1) Generate image from prompt
    try:
        url = "https://api.openai.com/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": size
        }

        # Make the request to OpenAI
        resp = requests.post(url, headers=headers, json=data)
        resp.raise_for_status()      # Raises an HTTPError if the request failed
        response_data = resp.json()

        # Extract the URL for the generated image
        image_url = response_data["data"][0]["url"]

    except Exception as e:
        logger.exception("Error generating image: %s", e)
        return

    # 2) Save image to disk
    try:
        os.makedirs("data/images", exist_ok=True)
        timestamp = int(time.time())
        filename = f"data/images/image_{timestamp}.jpg"
        dl_resp = requests.get(image_url)
        if dl_resp.status_code == 200:
            with open(filename, "wb") as file:
                file.write(dl_resp.content)
            logger.info("Image saved to %s", filename)
        else:
            logger.error("Failed to download image from %s (HTTP %d)",
                         image_url, dl_resp.status_code)
            return
    except Exception as e:
        logger.exception("Error saving image to disk: %s", e)
        return

    # 3) Upload image to Matrix
    try:
        with open(filename, "rb") as file:
            upload_resp = await client.upload(file, content_type="image/jpeg")
            if not isinstance(upload_resp, UploadResponse):
                logger.error("Error uploading image to Matrix: %s", upload_resp)
                return
            mxc_uri = upload_resp.content_uri
    except Exception as e:
        logger.exception("Error uploading image to Matrix: %s", e)
        return

    # 4) Send the image to Evan's chat room
    content = {
        "msgtype": "m.image",
        "body": os.path.basename(filename),
        "url": mxc_uri,
        "info": {
            "mimetype": "image/jpeg",
            "size": os.path.getsize(filename),
        },
    }

    try:
        send_resp = await client.room_send(
            room_id=evan_room_id,
            message_type="m.room.message",
            content=content
        )
        if send_resp and hasattr(send_resp, "event_id"):
            logger.info("Image posted to Evan's room => event_id=%s", send_resp.event_id)
        else:
            logger.error("Failed to post image to Evan's room.")
    except Exception as e:
        logger.exception("Error sending the image message to Matrix: %s", e)
        