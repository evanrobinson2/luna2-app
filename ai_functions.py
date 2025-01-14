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


async def get_gpt_response_dep(
    context: list,
    model: str = "gpt-4",
    temperature: float = 0.7,
    max_tokens: int = 300
) -> str:
    """
    A deprecated or alternate function, but also with verbose logs.
    """
    logger.debug("[get_gpt_response_dep] Called with context len=%d", len(context))
    logger.debug("   model=%s, temperature=%.2f, max_tokens=%d", model, temperature, max_tokens)
    logger.debug("   context array => %s", context)

    if not client:
        err_msg = "[get_gpt_response_dep] No AsyncOpenAI client is available!"
        logger.error(err_msg)
        return "[Error: GPT backend not available.]"

    t0 = time.time()
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=context,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        elapsed = time.time() - t0
        logger.debug("[get_gpt_response_dep] GPT response time: %.3fs", elapsed)
        logger.debug("[get_gpt_response_dep] Raw response: %s", response)

        text = response.choices[0].message.content
        logger.debug("[get_gpt_response_dep] GPT text len=%d => %r", len(text), text[:50])

        return text
    except Exception as e:
        logger.exception("[get_gpt_response_dep] Exception calling GPT => %s", e)
        return "[Error: Unable to generate response.]"
