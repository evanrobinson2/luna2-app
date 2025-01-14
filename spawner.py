import json
import asyncio
import logging
import shlex

# Suppose your GPT call is in ai_functions.py
from luna.ai_functions import get_gpt_response

logger = logging.getLogger(__name__)


def cmd_spawn_squad(args, loop):
    """
    The real logic for spawn_squad. 
    Called by console_functions.py or whichever file includes the “command router.”

    Usage: spawn_squad <numBots> "<theme or style>"

    Example:
      spawn_squad 3 "A jazzy trio of improvisational bots"
    """

    # 1) Parse the arguments
    tokens = shlex.split(args.strip())
    if len(tokens) < 2:
        print("SYSTEM: Usage: spawn_squad <numBots> \"<theme>\"")
        return

    try:
        count = int(tokens[0])
    except ValueError:
        print("SYSTEM: First arg must be an integer for the number of bots.")
        return

    if count < 1 or count > 5:
        print("SYSTEM: Allowed range is 1 to 5 bots.")
        return

    # Reconstruct the theme from all tokens after the first
    theme = " ".join(tokens[1:])

    # 2) Build the GPT system instructions & user message
    system_instructions = (
        "You are an assistant that outputs ONLY valid JSON. "
        "No markdown, no code fences, no extra commentary. "
        "Generate an array of exactly {count} persona objects. "
        "Each object must have keys: localpart, displayname, system_prompt, password, traits. "
        "No other keys. "
        "The 'traits' key is a JSON object with arbitrary key/values. "
    ).format(count=count)

    user_message = (
        f"Please create {count} persona(s) for the theme: '{theme}'. "
        "Return ONLY valid JSON (an array, no outer text)."
    )

    async def do_spawn():
        # 3) Actually call GPT to get JSON for the requested # of personas
        gpt_response = await get_gpt_response(
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user",   "content": user_message}
            ],
            model="gpt-4",
            temperature=0.7,
            max_tokens=1000
        )

        # 4) Attempt to parse the JSON
        try:
            persona_array = json.loads(gpt_response)
            print(f"Created {persona_array}")
        except json.JSONDecodeError as e:
            print(f"SYSTEM: GPT returned invalid JSON => {e}")
            logger.error("Invalid JSON from GPT: %s", gpt_response)
            return

        if not isinstance(persona_array, list):
            print("SYSTEM: GPT did not return a JSON list. Aborting.")
            return

        if len(persona_array) != count:
            print("SYSTEM: GPT returned a list of length different from the requested count.")
            return

        # 5) For each persona, call create_and_login_bot to spawn
        successes = 0
        for i, persona in enumerate(persona_array):
            # Validate required keys
            for key in ["localpart", "displayname", "system_prompt", "password", "traits"]:
                if key not in persona:
                    print(f"SYSTEM: Missing key '{key}' in GPT object {i}. Skipping.")
                    continue

            # Build the Matrix user ID
            full_bot_id = f"@{persona['localpart']}:localhost"
            password = persona["password"]
            displayname = persona["displayname"]
            system_prompt = persona["system_prompt"]
            traits = persona["traits"]

            async def single_spawn():
                from luna.luna_command_extensions.create_and_login_bot import create_and_login_bot
                result_msg = await create_and_login_bot(
                    bot_id=full_bot_id,
                    password=password,
                    displayname=displayname,
                    system_prompt=system_prompt,
                    traits=traits,
                    creator_user_id="@lunabot:localhost",
                    is_admin=False
                )
                return result_msg

            fut_single = asyncio.run_coroutine_threadsafe(single_spawn(), loop)
            spawn_result = fut_single.result()

            if "Successfully created" in spawn_result:
                successes += 1
            print(f"SYSTEM: {spawn_result}")

        # 6) Print a final summary
        print(f"SYSTEM: Attempted to spawn {count} bots, {successes} succeeded. Done.")


    # 7) Schedule the do_spawn() coroutine on the given loop
    fut = asyncio.run_coroutine_threadsafe(do_spawn(), loop)

    # Optionally handle any exceptions or final result
    def on_done(fut):
        exc = fut.exception()
        if exc:
            print(f"SYSTEM: spawn_squad encountered an error => {exc}")

    fut.add_done_callback(on_done)
    print(f"SYSTEM: Summoning a squad of {count} persona(s) for theme: '{theme}'... stand by.")
