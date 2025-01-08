"""
ai_functions.py

Provides a minimal interface for sending prompts to the OpenAI API
and receiving responses. Includes logging statements for transparency.
"""

import os
import logging
import openai
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Adjust as needed
logging.getLogger("nio.responses").setLevel(logging.CRITICAL)  # Suppress noisy nio responses

# Load environment variables from a .env file
load_dotenv("/Users/evanrobinson/Documents/Luna2/luna/src/.env")


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") # Load the API key from the environment
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY")) # Create an AsyncOpenAI client
openai.api_key = OPENAI_API_KEY # Set the API key for OpenAI


if not OPENAI_API_KEY:
    logger.warning("No OPENAI_API_KEY found in environment variables.")




async def get_gpt_response(
    context: list,
    model: str = "gpt-4",
    temperature: float = 0.7,
    max_tokens: int = 300
) -> str:
    """
    Sends a conversation context to GPT and retrieves the response.

    Returns a user-friendly, first-person error message if something goes wrong.
    """

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=context,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

    except openai.error.APIConnectionError as e:
        logger.exception(f"Network problem connecting to OpenAI: {e}")
        return (
            "I'm sorry, but I'm having network troubles at the moment. "
            "Could you check your internet connection and try again soon?"
        )

    except openai.error.RateLimitError as e:
        logger.exception(f"OpenAI rate limit error: {e}")
        return (
            "I'm sorry, I'm a bit overwhelmed right now and have hit my usage limits. "
            "Please try again in a little while!"
        )

    except Exception as e:
        # This catches any other errors
        logger.exception(f"Unhandled error calling OpenAI API: {e}")
        return (
            "I'm sorry, something went wrong on my end. "
            "Could you try again later?"
        )


async def get_gpt_response_dep(context: list, model: str = "gpt-4", temperature: float = 0.7, max_tokens: int = 300) -> str:
    """
    Sends a conversation context to GPT and retrieves the response.

    Args:
        context (list): A list of messages in the format [{"role": "user", "content": "..."}].
        model (str): The GPT model to use (default: "gpt-4").
        temperature (float): Controls randomness (default: 0.7).
        max_tokens (int): The maximum number of tokens in the response (default: 300).

    Returns:
        str: The GPT response.
    """
    logger.debug(f"get_gpt_response called with context: {context}")

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=context,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.exception(f"Error calling OpenAI API: {e}")
        return "[Error: Unable to generate response.]"



