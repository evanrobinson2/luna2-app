import asyncio
import logging
import json
import shlex

from luna.ai_functions import get_gpt_response, generate_image
from luna.luna_command_extensions.luna_message_handler import direct_upload_image
from luna.luna_command_extensions.create_and_login_bot import create_and_login_bot
from luna.luna_personas import update_bot
from luna.luna_functions import getClient


logger = logging.getLogger(__name__)

async def spawn_persona(descriptor: str) -> str:
    """
    1) Builds a system prompt for GPT to produce valid JSON for a new persona.
    2) Create & ephemeral-log the bot. (create_and_login_bot now returns (msg, ephemeral_client)).
    3) Generate a portrait image + upload => get mxc URI.
    4) Update the persona's traits with the portrait link, set the avatar if ephemeral client is available.
    5) Return success or error message.
    """
    logger.debug("[spawn_persona] Entered function. Descriptor=%r", descriptor)

    from .command_router import GLOBAL_PARAMS, load_config
    logger.debug("[spawn_persona] Loading config...")

    cfg = load_config()
    rp_system_prompt = cfg.get("bots", {}).get("role_play", {}).get("system_parameter", "")
    if not rp_system_prompt:
        logger.warning("[spawn_persona] No role_play.system_parameter found; using fallback.")
        rp_system_prompt = "You are in a role-play scenario..."

    system_instructions = (
        "You are an assistant that outputs ONLY valid JSON. "
        "No markdown, no code fences, no extra commentary. "
        "Generate a persona object which must have keys: localpart, displayname, biography, backstory, "
        "system_prompt, password, traits. No other keys. "
        "The 'traits' key is a JSON object with arbitrary key/values. "
        "Be sure that the system prompt instructs the bot to behave at all times in character. "
        "Incorporate as much of the character's identity into the system prompt as possible. "
        "In this environment, you can explicitly mention another bot by typing their Matrix user ID in the format @<localpart>:localhost. "
        "For example, if a bot’s localpart is diamond_dave, you would mention them as @diamond_dave:localhost. "
        "Important: mentioning a bot this way always triggers a response from them. "
        "Therefore, avoid frivolous or unnecessary mentions. "
        "Only mention another bot when you genuinely need their attention or expertise."
    )

    user_message = (
        f"Create a role-play persona based on this descriptor:\n{descriptor}\n\n"
        "Return ONLY valid JSON with the required keys.\n"
    )

    # B) GPT call
    logger.debug("[spawn_persona] Preparing GPT messages with system_text length=%d", len(system_instructions))
    gpt_messages = [
        {"role": "system", "content": system_instructions},
        {"role": "user", "content": user_message}
    ]
    logger.info("[spawn_persona] About to call get_gpt_response with model='gpt-4'...")

    try:
        gpt_response = await get_gpt_response(
            messages=gpt_messages,
            model="gpt-4",
            temperature=0.7,
            max_tokens=1200
        )
    except Exception as e:
        logger.exception("[spawn_persona] GPT call failed:")
        return f"SYSTEM: GPT call raised an exception => {e}"

    logger.debug("[spawn_persona] GPT call finished. Response length=%d", len(gpt_response))

    # C) Parse GPT output
    try:
        persona_data = json.loads(gpt_response)
        logger.debug("[spawn_persona] Successfully parsed GPT JSON => %s", persona_data)
    except json.JSONDecodeError as e:
        logger.exception("[spawn_persona] JSON parse error:")
        return f"SYSTEM: GPT returned invalid JSON => {e}"

    required_fields = ["localpart", "password", "displayname", "system_prompt", "traits"]
    missing = [f for f in required_fields if f not in persona_data]
    if missing:
        logger.warning("[spawn_persona] Missing fields=%r in GPT output.", missing)
        return f"SYSTEM: Persona is missing field(s) {missing}"

    localpart     = persona_data["localpart"]
    password      = persona_data["password"]
    displayname   = persona_data["displayname"]
    system_prompt = persona_data["system_prompt"]
    traits        = persona_data["traits"] or {}

    logger.info("[spawn_persona] Persona fields extracted: localpart=%r, displayname=%r", localpart, displayname)

    # D) Create & login bot => returns (msg, ephemeral_bot_client)
    try:
        logger.debug("[spawn_persona] Creating and logging in new bot => @%s:localhost", localpart)
        spawn_result, ephemeral_bot_client = await create_and_login_bot(
            bot_id=f"@{localpart}:localhost",
            password=password,
            displayname=displayname,
            system_prompt=system_prompt,
            traits=traits
        )
        logger.debug("[spawn_persona] create_and_login_bot => %r", spawn_result)

        if not spawn_result.startswith("Successfully created & logged in"):
            logger.warning("[spawn_persona] Bot creation returned non-success => %r", spawn_result)
            return f"SYSTEM: Bot creation failed => {spawn_result}"

    except Exception as e:
        logger.exception("[spawn_persona] ephemeral-login error =>")
        return f"SYSTEM: ephemeral-login error => {e}"

    # E) Generate a portrait
    from .command_router import GLOBAL_PARAMS
    style = GLOBAL_PARAMS.get("global_draw_prompt_appendix", "").strip()
    final_prompt = f"{descriptor.strip()}. {style}" if style else descriptor.strip()

    logger.info("[spawn_persona] Generating portrait with final_prompt=%r", final_prompt)
    portrait_url = None
    try:
        portrait_url = generate_image(final_prompt, size="1024x1024")
        logger.debug("[spawn_persona] Received portrait_url => %r", portrait_url)
    except Exception as e:
        logger.exception("[spawn_persona] error generating portrait image:")
        portrait_url = None  # Not fatal

    #  If we have a portrait => upload to matrix
    portrait_mxc = None
    if portrait_url:
        logger.info("[spawn_persona] Attempting to download + upload portrait.")
        import requests, os, time
        os.makedirs("data/images", exist_ok=True)
        filename = f"data/images/portrait_{int(time.time())}.jpg"

        try:
            resp = requests.get(portrait_url)
            resp.raise_for_status()
            with open(filename, "wb") as f:
                f.write(resp.content)

            logger.debug("[spawn_persona] Portrait downloaded => %s", filename)

            # Use the director client to do the direct_upload
            client = getClient()
            if not client:
                logger.warning("[spawn_persona] No director client found => cannot upload portrait.")
            else:
                portrait_mxc = await direct_upload_image(client, filename, "image/jpeg")
                logger.info("[spawn_persona] Portrait uploaded => %s", portrait_mxc)

                # Update the persona's traits
                traits["portrait_url"] = portrait_mxc
                logger.debug("[spawn_persona] Updating persona with new portrait info.")        

                update_bot(
                    bot_id=f"@{localpart}:localhost",
                    updates={
                        "displayname": displayname,
                        "password": password,
                        "creator_user_id": "@lunabot:localhost",
                        "system_prompt": system_prompt,
                        "traits": traits
                    }
                )

                # === NEW: Set the ephemeral bot's avatar if ephemeral_bot_client is available
                if ephemeral_bot_client and portrait_mxc:
                    try:
                        logger.info("[spawn_persona] Setting new bot avatar => %s", portrait_mxc)
                        await ephemeral_bot_client.set_avatar(portrait_mxc)

                        logger.info("[spawn_persona] Avatar set successfully.")
                    except Exception as e:
                        logger.exception("[spawn_persona] Error setting avatar_url =>")
                        # Not fatal
        except Exception as e:
            logger.exception("[spawn_persona] portrait upload error:")
            # not fatal
    else:
        logger.debug("[spawn_persona] No portrait_url returned; skipping upload.")

    # F) Return success
    portrait_msg = f" Portrait => {portrait_mxc}" if portrait_mxc else ""
    success_message = f"SYSTEM: Successfully spawned persona '@{localpart}:localhost' named '{displayname}'.{portrait_msg}"
    logger.info("[spawn_persona] Completed success => %s", success_message)
    return success_message


async def cmd_spawn(bot_client, descriptor):
    """
    Usage: spawn "<descriptor>"
    e.g. !spawn "A cosmic explorer who hunts star routes"
    """
    logger.debug(f"[cmd_spawn] Attempting to Spawn: {descriptor}")
    try:
        msg = await spawn_persona(descriptor)
        return msg
    except Exception as e:
        logger.exception("cmd_spawn => error in spawn_persona")
        return f"SYSTEM: Error spawning persona => {e}"
