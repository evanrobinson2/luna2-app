# assemble_command.py

import asyncio
import json
import logging
from typing import Optional

from nio import AsyncClient

# We'll assume these exist in your codebase:
from luna.luna_command_extensions.command_helpers import _post_in_thread, _keep_typing
from luna.luna_command_extensions.create_room2 import create_room2_command
from luna.luna_command_extensions.spawn_persona import spawn_persona
from luna.ai_functions import get_gpt_response

logger = logging.getLogger(__name__)

async def assemble_command(
    bot_client: AsyncClient,
    invoking_room_id: str,
    parent_event_id: str,
    raw_args: str,
    sender: str
) -> None:
    """
    Usage:
      !assemble "<high-level instructions>"

    Example:
      !assemble "A crack squad of assassins, bring them to my headquarters"

    Flow:
      1) GPT => returns JSON with at least:
         {
           "roomLocalpart": "<str>",
           "roomPrompt": "<str>",
           "personas": [
             { "localpart": "...", "descriptor": "..." },
             ...
           ]
         }
         The 'personas' array can be 1–3 items, each with:
           localpart  => for the newly created bot's Matrix ID
           descriptor => the text we pass to spawn_persona()

      2) For each persona => call spawn_persona(descriptor).
         Keep track of the localparts, so we can invite them.

      3) Build a !create_room2 command string:
         --name=<roomLocalpart>
         --invite=@lunabot:localhost,@<requester>,@<each persona localpart>
         --set_avatar=true
         "<roomPrompt>"

      4) Invoke create_room2_command(...) so the new room is created,
         with an avatar, inviting Luna, the command requester, and each
         newly spawned persona.

    All partial/final output is posted in-thread. No return value.
    """

    typing_task = asyncio.create_task(_keep_typing(bot_client, invoking_room_id))

    # Post initial acknowledgment in-thread
    await _post_in_thread(
        bot_client,
        invoking_room_id,
        parent_event_id,
        "<p>Understood! Assembling your operation now...</p>",
        is_html=True
    )

    # 1) If user didn't provide any instructions, bail
    user_prompt = raw_args.strip('" ')
    if not user_prompt:
        await _post_in_thread(
            bot_client,
            invoking_room_id,
            parent_event_id,
            "Error: No instructions provided.",
            is_html=False
        )
        typing_task.cancel()
        return

    # 2) GPT call => expecting "roomLocalpart", "roomPrompt", "personas" array
    system_instructions = (
        "You are an assistant that outputs ONLY valid JSON, no extra commentary. "
        "The user wants:\n"
        "1) roomLocalpart: a string alias for the new room (e.g., 'crido_deck').\n"
        "2) roomPrompt: a string describing the room's theme.\n"
        "3) personas: an array of up to 3 objects, each with:\n"
        "   localpart  (the new bot's name)\n"
        "   descriptor (the textual prompt we pass to spawn_persona).\n\n"
        "If the user is vague, invent 1–3 personas. Example JSON:\n"
        "{\n"
        "  \"roomLocalpart\": \"crido_deck\",\n"
        "  \"roomPrompt\": \"A starship deck for clandestine ops...\",\n"
        "  \"personas\": [\n"
        "    { \"localpart\": \"sniperX\", \"descriptor\": \"A silent sniper assassin...\"},\n"
        "    { \"localpart\": \"toxinZ\",  \"descriptor\": \"A poison master...\"}\n"
        "  ]\n"
        "}"
        "\nReturn ONLY valid JSON. No code fences."
    )
    messages = [
        {"role": "system", "content": system_instructions},
        {"role": "user",   "content": user_prompt},
    ]

    try:
        gpt_response = await get_gpt_response(
            messages=messages,
            model="gpt-4o",
            temperature=0.7,
            max_tokens=1500
        )
    except Exception as e:
        logger.exception("[assemble_command] GPT error =>")
        await _post_in_thread(
            bot_client,
            invoking_room_id,
            parent_event_id,
            f"<p><strong>Oops!</strong> GPT error => {e}</p>",
            is_html=True
        )
        typing_task.cancel()
        return

    # 3) Parse GPT response => JSON object
    try:
        data = json.loads(gpt_response)
        room_localpart = data.get("roomLocalpart", "").strip()
        room_prompt    = data.get("roomPrompt", "").strip()
        personas       = data.get("personas", [])
        if (not room_localpart) or (not room_prompt) or (not isinstance(personas, list)):
            raise ValueError("Missing one of {roomLocalpart, roomPrompt, personas} or invalid format.")
    except Exception as e:
        logger.exception("[assemble_command] JSON parse error =>")
        await _post_in_thread(
            bot_client,
            invoking_room_id,
            parent_event_id,
            f"<p><strong>Oops!</strong> Invalid JSON => {e}</p>",
            is_html=True
        )
        typing_task.cancel()
        return

    total_personas = len(personas)
    await _post_in_thread(
        bot_client,
        invoking_room_id,
        parent_event_id,
        f"Creating new room `#{room_localpart}:localhost` + spawning {total_personas} persona(s).",
        is_html=False
    )

    # 4) Spawn each persona
    success_count = 0
    fail_count = 0

    # We'll collect each persona's localpart so we can invite them all:
    persona_localparts = []

    # 5) Build the command string for create_room2
    # Hardcode invites for Luna + the command user + newly spawned personas
    base_invites = [ "@lunabot:localhost", sender ]
           
    for idx, pdef in enumerate(personas, start=1):
        localpart = pdef.get("localpart", "").strip()
        descriptor_str = pdef.get("descriptor", "").strip()

        if not localpart or not descriptor_str:
            fail_count += 1
            await _post_in_thread(
                bot_client,
                invoking_room_id,
                parent_event_id,
                f"(#{idx}/{total_personas}) Missing localpart or descriptor. Skipping.",
                is_html=False
            )
            continue

        # Post partial
        await _post_in_thread(
            bot_client,
            invoking_room_id,
            parent_event_id,
            f"<p><strong>Persona #{idx}:</strong> localpart=@{localpart}:localhost<br/>{descriptor_str}</p>",
            is_html=True
        )

        # Attempt to spawn
        try:
            result = await spawn_persona(descriptor_str)
            card_html = result["html"]
            bot_id = result["bot_id"]
            base_invites.append(bot_id)
            
            success_count += 1
            persona_localparts.append(localpart)

            await _post_in_thread(
                bot_client,
                invoking_room_id,
                parent_event_id,
                card_html,
                is_html=True
            )

        except Exception as e:
            logger.exception(f"[assemble_command] persona {idx} spawn failed =>")
            fail_count += 1
            await _post_in_thread(
                bot_client,
                invoking_room_id,
                parent_event_id,
                f"<p>Persona #{idx} spawn failed => {e}</p>",
                is_html=True
            )



    invites_str = ",".join(base_invites)

    create_room2_args = (
        f"--name={room_localpart} "
        f"--invite={invites_str} "
        f"--set_avatar=true "
        f"\"{room_prompt}\""
    )

    # 6) Call create_room2_command => sets avatar, invites everyone
    try:
        await create_room2_command(
            bot_client,
            invoking_room_id,
            parent_event_id,
            create_room2_args,
            sender
        )
    except Exception as e:
        logger.exception("[assemble_command] create_room2_command failed =>")
        await _post_in_thread(
            bot_client,
            invoking_room_id,
            parent_event_id,
            f"<p><strong>Room creation step failed =></strong> {e}</p>",
            is_html=True
        )

    # 7) Final summary
    final_msg = (
        f"<p><strong>All done!</strong><br/>"
        f"Spawned <b>{success_count}</b> persona(s), <b>{fail_count}</b> failed.<br/>"
        f"Room alias => <code>#{room_localpart}:localhost</code>.</p>"
    )
    await _post_in_thread(
        bot_client,
        invoking_room_id,
        parent_event_id,
        final_msg,
        is_html=True
    )

    typing_task.cancel()
    logger.info("[assemble_command] Completed => success=%d, fail=%d", success_count, fail_count)
    return
