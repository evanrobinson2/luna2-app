import os
import json
import logging

logger = logging.getLogger(__name__)

BOT_MESSAGES_FILE = "data/bot_messages.json"

# We’ll keep the in-memory list here once loaded
_bot_messages = []  # each entry is {bot_localpart, room_id, event_id, timestamp, sender, body, ...}


def load_messages() -> None:
    """
    Loads the entire message list from BOT_MESSAGES_FILE into
    the global _bot_messages list in memory.
    If the file doesn’t exist or is invalid, we start with an empty list.
    """
    global _bot_messages

    if not os.path.exists(BOT_MESSAGES_FILE):
        logger.warning(f"{BOT_MESSAGES_FILE} not found. Starting with empty messages list.")
        _bot_messages = []
        return

    try:
        with open(BOT_MESSAGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                _bot_messages = data
            else:
                logger.warning(f"{BOT_MESSAGES_FILE} does not contain a list. Starting empty.")
                _bot_messages = []
    except Exception as e:
        logger.exception(f"Error loading {BOT_MESSAGES_FILE}: {e}")
        _bot_messages = []


def save_messages() -> None:
    """
    Saves the current in-memory _bot_messages list to BOT_MESSAGES_FILE.
    """
    global _bot_messages

    try:
        with open(BOT_MESSAGES_FILE, "w", encoding="utf-8") as f:
            json.dump(_bot_messages, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {_bot_messages.__len__()} messages to {BOT_MESSAGES_FILE}.")
    except Exception as e:
        logger.exception(f"Error saving to {BOT_MESSAGES_FILE}: {e}")


def append_message(
    bot_localpart: str,
    room_id: str,
    event_id: str,
    sender: str,
    timestamp: int,
    body: str
) -> None:
    """
    Appends a single new record to the in-memory list, then saves to disk.

    :param bot_localpart: e.g. "lunabot", "blended_malt", ...
    :param room_id: e.g. "!abc123:localhost"
    :param event_id: e.g. "$someUniqueEventId"
    :param sender: e.g. "@user:localhost"
    :param timestamp: e.g. 1736651234567
    :param body: message text
    """
    global _bot_messages

    record = {
        "bot_localpart": bot_localpart,
        "room_id": room_id,
        "event_id": event_id,
        "sender": sender,
        "timestamp": timestamp,
        "body": body
    }

    _bot_messages.append(record)
    # Optionally check for duplicates if desired
    # Or you might want to do a "drop_duplicates" approach
    save_messages()


def get_messages_for_bot(bot_localpart: str):
    """
    Returns a new list of all messages in memory for the specified bot,
    sorted by ascending timestamp (or descending, as you prefer).
    """
    # Filter in-memory
    relevant = [m for m in _bot_messages if m["bot_localpart"] == bot_localpart]

    # Sort by timestamp ascending
    relevant.sort(key=lambda x: x["timestamp"])
    return relevant
