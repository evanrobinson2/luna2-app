import json
import asyncio

from src.ai_functions import get_gpt_response  # or however you've structured your import
from src.luna_functions import create_user as matrix_create_user  # presumably in your code already
import src.luna_personas

def cmd_create_inspired_bot(args, loop):
    """
    Usage:
      create_bot_inspired <inspiration_text>
    """

    if not args.strip():
        print("SYSTEM: No inspiration provided. Please give a short string describing the persona idea.")
        return

    system_instructions = (
        "You are a helpful assistant that must respond only with a single valid JSON object. "
        "The JSON object must include exactly these fields: localpart, displayname, system_prompt, password, and traits. "
        "The 'traits' field should be a JSON object (with zero or more key-value pairs). "
        "Do not include any extra keys or text. Do not wrap your response in Markdown or code fences. "
        "Do not provide any explanations—only raw JSON. "
        "Any additional text or formatting outside the JSON object will invalidate the response. "
        "INVALID: Sure, here's an example of a JSON that represents a person's contact details ```json..."
    )

    user_prompt = (
        f"Generate a persona from this inspiration: '{args}'. "
        f"The persona can be imaginative or grounded, but must be returned as raw JSON."
    )

    # We’ll call get_gpt_response asynchronously
    # (similar to how you do with matrix_create_user)
    # so we run it in the existing event loop with `run_coroutine_threadsafe`.
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
        print(f"SYSTEM: Error calling GPT => {e}")
        return

    # Now we expect the GPT response to be valid JSON. Let's parse it.
    try:
        persona_data = json.loads(gpt_raw_response)
    except json.JSONDecodeError as e:
        print(f"SYSTEM: GPT returned invalid JSON => {e}")
        print("SYSTEM: Raw GPT response was:")
        print(gpt_raw_response)
        return

    # Print out the data we got from GPT
    print("SYSTEM: GPT suggested the following persona data:")
    print(json.dumps(persona_data, indent=2))

    # Optionally, auto-create the persona from GPT's output:
    localpart = persona_data.get("localpart")
    displayname = persona_data.get("displayname")
    system_prompt = persona_data.get("system_prompt")
    password = persona_data.get("password")
    traits = persona_data.get("traits", {})

    # Basic checks
    required = [("localpart", localpart), ("displayname", displayname),
                ("system_prompt", system_prompt), ("password", password)]
    missing_fields = [name for (name, val) in required if not val]
    if missing_fields:
        print(f"SYSTEM: GPT persona is missing required fields: {missing_fields}")
        return

    bot_id = f"@{localpart}:localhost"

    # Step A: Create local persona
    try:
        persona = src.luna_personas.create_bot(
            bot_id=bot_id,
            password=password,
            displayname=displayname,
            creator_user_id="@lunabot:localhost",
            system_prompt=system_prompt,
            traits=traits
        )
        print(f"SYSTEM: Local persona created => {persona}")
    except Exception as e:
        print(f"SYSTEM: Unexpected error => {e}")
        return

    # Step B: Register user with Synapse (async call)
    from src.luna_functions import create_user as matrix_create_user
    fut_reg = asyncio.run_coroutine_threadsafe(
        matrix_create_user(localpart, password, is_admin=False),
        loop
    )
    try:
        result_msg = fut_reg.result()
        print(f"SYSTEM: Matrix user creation => {result_msg}")
    except Exception as e:
        print(f"SYSTEM: Error creating matrix user => {e}")
