import logging
import json
import time
import os

from luna.ai_functions import get_gpt_response, generate_image
from luna.luna_command_extensions.create_and_login_bot import create_and_login_bot
from luna.luna_personas import update_bot
from luna.luna_functions import getClient
from luna.luna_command_extensions.image_helpers import direct_upload_image

logger = logging.getLogger(__name__)

async def spawn_persona(descriptor: str) -> str:
    """
    Creates a new persona, returning one HTML string that includes:
    - A table (the "character card") with:
       * localpart, displayname, biography, backstory, system prompt
       * the EXACT DALL·E prompt used for image creation
       * traits as a nested table
    - Possibly an <img> referencing the final mxc:// URI.
    """

    # 1) GPT => persona JSON
    system_instructions = (
        "You are an assistant that outputs ONLY valid JSON. "
        "No markdown, no code fences, no extra commentary. "
        "Generate a persona object which must have keys: localpart, displayname, biography, backstory, "
        "system_prompt, password, traits. No other keys. "
        "The 'traits' key is a JSON object with arbitrary key/values. "
        "Be sure that the system prompt instructs the bot to behave in character."
    )
    user_message = (
        f"Create a persona based on:\n{descriptor}\n\n"
        "Return ONLY valid JSON with required keys."
    )

    messages = [
        {"role": "system", "content": system_instructions},
        {"role": "user", "content": user_message},
    ]

    logger.info(f"SYSTEM: Attemping to get a character card generated via GPT. System Instruction: {system_instructions}. Prompt: {user_message}")
    try:
        gpt_response = await get_gpt_response(
            messages=messages,
            model="gpt-4",
            temperature=0.7,
            max_tokens=5000
        )
    except Exception as e:
        logger.exception("GPT error =>")
        return f"SYSTEM: GPT error => {e}"

    # 2) Parse persona JSON
    try:
        persona_data = json.loads(gpt_response)
    except json.JSONDecodeError as e:
        logger.exception("JSON parse error =>")
        return f"SYSTEM: GPT returned invalid JSON => {e}"

    required = ["localpart", "password", "displayname", "system_prompt", "traits"]
    missing = [f for f in required if f not in persona_data]
    if missing:
        return f"SYSTEM: Persona missing fields => {missing}"

    localpart     = persona_data["localpart"]
    password      = persona_data["password"]
    displayname   = persona_data["displayname"]
    system_prompt = persona_data["system_prompt"]
    traits        = persona_data["traits"] or {}
    biography     = persona_data.get("biography", "")
    backstory     = persona_data.get("backstory", "")

    # 3) Register & login the persona
    bot_result = await create_and_login_bot(
        bot_id=f"@{localpart}:localhost",
        password=password,
        displayname=displayname,
        system_prompt=system_prompt,
        traits=traits
    )
    bot_id = bot_result["bot_id"]
    spawn_msg = bot_result["html"]                       # e.g. success/error message in HTML
    ephemeral_bot_client = bot_result["client"]          # the AsyncClient instance

    if not bot_result["ok"]:
        # Something went wrong. You could return or raise an error, for example:
        error_details = bot_result.get("error", "Unknown error")
        raise RuntimeError(f"Persona creation failed: {error_details}")
   
    if bot_id.startswith('@'):
        bot_id = bot_id[1:]  # Remove the first '@'
    if bot_id.endswith(':localhost'):
        bot_id = bot_id[:-10]  # Remove the last ':localhost'
    
    # 4) Attempt to generate & upload a portrait
    #    We'll store the EXACT DALL·E prompt in 'final_prompt'
    final_prompt = descriptor.strip()  
    portrait_mxc = None
    try:
        portrait_url = await generate_image(final_prompt, size="1024x1024")
        if portrait_url:
            portrait_mxc = await _download_and_upload_portrait(portrait_url, bot_id, password, system_prompt, traits, ephemeral_bot_client)
    except Exception as e:
        logger.warning("Portrait error => %s", e)

    # get the global style prompt appendix
    from luna.luna_command_extensions.command_router import GLOBAL_PARAMS
    global_draw_appendix = GLOBAL_PARAMS["global_draw_prompt_appendix"]

    # 5) Build final HTML table (with nested table for `traits`)
    #    plus an <img> if we have a portrait.
    card_html = _build_persona_card(
        localpart=localpart,
        displayname=displayname,
        biography=biography,
        backstory=backstory,
        system_prompt=system_prompt,
        dall_e_prompt=final_prompt,   # EXACT final prompt
        traits=traits,
        portrait_mxc=portrait_mxc,
        global_draw_appendix = global_draw_appendix 
    )

    logger.info(f"[spawn_persona] Spawning {localpart}")
    return {
        "html": card_html,
        "bot_id": bot_id
    }

async def cmd_spawn(bot_client, descriptor):
    """
    Usage: spawn "A cosmic explorer..."
    Returns a single HTML string containing the entire character card
    (table + optional <img>).
    """
    try:
        result = await spawn_persona(descriptor)  # now returns a dict {"html": ..., "bot_id": ...}
        card_html = result["html"]               # extract the HTML portion
        return card_html
    except Exception as e:
        logger.exception("cmd_spawn => error in spawn_persona")
        return f"SYSTEM: Error spawning persona => {e}"



# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------

async def _download_and_upload_portrait(
    portrait_url: str,
    localpart: str,
    password: str,
    system_prompt: str,
    traits: dict,
    ephemeral_bot_client
) -> str:
    """
    Download the image from portrait_url, upload to matrix,
    update persona record + set bot avatar. Returns mxc:// URI or None.
    """
    import requests
    os.makedirs("data/images", exist_ok=True)
    filename = f"data/images/portrait_{int(time.time())}.jpg"
    dl_resp = requests.get(portrait_url)
    dl_resp.raise_for_status()
    with open(filename, "wb") as f:
        f.write(dl_resp.content)

    client = getClient()
    if not client:
        return None
    portrait_mxc = await direct_upload_image(client, filename, "image/jpeg")
    # Update persona
    traits["portrait_url"] = portrait_mxc
    update_bot(
        f"@{localpart}:localhost",
        {
            "password": password,
            "system_prompt": system_prompt,
            "traits": traits
        }
    )
    # Attempt to set avatar
    if ephemeral_bot_client:
        try:
            await ephemeral_bot_client.set_avatar(portrait_mxc)
        except Exception as e:
            logger.warning("Error setting avatar => %s", e)

    return portrait_mxc

def _build_persona_card(
    localpart: str,
    displayname: str,
    biography: str,
    backstory: str,
    system_prompt: str,
    dall_e_prompt: str,
    global_draw_appendix: str,
    traits: dict,
    portrait_mxc: str = None
) -> str:
    """
    1) Show the localpart as a big title above the portrait.
    2) Show an italic line beneath the title (e.g. the displayname).
    3) Then the portrait if available.
    4) Then a table with the rest of the details, including version=1.0.
    """

    import html
    def esc(t): 
        return html.escape(str(t))

    # -------------------------
    # Sub-table for traits
    # -------------------------
    trait_rows = []
    for k, v in traits.items():
        trait_rows.append(
            "<tr>"
            f"<td style='padding:2px 6px;'><b>{esc(k)}</b></td>"
            f"<td style='padding:2px 6px;'>{esc(v)}</td>"
            "</tr>"
        )
    traits_subtable = (
        "<table border='1' style='border-collapse:collapse; font-size:0.9em;'>"
        "<thead><tr><th colspan='2'>Traits</th></tr></thead>"
        f"<tbody>{''.join(trait_rows)}</tbody>"
        "</table>"
    )

    # A quick helper to build each row
    def row(label, val):
        return (
            "<tr>"
            f"<td style='padding:4px 8px;vertical-align:top;'><b>{esc(label)}</b></td>"
            f"<td style='padding:4px 8px;'>{val}</td>"
            "</tr>"
        )

    # -------------------------
    # The portrait HTML (if any)
    # -------------------------
    portrait_html = ""
    if portrait_mxc:
        portrait_html = (
            f"<div style='margin-bottom:8px;'>"
            f"<img src='{esc(portrait_mxc)}' alt='Portrait' width='300'/>"
            "</div>"
        )

    # -------------------------
    # The table of fields
    # -------------------------
    # Hardcoded version => "1.0"
    row_version       = row("Version", "1.0")
    row_localpart     = row("Localpart", esc(localpart))
    row_displayname   = row("DisplayName", esc(displayname))
    row_biography     = row("Biography", esc(biography))
    row_backstory     = row("Backstory", esc(backstory))
    row_systemprompt  = row("System Prompt", esc(system_prompt))
    row_dalle_prompt  = row("DALL·E Prompt", esc(dall_e_prompt))
    row_draw_appendix = row("Draw Prompt Appendix", esc(global_draw_appendix))
    row_traits        = row("Traits", traits_subtable)

    table_body = "".join([
        row_localpart,
        row_displayname,
        row_biography,
        row_backstory,
        row_systemprompt,
        row_dalle_prompt,
        row_draw_appendix,
        row_traits,
        row_version
    ])

    table_html = (
        "<table border='1' style='border-collapse:collapse;'>"
        f"<tbody>{table_body}</tbody>"
        "</table>"
    )

    # -------------------------
    # Combine everything
    # -------------------------
    # 1) <h2>@localpart</h2> as a big title
    # 2) Italic line with displayName (or biography if you prefer)
    # 3) The portrait
    # 4) The table
    final_html = (
        f"<h2 style='margin-bottom:2px;'>{esc(localpart)}</h2>"
        f"<p style='margin-top:0; margin-bottom:10px;'><em>{esc(displayname)}</em></p>"
        f"{portrait_html}"
        f"{table_html}"
        "<p><em>All done creating the persona!</em></p>"
    )
    return final_html
