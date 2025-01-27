# spawn_ensemble.py

import asyncio
import json
import logging

from nio import AsyncClient

# Helper functions from your codebase
from luna.luna_command_extensions.command_helpers import _post_in_thread, _keep_typing
from luna.luna_command_extensions.spawn_persona import spawn_persona
from luna.ai_functions import get_gpt_response

logger = logging.getLogger(__name__)

async def spawn_ensemble_command(
    bot_client: AsyncClient,
    invoking_room_id: str,
    parent_event_id: str,
    raw_args: str,
    sender: str
) -> None:
    """
    Usage:
      !spawn_ensemble "<high-level group instructions>"

    Example:
      !spawn_ensemble "We need 3 blind mice, each with a unique perspective"

    Flow:
      1) Parse user’s entire prompt (raw_args).
      2) Call GPT to produce a JSON array of objects like [{ "prompt": "Mouse A..." }, ... ].
      3) For each object in that array, extract .prompt -> call spawn_persona(prompt_str).
      4) Post partial updates in-thread, plus a final summary.

    spawn_persona() is expected to take a single text descriptor. 
    """
    # Start a keep-typing background task
    typing_task = asyncio.create_task(_keep_typing(bot_client, invoking_room_id))

    # 1) Acknowledge user command
    await _post_in_thread(
        bot_client,
        invoking_room_id,
        parent_event_id,
        "<p>Understood! Generating persona descriptors now...</p>",
        is_html=True
    )

    # The user’s entire prompt is raw_args
    user_prompt = raw_args.strip('" ')
    if not user_prompt:
        await _post_in_thread(
            bot_client,
            invoking_room_id,
            parent_event_id,
            "Error: No ensemble description provided.",
            is_html=False
        )
        typing_task.cancel()
        return

    # NEW IMPORT for config
    from luna.luna_command_extensions.command_router import load_config

    # 2) Load config instructions for ensemble spawner, fallback if missing
    cfg = load_config()
    system_instructions = cfg.get("ensemble_flow", {}).get("spawner_instructions", "")
    if not system_instructions:
        system_instructions = (
            "You are an assistant that outputs ONLY valid JSON, no extra text. "
            "The user wants multiple persona descriptors (strings). Return a JSON array where "
            "each element is an object with exactly one key: 'prompt', whose value is the short descriptor. "
            "No code fences, no markdown, just raw JSON.\n"
            "Example:\n"
            "[{\"prompt\":\"An female mouse named Roxanne...\"}, {\"prompt\":\"A farm mouse named Jorge...\"}, ...]"
        )

    messages = [
        {"role": "system", "content": system_instructions},
        {"role": "user",   "content": user_prompt},
    ]

    # 3) Call GPT
    try:
        gpt_response = await get_gpt_response(
            messages=messages,
            model="gpt-4",
            temperature=0.7,
            max_tokens=1500
        )
    except Exception as e:
        logger.exception("[spawn_ensemble] GPT error =>")
        await _post_in_thread(
            bot_client,
            invoking_room_id,
            parent_event_id,
            f"<p><strong>Oops!</strong> GPT error => {e}</p>",
            is_html=True
        )
        typing_task.cancel()
        return

    # 4) Parse JSON array of { "prompt": "..." }
    try:
        persona_array = json.loads(gpt_response)
        if not isinstance(persona_array, list):
            raise ValueError("GPT returned something that's not a JSON array.")
    except Exception as e:
        logger.exception("[spawn_ensemble] JSON parse error =>")
        await _post_in_thread(
            bot_client,
            invoking_room_id,
            parent_event_id,
            f"<p><strong>Oops!</strong> Invalid JSON from GPT => {e}</p>",
            is_html=True
        )
        typing_task.cancel()
        return

    total = len(persona_array)
    success_count = 0
    fail_count = 0

    await _post_in_thread(
        bot_client,
        invoking_room_id,
        parent_event_id,
        f"Received {total} descriptors. Spawning each persona now...",
        is_html=False
    )

    # 5) For each sub-prompt, call spawn_persona()
    bot_id = None
    for idx, obj in enumerate(persona_array, start=1):
        sub_prompt = obj.get("prompt", "").strip()
        if not sub_prompt:
            await _post_in_thread(
                bot_client,
                invoking_room_id,
                parent_event_id,
                f"(#{idx}/{total}) Missing 'prompt' key in GPT output. Skipping.",
                is_html=False
            )
            fail_count += 1
            continue

        # Post partial update
        await _post_in_thread(
            bot_client,
            invoking_room_id,
            parent_event_id,
            f"<p><strong>Persona #{idx}/{total}:</strong> Prompt: {sub_prompt}</p>",
            is_html=True
        )

        # Call spawn_persona
        try:
            result = await spawn_persona(sub_prompt)
            card_html = result["html"]
            bot_id = result["bot_id"]

            # Post the card
            await _post_in_thread(
                bot_client,
                invoking_room_id,
                parent_event_id,
                card_html,
                is_html=True
            )
            success_count += 1
        except Exception as e:
            logger.exception(f"[spawn_ensemble] persona {idx} spawn failed =>")
            fail_count += 1
            await _post_in_thread(
                bot_client,
                invoking_room_id,
                parent_event_id,
                f"<p>Persona #{idx} spawn failed => {e}</p>",
                is_html=True
            )

    # 6) Final summary
    final_msg = (
        f"<p><strong>All done!</strong> "
        f"Spawned <b>{success_count}</b> persona(s) successfully."
    )
    if fail_count > 0:
        final_msg += f" <br/>Failed <b>{fail_count}</b> persona(s)."
    final_msg += "</p>"

    await _post_in_thread(
        bot_client,
        invoking_room_id,
        parent_event_id,
        final_msg,
        is_html=True
    )

    typing_task.cancel()
    logger.info("[spawn_ensemble_command] Completed. success=%d fail=%d", success_count, fail_count)

    return bot_id
