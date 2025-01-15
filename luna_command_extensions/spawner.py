# spawner.py

import json
import asyncio
import logging
import shlex

# Suppose your GPT call is in ai_functions.py
from luna.ai_functions import get_gpt_response

logger = logging.getLogger(__name__)

# Simple ANSI color codes for old-school vibe:
ANSI_YELLOW = "\033[93m"
ANSI_GREEN = "\033[92m"
ANSI_CYAN = "\033[96m"
ANSI_MAGENTA = "\033[95m"
ANSI_RED = "\033[91m"
ANSI_WHITE = "\033[97m"
ANSI_RESET = "\033[0m"


def cmd_spawn_squad(args, loop):
    """
    The real logic for spawn_squad.
    Called by console_functions.py or whichever file includes the “command router.”

    Usage: spawn_squad <numBots> "<theme or style>"

    Example:
      spawn_squad 3 "A jazzy trio of improvisational bots"

    This version displays a more colorful, “BBS-like” console output
    when describing the spawned personas and their JSON details.
    """

    logger.debug("cmd_spawn_squad => Received args=%r", args)

    # 1) Parse the arguments
    tokens = shlex.split(args.strip())
    logger.debug("Parsed tokens => %s", tokens)

    if len(tokens) < 2:
        msg = "SYSTEM: Usage: spawn_squad <numBots> \"<theme>\""
        print(msg)
        logger.warning(msg)
        return

    # Try to parse the count as an integer
    try:
        count = int(tokens[0])
    except ValueError:
        msg = "SYSTEM: First arg must be an integer for the number of bots."
        print(msg)
        logger.warning(msg)
        return

    # We only allow 1–5 bots
    if count < 1 or count > 5:
        msg = "SYSTEM: Allowed range is 1 to 5 bots."
        print(msg)
        logger.warning(msg)
        return

    # Reconstruct the theme from all tokens after the first
    theme = " ".join(tokens[1:])
    logger.debug("Spawn_squad => count=%d, theme=%r", count, theme)

    # 2) Build the GPT system instructions & user message.
    #    We now require 'biography' and 'backstory' keys as well.
    system_instructions = (
        "You are an assistant that outputs ONLY valid JSON. "
        "No markdown, no code fences, no extra commentary. "
        f"Generate an array of exactly {count} persona objects. "
        "Each object must have keys: localpart, displayname, biography, backstory, system_prompt, password, traits."
        "No other keys. "
        "The 'traits' key is a JSON object with arbitrary key/values. "
        "Be sure that the system prompt instructs the bot to behave at all times in character."
        "Incorporate as much of the character's identity into the system prompt as possible"
        "In this environment, you can explicitly mention another bot by typing their Matrix user ID in the format @<localpart>:localhost. For example, if a bot’s localpart is diamond_dave, you would mention them as @diamond_dave:localhost. Important: mentioning a bot this way always triggers a response from them. Therefore, avoid frivolous or unnecessary mentions. Only mention another bot when you genuinely need their attention or expertise."
    )

    user_message = (
        f"Please create {count} persona(s) for the theme: '{theme}'. "
        "Return ONLY valid JSON (an array, no outer text). Be sure that the system prompt instructs the bot to behave at all times in character."
    )

    logger.debug("system_instructions=%r", system_instructions)
    logger.debug("user_message=%r", user_message)

    async def do_spawn():
        logger.debug("do_spawn => Starting GPT call (count=%d)", count)

        # 3) Call GPT to get JSON for the requested # of personas
        gpt_response = await get_gpt_response(
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user",   "content": user_message}
            ],
            model="gpt-4",
            temperature=0.7,
            max_tokens=1000
        )

        logger.debug("GPT raw response => %r", gpt_response)

        # 4) Parse JSON
        try:
            persona_array = json.loads(gpt_response)
        except json.JSONDecodeError as e:
            err_msg = f"SYSTEM: GPT returned invalid JSON => {e}"
            print(err_msg)
            logger.error("%s -- full GPT response => %s", err_msg, gpt_response)
            return

        if not isinstance(persona_array, list):
            msg = "SYSTEM: GPT did not return a JSON list. Aborting."
            print(msg)
            logger.warning(msg)
            return

        if len(persona_array) != count:
            msg = (
                f"SYSTEM: GPT returned a list of length "
                f"{len(persona_array)}, expected {count}. Aborting."
            )
            print(msg)
            logger.warning(msg)
            return

        # 5) Summon each persona
        successes = 0

        for i, persona in enumerate(persona_array):
            logger.debug("Persona[%d] => %s", i, persona)

            # Check for required keys
            required_keys = [
                "localpart",
                "displayname",
                "biography",
                "backstory",
                "system_prompt",
                "password",
                "traits",
            ]

            missing_key = None
            for rk in required_keys:
                if rk not in persona:
                    missing_key = rk
                    break
            if missing_key:
                msg = f"SYSTEM: Missing key '{missing_key}' in GPT object {i}. Skipping."
                print(msg)
                logger.warning(msg)
                continue

            # Display a fancy "character sheet" in BBS style
            persona_label = f"{ANSI_GREEN}Persona #{i+1} of {count}{ANSI_RESET}"

            print(f"\n{ANSI_MAGENTA}{'=' * 60}{ANSI_RESET}")
            print(f"{ANSI_YELLOW} Summoning {persona_label} for your {theme} squad...{ANSI_RESET}")
            print(f"{ANSI_MAGENTA}{'=' * 60}{ANSI_RESET}")

            # We'll display the entire JSON so we don't rely on a specific schema.
            # For color + indentation, let's do a pretty print but highlight keys.
            # We'll build lines by hand:
            for k, v in persona.items():
                # Show keys in CYAN, values in WHITE
                # If v is a dict, we can pretty-dump it
                if isinstance(v, dict):
                    dict_str = json.dumps(v, indent=2)
                    print(f"{ANSI_CYAN}  {k}{ANSI_RESET} = {ANSI_WHITE}{dict_str}{ANSI_RESET}")
                else:
                    # Just convert to string
                    print(f"{ANSI_CYAN}  {k}{ANSI_RESET} = {ANSI_WHITE}{v}{ANSI_RESET}")

            # Actually spawn the user
            full_bot_id = f"@{persona['localpart']}:localhost"
            password = persona["password"]
            displayname = persona["displayname"]
            system_prompt = persona["system_prompt"]
            traits = persona["traits"]

            async def single_spawn():
                from luna.luna_command_extensions.create_and_login_bot import create_and_login_bot
                logger.debug("single_spawn => Creating user_id=%r", full_bot_id)
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

            spawn_result = await single_spawn()

            # Check if creation was successful
            if "Successfully created" in spawn_result:
                successes += 1
                print(
                    f"{ANSI_GREEN}SUCCESS:{ANSI_RESET} {spawn_result}"
                )
            else:
                print(
                    f"{ANSI_RED}FAILED:{ANSI_RESET} {spawn_result}"
                )

        # 6) Summary
        print()
        summary_msg = (
            f"SYSTEM: Attempted to spawn {count} persona(s). "
            f"{successes} succeeded, {count - successes} failed. Done."
        )
        print(f"{ANSI_CYAN}{summary_msg}{ANSI_RESET}")
        logger.info(summary_msg)

    # Announce to user we're about to do it
    print(
        f"{ANSI_YELLOW}SYSTEM:{ANSI_RESET} Summoning a squad of {count} "
        f"'{theme}'... stand by."
    )
    logger.info("cmd_spawn_squad => scheduling do_spawn (count=%d, theme=%r)", count, theme)

    # 7) We do a blocking run of do_spawn on the given loop
    future = asyncio.run_coroutine_threadsafe(do_spawn(), loop)

    # Block until do_spawn() completes
    try:
        future.result()
    except Exception as e:
        print(
            f"{ANSI_RED}SYSTEM: spawn_squad encountered an error => {e}{ANSI_RESET}"
        )
        logger.exception("spawn_squad encountered an exception =>", exc_info=e)
