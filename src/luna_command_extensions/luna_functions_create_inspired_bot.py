import json
import asyncio
import logging

# Adjust imports for your project structure
from src.ai_functions import get_gpt_response
from src.luna_command_extensions.create_and_login_bot import create_and_login_bot

logger = logging.getLogger(__name__)

def create_inspired_bot(args, loop):
    """
    Usage:
      create_bot_inspired <inspiration_text>

    GPT must return JSON with:
      {
        "localpart": "...",
        "displayname": "...",
        "system_prompt": "...",
        "password": "...",
        "traits": {...}
      }
    """
    RED = "\x1b[31m"
    GREEN = "\x1b[32m"
    YELLOW = "\x1b[33m"
    CYAN = "\x1b[36m"
    BOLD = "\x1b[1m"
    RESET = "\x1b[0m"

    if not args.strip():
        print(f"{RED}SYSTEM: No inspiration provided. Please give a short string describing the persona idea.{RESET}")
        return

    print(f"{YELLOW}Attempting to create an inspired bot...{RESET}")

    system_instructions = (
        "You are a helpful assistant that must respond ONLY with a single valid JSON object. "
        "The JSON object must contain exactly: localpart, displayname, system_prompt, password, and traits. "
        "The 'traits' field is a JSON object with zero or more key-value pairs. "
        "No extra keys. Do not wrap your response in Markdown or code fences. "
        "Do not provide any explanation—only raw JSON."
    )
    user_prompt = f"Create a persona from this inspiration: '{args}'. Return as raw JSON."

    # 1) Ask GPT for the persona
    fut = asyncio.run_coroutine_threadsafe(
        get_gpt_response(
            context=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": user_prompt},
            ],
            model="gpt-4",
            temperature=0.7,
            max_tokens=300
        ),
        loop
    )

    try:
        gpt_raw_response = fut.result()
    except Exception as e:
        print(f"{RED}SYSTEM: Error calling GPT => {e}{RESET}")
        return

    # 2) Parse the JSON
    try:
        persona_data = json.loads(gpt_raw_response)
    except json.JSONDecodeError as jde:
        print(f"{RED}SYSTEM: GPT response is not valid JSON => {jde}{RESET}")
        return

    # 3) Display the data (optional debugging)
    print(f"{BOLD}SYSTEM: GPT suggested persona data:{RESET}")
    for key in ["localpart", "displayname", "system_prompt", "password"]:
        val = persona_data.get(key)
        print(f"{CYAN}{key}{RESET} => {val}")
    print(f"{CYAN}traits{RESET} => {persona_data.get('traits', {})}")

    # 4) Validate required fields
    missing = [k for k in ("localpart", "displayname", "system_prompt", "password") if not persona_data.get(k)]
    if missing:
        print(f"{RED}SYSTEM: Missing fields: {missing}{RESET}")
        return

    # 5) Call create_and_login_bot in an async context
    async def do_create_and_login():
        full_bot_id = f"@{persona_data['localpart']}:localhost"
        # Synchronously handle the entire persona creation & ephemeral login
        return await create_and_login_bot(
            bot_id=full_bot_id,
            password=persona_data["password"],
            displayname=persona_data["displayname"],
            system_prompt=persona_data["system_prompt"],
            traits=persona_data["traits"],
            creator_user_id="@lunabot:localhost",  # or the actual user who triggered it
            is_admin=False
        )

    fut_create = asyncio.run_coroutine_threadsafe(do_create_and_login(), loop)
    try:
        final_msg = fut_create.result()
        if final_msg.startswith("Successfully created"):
            print(f"{GREEN}SYSTEM: {final_msg}{RESET}")
        else:
            print(f"{RED}SYSTEM: {final_msg}{RESET}")
    except Exception as e:
        print(f"{RED}SYSTEM: Failed to create & login => {e}{RESET}")
