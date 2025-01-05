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

# Load environment variables from a .env file
load_dotenv()

# Load the API key from the environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Create an AsyncOpenAI client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Adjust as needed
logging.getLogger("nio.responses").setLevel(logging.CRITICAL)  # Suppress noisy nio responses

if not OPENAI_API_KEY:
    logger.warning("No OPENAI_API_KEY found in environment variables.")


async def get_gpt_response(context: list, model: str = "gpt-4", temperature: float = 0.7, max_tokens: int = 300) -> str:
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

# Set the API key for OpenAI
openai.api_key = OPENAI_API_KEY


