# luna_invocable.py
import re
import logging
import shlex
import asyncio

from luna.luna_command_extensions.create_and_login_bot import create_and_login_bot
from luna.ai_functions import get_gpt_response
# Or anything else you need to import

logger = logging.getLogger(__name__)

# A naive pattern =>  commandName(argsHere)
ACTION_CALL_REGEX = re.compile(r'^(\w+)\((.*)\)$')

async def run_action_command(action_line: str, loop) -> str:
    """
    Given a string like 'spawn_squad(1,"pirates")' or 'summon_bot("pirate1","Scurvy prompt")',
    parse it, figure out the command, and run the relevant code. Return a text result.
    
    If unrecognized => return an error message.
    """
    match = ACTION_CALL_REGEX.match(action_line)
    if not match:
        return f"Unrecognized action syntax => {action_line}"

    command_name = match.group(1)
    args_str = match.group(2)  # e.g. 1,"pirates"

    # You might parse the args with shlex, or something else
    # For example:
    try:
        tokens = shlex.split(args_str)
    except Exception as e:
        return f"Error parsing action arguments => {e}"

    if command_name == "spawn_squad":
        return await handle_spawn_squad(tokens, loop)
    elif command_name == "summon_bot":
        return await handle_summon_bot(tokens, loop)
    # etc. add more commands

    return f"No known command '{command_name}'"

async def handle_spawn_squad(tokens, loop) -> str:
    """
    This would replicate your spawn_squad logic, 
    e.g. tokens might be [1, 'pirates'] if the user typed spawn_squad(1,"pirates")
    """
    if len(tokens) < 2:
        return "Usage: spawn_squad(count, \"theme\")"

    try:
        count = int(tokens[0])
    except ValueError:
        return "First arg is not an integer."

    theme = " ".join(tokens[1:])
    if count < 1 or count > 5:
        return "Allowed range is 1..5"

    # Insert your GPT call that returns an array of persona JSON
    # Then create each bot, etc. Return final result.

    return f"(Pretend) spawn_squad => Creating {count} bots for theme='{theme}'."

async def handle_summon_bot(tokens, loop) -> str:
    """
    Suppose the user typed:  summon_bot("pirate1","some password","A prompt")
    tokens => ["pirate1","some password","A prompt"]
    """
    if len(tokens) < 3:
        return "summon_bot => usage: localpart password \"system_prompt\""

    localpart = tokens[0]
    password = tokens[1]
    system_prompt = " ".join(tokens[2:])
    full_bot_id = f"@{localpart}:localhost"

    # Actually create & login
    async def do_create():
        # minimal traits
        traits = {}
        result = await create_and_login_bot(
            bot_id=full_bot_id,
            password=password,
            displayname=localpart,
            system_prompt=system_prompt,
            traits=traits,
            creator_user_id="@lunabot:localhost",
            is_admin=False
        )
        return result

    fut = asyncio.run_coroutine_threadsafe(do_create(), loop)
    outcome = fut.result()
    return outcome
