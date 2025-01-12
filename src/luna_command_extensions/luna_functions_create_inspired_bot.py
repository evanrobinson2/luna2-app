import json
import asyncio

from src.ai_functions import get_gpt_response  # or however you've structured your import
from src.luna_functions import create_user as matrix_create_user  # presumably in your code already
import src.luna_personas

import json
import asyncio

from src.ai_functions import get_gpt_response
import src.luna_personas

import json
import asyncio

from src.ai_functions import get_gpt_response
import src.luna_personas

def cmd_create_inspired_bot(args, loop):
    """
    Usage:
      create_bot_inspired <inspiration_text>

    Assumes GPT will always return well-formed JSON with:
      {
        "localpart": "...",
        "displayname": "...",
        "system_prompt": "...",
        "password": "...",
        "traits": {...}
      }
    """

    # ────────── ANSI COLORS ──────────
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
        "You are a helpful assistant that must respond only with a single valid JSON object. "
        "The JSON object must include exactly these fields: localpart, displayname, system_prompt, password, and traits. "
        "The 'traits' field should be a JSON object (with zero or more key-value pairs). "
        "Do not include any extra keys or text. Do not wrap your response in Markdown or code fences. "
        "Do not provide any explanations—only raw JSON. "
    )

    user_prompt = (
        f"Generate a persona from this inspiration: '{args}'. "
        f"The persona can be imaginative or grounded, but must be returned as raw JSON."
    )

    # Asynchronously call get_gpt_response in the existing event loop
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
        gpt_raw_response = fut.result()  # Wait for GPT to finish
    except Exception as e:
        print(f"{RED}SYSTEM: Error calling GPT => {e}{RESET}")
        return

    # We assume GPT returns valid JSON
    persona_data = json.loads(gpt_raw_response)

    # ─────────────────────────────────────────────────────────
    # Print persona_data in a minimal ASCII table
    # ─────────────────────────────────────────────────────────
    print(f"{BOLD}SYSTEM: GPT suggested the following persona data (table format):{RESET}")

    # Table header
    header_key = "Key"
    header_val = "Value"
    print(f"{CYAN}{header_key:<15}|{header_val:<50}{RESET}")
    print(f"{CYAN}{'-'*15}+{'-'*50}{RESET}")

    # For the top-level fields
    for field in ["localpart", "displayname", "system_prompt", "password"]:
        value = persona_data.get(field, "")
        print(f"{BOLD}{field:<15}{RESET}| {str(value):<50}")

    # Now handle 'traits' which is a sub-dict
    traits = persona_data.get("traits", {})
    print(f"{BOLD}{'traits':<15}{RESET}|")
    if isinstance(traits, dict):
        for t_key, t_val in traits.items():
            print(f"   - {t_key:<10}: {t_val}")
    else:
        # If for some reason 'traits' wasn't a dict
        print(f"   (Not a dict) => {traits}")

    print()  # extra blank line for readability

    # Extract the relevant fields for persona creation
    localpart = persona_data.get("localpart")
    displayname = persona_data.get("displayname")
    system_prompt = persona_data.get("system_prompt")
    password = persona_data.get("password")

    # Basic checks
    required = [
        ("localpart", localpart),
        ("displayname", displayname),
        ("system_prompt", system_prompt),
        ("password", password)
    ]
    missing_fields = [name for (name, val) in required if not val]
    if missing_fields:
        print(f"{RED}SYSTEM: GPT persona is missing required fields: {missing_fields}{RESET}")
        return

    bot_id = f"@{localpart}:localhost"

    # Step A: Create local persona in personalities.json
    try:
        persona = src.luna_personas.create_bot(
            bot_id=bot_id,
            password=password,
            displayname=displayname,
            creator_user_id="@lunabot:localhost",
            system_prompt=system_prompt,
            traits=persona_data.get("traits", {})
        )
        print(f"{GREEN}SYSTEM: Local persona created successfully!{RESET}")
    except Exception as e:
        print(f"{RED}SYSTEM: Unexpected error => {e}{RESET}")
        return

    # Step B: Register user with Synapse (async call)
    from src.luna_functions import create_user as matrix_create_user
    fut_reg = asyncio.run_coroutine_threadsafe(
        matrix_create_user(localpart, password, is_admin=False),
        loop
    )
    try:
        result_msg = fut_reg.result()
        print(f"{GREEN}SYSTEM: Matrix user creation => {result_msg}{RESET}")
    except Exception as e:
        print(f"{RED}SYSTEM: Error creating matrix user => {e}{RESET}")