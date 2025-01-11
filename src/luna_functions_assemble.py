# File: luna_functions_team.py

import json
import logging
import datetime
from src.ai_functions import get_gpt_response
from src.luna_functions import create_user, invite_user_to_room, getClient
from src.luna_functions_create_room import create_room
from src.luna_personas import create_bot

logger = logging.getLogger(__name__)

def cmd_assemble(args):
    """
    Usage:
      assemble <team_name> <location>

    1. Calls GPT to create multiple personas for a 'team'.
    2. Saves them to the 'luna_personalities.json' (via create_bot()).
    3. Creates them in Synapse (register).
    4. Creates a new Matrix room.
    5. Invites the team members to the room.
    """

    logger.info("SYSTEM: Starting the assemble process.")
    parts = args.strip().split()
    if len(parts) < 2:
        logger.error("SYSTEM: Invalid arguments. Usage: assemble <team_name> <location>")
        return

    team_name, location = parts[0], parts[1]
    logger.info("SYSTEM: Team name: %s, Location: %s", team_name, location)

    # Step 1: Prompt GPT to generate personas
    print("Prompting GPT for team personas...")
    system_instructions = (
        "You are a helpful assistant that ONLY responds with valid JSON. "
        "You will create a small list of 4 persona objects, each must have fields: "
        "`localpart`, `displayname`, `system_prompt`, `password`, and `traits`. "
        "Output must be a JSON array of these persona objects—no extra text."
    )
    user_prompt = (
        f"Create 4 unique personas who are members of the '{team_name}' team, "
        f"stationed at '{location}'. Return them as a JSON array. "
        "Each persona should include a localpart (no spaces), a displayname, "
        "a short system_prompt, a simple password, and any traits you think relevant."
    )

    try:
        gpt_response = get_gpt_response(
            context=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": user_prompt},
            ],
            model="gpt-4",
            temperature=0.7,
            max_tokens=600,
        )
    except Exception as e:
        logger.error("SYSTEM: Error calling GPT: %s", e)
        return

    print("Parsing GPT response...")
    try:
        personas = json.loads(gpt_response)
    except json.JSONDecodeError as e:
        logger.error("SYSTEM: GPT returned invalid JSON: %s", e)
        logger.debug("SYSTEM: Raw GPT response: %s", gpt_response)
        return

    if not isinstance(personas, list):
        logger.error("SYSTEM: GPT did not return a JSON array.")
        logger.debug("SYSTEM: Raw GPT response: %s", gpt_response)
        return

    logger.info("SYSTEM: Successfully parsed GPT response. Generating users...")

    # Step 2: Create personas and register users
    created_user_ids = []
    for i, persona_data in enumerate(personas, start=1):
        localpart = persona_data.get("localpart")
        displayname = persona_data.get("displayname")
        system_prompt = persona_data.get("system_prompt")
        password = persona_data.get("password")
        traits = persona_data.get("traits", {})

        if not all([localpart, displayname, system_prompt, password]):
            logger.warning(
                "SYSTEM: Skipping persona %d due to missing fields: %s",
                i,
                persona_data,
            )
            continue

        bot_id = f"@{localpart}:localhost"
        logger.info("SYSTEM: Creating persona: %s", bot_id)

        # Save persona to personalities.json
        try:
            create_bot(
                bot_id=bot_id,
                displayname=displayname,
                password=password,
                creator_user_id="@lunabot:localhost",
                system_prompt=system_prompt,
                traits=traits,
                notes=f"Generated for team {team_name} on {datetime.datetime.utcnow().isoformat()}",
            )
            logger.info("SYSTEM: Persona saved to personalities.json: %s", bot_id)
        except Exception as e:
            logger.error("SYSTEM: Error saving persona to file: %s", e)
            continue

        # Register the user in Synapse
        try:
            create_user(localpart, password, is_admin=False)
            logger.info("SYSTEM: User registered in Synapse: %s", bot_id)
            created_user_ids.append(bot_id)
        except Exception as e:
            logger.error("SYSTEM: Error registering user in Synapse: %s", e)

    if not created_user_ids:
        logger.error("SYSTEM: No users were created successfully. Exiting.")
        return

    # Step 3: Create a room for the team
    logger.info("SYSTEM: Creating a room for the team...")
    try:
        room_id = create_room(room_name=f"{team_name} HQ", is_public=True)
        logger.info("SYSTEM: Room created successfully. Room ID: %s", room_id)
    except Exception as e:
        logger.error("SYSTEM: Error creating room: %s", e)
        return

    # Step 4: Invite users to the room
    logger.info("SYSTEM: Inviting users to the room...")
    for user_id in created_user_ids + ["@lunabot:localhost", "@evan:localhost"]:
        try:
            invite_user_to_room(room_id=room_id, user_id=user_id)
            logger.info("SYSTEM: Successfully invited user: %s", user_id)
        except Exception as e:
            logger.error("SYSTEM: Error inviting user: %s", e)

    logger.info("SYSTEM: Team assembly complete. Room created and users invited.")
    print("SYSTEM: Team assembly complete!")
