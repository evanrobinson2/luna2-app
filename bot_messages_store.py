#!/usr/bin/env python3
"""
bot_messages_store.py

Drop-in replacement for the original JSON-based message store.
Instead of reading/writing a .json file, we store messages in an SQLite DB.
We keep the same 4 main functions:
    load_messages()
    save_messages()
    append_message(bot_localpart, room_id, event_id, sender, timestamp, body)
    get_messages_for_bot(bot_localpart)

Internally, we rely on a table named "bot_messages" with columns:
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_localpart TEXT,
    room_id      TEXT,
    event_id     TEXT,
    sender       TEXT,
    timestamp    INTEGER,
    body         TEXT

Notes:
  - We replicate the old behavior, so load_messages() and save_messages() still exist
    but are partially no-ops. We don't need to load everything into memory,
    but we do so for completeness. In real usage, you might prefer direct SELECT calls.
  - The interface is intentionally minimal to mimic the prior JSON store.
"""

import os
import logging
import sqlite3
from typing import List, Dict

logger = logging.getLogger(__name__)

# Adjust if desired
BOT_MESSAGES_DB = "data/bot_messages.db"

# In-memory cache (optional, to mimic the old JSON approach).
# If you prefer to query the DB on each call, you can skip this.
_in_memory_list: List[Dict] = []


def load_messages() -> None:
    """
    Sets up the SQLite DB (creating the table if needed), then loads all rows
    into the global _in_memory_list to mimic the old JSON behavior.
    """
    global _in_memory_list
    logger.info("[load_messages] Setting up the DB & loading messages into memory.")

    # Ensure data folder if needed
    os.makedirs(os.path.dirname(BOT_MESSAGES_DB), exist_ok=True)

    # 1) Create table if not exist
    create_sql = """
    CREATE TABLE IF NOT EXISTS bot_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_localpart TEXT,
        room_id TEXT,
        event_id TEXT,
        sender TEXT,
        timestamp INTEGER,
        body TEXT
    )"""
    try:
        conn = sqlite3.connect(BOT_MESSAGES_DB)
        c = conn.cursor()
        c.execute(create_sql)
        conn.commit()
        # 2) Load all messages into _in_memory_list
        rows = c.execute("SELECT bot_localpart, room_id, event_id, sender, timestamp, body FROM bot_messages").fetchall()

        _in_memory_list.clear()
        for row in rows:
            record = {
                "bot_localpart": row[0],
                "room_id": row[1],
                "event_id": row[2],
                "sender": row[3],
                "timestamp": row[4],
                "body": row[5],
            }
            _in_memory_list.append(record)

        conn.close()
        logger.info(f"[load_messages] Loaded {_in_memory_list.__len__()} rows from DB into memory.")
    except Exception as e:
        logger.exception(f"[load_messages] Failed to set up DB or load messages: {e}")
        _in_memory_list = []


def save_messages() -> None:
    """
    We keep this function to match the previous interface.
    In an SQLite approach, appends are typically committed immediately.
    So this is effectively a no-op, or can re-sync memory with the DB if needed.
    """
    logger.info("[save_messages] No-op in SQLite approach (data is committed on append).")


def append_message(
    bot_localpart: str,
    room_id: str,
    event_id: str,
    sender: str,
    timestamp: int,
    body: str
) -> None:
    """
    Inserts a single new row into the "bot_messages" table,
    and also updates the in-memory list if you prefer to keep that synchronized.

    :param bot_localpart: e.g. "lunabot"
    :param room_id: e.g. "!abc123:localhost"
    :param event_id: e.g. "$someUniqueEventId"
    :param sender: e.g. "@someuser:localhost"
    :param timestamp: e.g. 1736651234567
    :param body: message text
    """
    global _in_memory_list
    try:
        conn = sqlite3.connect(BOT_MESSAGES_DB)
        c = conn.cursor()

        insert_sql = """
        INSERT INTO bot_messages (bot_localpart, room_id, event_id, sender, timestamp, body)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        c.execute(insert_sql, (bot_localpart, room_id, event_id, sender, timestamp, body))
        conn.commit()
        conn.close()

        # Optionally keep our in-memory list in sync
        record = {
            "bot_localpart": bot_localpart,
            "room_id": room_id,
            "event_id": event_id,
            "sender": sender,
            "timestamp": timestamp,
            "body": body
        }
        _in_memory_list.append(record)

        logger.info(f"[append_message] Inserted event_id={event_id} for bot={bot_localpart} into DB.")
    except Exception as e:
        logger.exception(f"[append_message] Error inserting message => {e}")


def get_messages_for_bot(bot_localpart: str) -> List[Dict]:
    """
    Returns a list of messages from the DB for the given bot, sorted by timestamp ascending.
    We can either:
      - Query in-memory if you prefer the old approach
      - or do a direct SELECT with an ORDER BY.

    Here, we do a direct SELECT to be robust.
    """

    try:
        conn = sqlite3.connect(BOT_MESSAGES_DB)
        c = conn.cursor()
        select_sql = """
        SELECT bot_localpart, room_id, event_id, sender, timestamp, body
        FROM bot_messages
        WHERE bot_localpart = ?
        ORDER BY timestamp ASC
        """
        rows = c.execute(select_sql, (bot_localpart,)).fetchall()
        conn.close()

        results = []
        for row in rows:
            record = {
                "bot_localpart": row[0],
                "room_id": row[1],
                "event_id": row[2],
                "sender": row[3],
                "timestamp": row[4],
                "body": row[5],
            }
            results.append(record)

        logger.info(f"[get_messages_for_bot] Found {len(results)} messages for '{bot_localpart}'.")
        return results

    except Exception as e:
        logger.exception(f"[get_messages_for_bot] Error selecting messages => {e}")
        return []

