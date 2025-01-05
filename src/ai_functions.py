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
logging.getLogger("nio.responses").setLevel(logging.WARNING)  # Suppress noisy nio responses

if not OPENAI_API_KEY:
    logger.warning("No OPENAI_API_KEY found in environment variables.")

# Set the API key for OpenAI
openai.api_key = OPENAI_API_KEY

async def get_gpt_response(prompt: str, model: str = "gpt-4", temperature: float = 0.7, max_tokens: int = 150) -> str:
    """
    Sends a user_input prompt to GPT and returns the response asynchronously.

    Args:
        prompt (str): The user's input message.
        model (str): The GPT model to use (default: "gpt-4").
        temperature (float): Sampling temperature (default: 0.7).
        max_tokens (int): Maximum tokens for the response (default: 150).

    Returns:
        str: The assistant's response or an error message.
    """
    logger.debug(f"get_gpt_response called with prompt: {prompt}")

    try:
        # Make the API call
        logger.info(f"Sending user_input to OpenAI using model '{model}', max_tokens={max_tokens}, temperature={temperature}.")
        response = await client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        # Extract the assistant's response
        answer = response.choices[0].message.content
        logger.info(f"OpenAI responded successfully: {answer}")
        return answer

    except client.errors.APIConnectionError as e:
        logger.exception(f"API connection error: {e}")
        return "[Error: Unable to connect to OpenAI API.]"

    except client.errors.AuthenticationError as e:
        logger.exception(f"Authentication error: {e}")
        return "[Error: Invalid OpenAI API key.]"

    except client.errors.InvalidRequestError as e:
        logger.exception(f"Invalid request: {e}")
        return f"[Error: Invalid request. Details: {e}]"

    except Exception as e:
        logger.exception(f"Unexpected error occurred: {e}")
        return "[Error: An unexpected error occurred.]"