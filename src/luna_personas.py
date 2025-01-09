# luna_personalities.py
import os
import json
import datetime

PERSONALITIES_FILE = "luna_personalities.json"

def _load_personalities() -> dict:
    """
    Internal helper to load the entire JSON dictionary from disk.
    Returns {} if file not found or invalid.
    """
    if not os.path.exists(PERSONALITIES_FILE):
        return {}
    try:
        with open(PERSONALITIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # If malformed or other error
        return {}


def _save_personalities(data: dict) -> None:
    """
    Internal helper to write the entire JSON dictionary to disk.
    """
    # Using `ensure_ascii=False` to better handle spaces, quotes, and
    # avoid weird escape behavior for non-ASCII. `indent=2` is still fine.
    with open(PERSONALITIES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _sanitize_field(value: str) -> str:
    """
    Strips leading and trailing quotes or whitespace from a field,
    and removes embedded unescaped quotes that might break JSON structure.
    Adjust logic as needed for your environment or console usage.
    """
    if not value:
        return ""

    # Remove leading/trailing quotes/spaces
    cleaned = value.strip().strip('"').strip()

    # Remove any accidental embedded quotes that might fragment JSON
    # (If you prefer to keep them and properly escape them, that is also an option.)
    cleaned = cleaned.replace('"', '')

    return cleaned


def create_bot(
    bot_id: str,
    displayname: str,
    creator_user_id: str,
    system_prompt: str,
    traits: dict | None = None,
    notes: str = ""
) -> dict:
    """
    Creates a new bot persona entry in personalities.json.

    :param bot_id: The Matrix user ID for this bot (e.g. "@mybot:localhost").
    :param displayname: A user-friendly name, e.g. "Anne Bonny".
    :param creator_user_id: The user who spawned this bot (e.g. "@lunabot:localhost").
    :param system_prompt: GPT system text describing the bot’s style/personality.
    :param traits: Optional dictionary with arbitrary traits (age, color, etc.).
    :param notes: Optional freeform text or dev notes.
    :return: The newly created bot data (dict).
    """

    data = _load_personalities()

    # If the bot_id already exists, you might want to error out or update.
    # For now, let's raise an exception to keep it simple.
    if bot_id in data:
        raise ValueError(f"Bot ID {bot_id} already exists in {PERSONALITIES_FILE}.")

    # Clean up potential quotes
    displayname_clean = _sanitize_field(displayname)
    system_prompt_clean = _sanitize_field(system_prompt)
    notes_clean = _sanitize_field(notes)

    # Build the new persona
    persona = {
        "displayname": displayname_clean,
        "system_prompt": system_prompt_clean,
        "traits": traits if traits else {},
        "creator_user_id": creator_user_id,
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",  # e.g. 2025-01-07T14:06:15Z
        "notes": notes_clean
    }

    data[bot_id] = persona
    _save_personalities(data)

    return persona


def update_bot(bot_id: str, updates: dict) -> dict:
    """
    Updates an existing bot persona with given key-value pairs.

    :param bot_id: The Matrix user ID for this bot (e.g. "@mybot:localhost").
    :param updates: A dict of fields to update, e.g. {"displayname": "New Name"}.
    :return: The updated bot data (dict).
    """
    data = _load_personalities()

    if bot_id not in data:
        raise ValueError(f"Bot ID {bot_id} not found in {PERSONALITIES_FILE}.")

    persona = data[bot_id]

    # Clean each field if it's a string
    for key, val in updates.items():
        if isinstance(val, str):
            updates[key] = _sanitize_field(val)

    # Merge updates in
    for key, val in updates.items():
        persona[key] = val

    data[bot_id] = persona
    _save_personalities(data)
    return persona


def read_bot(bot_id: str) -> dict | None:
    """
    Fetch a single bot persona by ID.

    :param bot_id: The Matrix user ID (e.g. "@mybot:localhost").
    :return: The bot's data dict, or None if not found.
    """
    data = _load_personalities()
    return data.get(bot_id)


def delete_bot_persona(bot_id: str) -> None:
    """
    Removes the bot entry from personalities.json.
    Raises KeyError if bot_id not found.
    """
    data = _load_personalities()
    if bot_id not in data:
        raise KeyError(f"Bot ID {bot_id} not found in {PERSONALITIES_FILE}")

    del data[bot_id]  # remove that entry
    _save_personalities(data)
    # no return needed; it either succeeds or raises an exception
