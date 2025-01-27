# summarize_pipeline.py

import logging
import json
from typing import Optional
import re
import asyncio
from nio import AsyncClient, RoomSendResponse

# Import from your codebase
from luna.bot_messages_store import BOT_MESSAGES_DB
from luna.ai_functions import get_gpt_response
from luna.luna_command_extensions.command_router import GLOBAL_PARAMS, load_config
from luna.luna_command_extensions.command_helpers import _keep_typing, _post_in_thread, _strip_html_tags

logger = logging.getLogger(__name__)

async def run_summarize_pipeline(
    bot_client: AsyncClient,
    room_id: str,
    event_id: str,
    user_prompt_str: str,
    bot_localpart: str = "lunabot"
) -> None:
    """
    The top-level function that:
      1) Calls GPT #1 (Query Builder) to produce a SELECT query for conversation logs.
      2) Posts a partial “Gathering data…” message in-thread.
      3) Executes the query or falls back if invalid.
      4) Calls GPT #2 (Summarizer) with the retrieved logs.
      5) Posts the final summary in-thread.

    :param bot_client:   The AsyncClient for Luna or whichever bot is in use.
    :param room_id:      The room where user typed "!summarize ...".
    :param event_id:     The specific event we want to reply to in-thread.
    :param user_prompt_str: The user’s instructions for summarizing, e.g. "Focus on comedic highlights"
    :param bot_localpart: The bot's localpart, defaults to "lunabot" if not specified.
    """

    typing_task = asyncio.create_task(_keep_typing(bot_client, room_id))


    # 1) GPT #1 => Query
    qb_output = await _gpt_query_builder(user_prompt_str, room_id)

    desc_sentence = "[run_summarize_pipeline] Unset Variable"
    # 3) Check if qb_output is valid JSON with "query", "confidence_level", "comments".
    if not qb_output or not qb_output.strip():
        # Fallback to a known safe query => last 50 messages
        query_sql = f"SELECT * FROM bot_messages ORDER BY timestamp DESC LIMIT 50"
        logger.warning("[SummarizePipeline] Query builder returned empty. Falling back to last 50 messages.")
    else:
        # Attempt JSON parse
        try:
            qb_output_clean = qb_output.strip()

            # Remove ```json or ```
            qb_output_clean = re.sub(r"^```json\s*", "", qb_output_clean)
            qb_output_clean = re.sub(r"^```\s*", "", qb_output_clean)
            qb_output_clean = re.sub(r"\s*```$", "", qb_output_clean)

            qb_data = json.loads(qb_output_clean)

            desc_sentence = qb_data.get("query_description_sentence")
            query_sql = qb_data.get("query", "")
            if not query_sql.upper().startswith("SELECT"):
                # Fallback if the user tries to do something other than SELECT
                raise ValueError("Non-SELECT or empty query returned.")
        except Exception as e:
            desc_sentence = "No query description provided."
            logger.warning(f"[SummarizePipeline] Query builder JSON parse error => {e}")
            # Fallback
            query_sql = f"SELECT * FROM bot_messages ORDER BY timestamp DESC LIMIT 50"

    # 2) Post a partial message => "Got it, Gathering data..."    
    partial_html = (
        f"<p><strong>Creating your summary. Remember summaries can take up to a minute or longer in some cases!</strong></p>"
        f"<p><em>{desc_sentence}</em></p>"
    )

    await _post_in_thread(
        bot_client,
        room_id,
        event_id,
        partial_html,
        is_html=True
    )


    # 4) Execute the query
    rows = await _execute_query(query_sql)

    # If no rows or error, fallback to simpler approach
    if rows is None:
        # Possibly fallback to a default “last 50 messages”
        fallback_sql = "SELECT * FROM bot_messages ORDER BY timestamp DESC LIMIT 50"
        rows = await _execute_query(fallback_sql)
        if not rows:
            # Then we have absolutely no data; can post a final note
            await _post_in_thread(
                bot_client,
                room_id,
                event_id,
                "SYSTEM: No messages to summarize (or query error)."
            )
            return

    # 5) GPT #2 => Summarizer with error handling
    try:
        summary_text = await _gpt_summarizer(rows, user_prompt_str)
    except Exception as e:
        # Check if it's specifically a 'context_length_exceeded' or large context error
        if "context_length_exceeded" in str(e) or "maximum context length" in str(e):
            logger.warning("[SummarizePipeline] Summarizer exceeded context length. Retrying with fewer rows.")
            # For simplicity, let’s just cut the rows in half; you can do more advanced chunking if desired.
            half_len = len(rows) // 2
            rows_subset = rows[:half_len]

            # Attempt a second summarizer call with fewer rows
            try:
                summary_text = await _gpt_summarizer(rows_subset, user_prompt_str)
            except Exception as second_e:
                logger.exception("[SummarizePipeline] Second attempt also failed =>")
                summary_text = f"SYSTEM: Summarization failed again. Error => {second_e}"
        else:
            # Some other error that is not related to context length
            logger.exception("[SummarizePipeline] Summarizer error =>")
            summary_text = f"SYSTEM: Summarization failed. Error => {e}"

    # 6) Post final summary in the same thread
    if not summary_text.strip():
        summary_text = "SYSTEM: Summarization returned no text (empty)."

    final_html = f"<p><strong>Here is your summary:</strong></p><p>{summary_text}</p>"

    await _post_in_thread(
        bot_client,
        room_id,
        event_id,
        final_html,
        is_html=True
    )

    typing_task.cancel()

# ----------------------------------------------------------------
# GPT #1 - Query Builder
# ----------------------------------------------------------------
async def _gpt_query_builder(user_prompt: str, room_id) -> str:
    """
    Calls GPT to convert the user’s natural-language summarization request
    into a JSON object with fields: { query, confidence_level, comments }.
    The query is a SELECT from 'bot_messages' referencing columns: 
      bot_localpart, room_id, event_id, sender, timestamp, body

    Returns GPT’s raw string (which we assume is JSON).
    On failure or exception, returns an empty string.
    """
    # 1) Load instructions from config.yaml
    cfg = load_config()
    qb_instructions = cfg.get("summarize_flow", {}).get("query_builder_instructions", "")
    if not qb_instructions:
        qb_instructions = (
            "You are a Query Builder AI. User will give summarization instructions. Instruction source: Fallback Hardcode."
            "Return JSON with {query, confidence_level, comments, query_description_sentence=\"Fallback Query\"} for a SELECT statement."
        )

    logger.info(f"[_gpt_query_builder] Buiding QueryBuilder with {qb_instructions}")
    
    # 2) Build the system + user messages
    system_prompt = qb_instructions

    user_content = (
        f"User's request: {user_prompt}\n\n"
        f"The relevant room is '#{room_id}:localhost'. If the user wants to filter to this room, "
        f"remember to use: WHERE room_id = '{room_id}'.\n\n"
        "Note: There is a supervisor bot named 'Luna' in this channel. "
        "The user may want to exclude these messages or handle them specially.\n\n"
        "Please respond with a valid JSON object per the system's instructions."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_content},
    ]

    # 3) Call GPT
    try:
        resp_text = await get_gpt_response(
            messages=messages,
            temperature=0.7,
            model="gpt-4o"
        )
        return resp_text
    except Exception as e:
        logger.exception("[SummarizePipeline] GPT QueryBuilder error =>")
        return ""

# ----------------------------------------------------------------
# Execute the SQL query
# ----------------------------------------------------------------
async def _execute_query(sql_str: str) -> Optional[list]:
    """
    Runs the given SQL SELECT against the 'bot_messages.db' file, 
    returning a list of rows as dicts. If an error occurs, returns None.
    """
    import sqlite3
    if not sql_str.strip().upper().startswith("SELECT"):
        logger.warning("[_execute_query] Non-SELECT or empty SQL => fallback needed.")
        return None

    try:
        conn = sqlite3.connect(BOT_MESSAGES_DB)
        c = conn.cursor()
        rows = c.execute(sql_str).fetchall()
        # We assume the columns are in order:
        #   id, bot_localpart, room_id, event_id, sender, timestamp, body
        # But the user might have done custom SELECT. So we do a quick approach:
        columns = [desc[0] for desc in c.description]
        results = []
        for raw_row in rows:
            row_dict = {}
            for col, val in zip(columns, raw_row):
                row_dict[col] = val
            results.append(row_dict)

        conn.close()
        logger.debug(f"Query returned {len(results)} rows. First row => {results[0] if results else 'N/A'}")
        return results

    except Exception as e:
        logger.warning(f"Error executing user query => {e}")
        return None


async def _gpt_summarizer(rows: list, user_prompt: str) -> str:
    """
    Takes the DB result rows (list of dicts) and calls GPT to produce a final summary.
    Automatically chunks the logs if there are too many, creating partial summaries,
    then merges them into one final summary pass to keep token usage manageable.
    """
    from math import ceil

    cfg = load_config()
    sum_instructions = cfg.get("summarize_flow", {}).get("summarizer_instructions", "")
    if not sum_instructions:
        sum_instructions = (
            "You are a Summarizer AI. Produce a coherent summary from the user's instructions and logs."
        )

    # Decide on a chunk size. Adjust as needed.
    chunk_size = 50

    # ----------------------------------------------------------------
    # If rows fit comfortably in one chunk, just do a single pass
    # ----------------------------------------------------------------
    if len(rows) <= chunk_size:
        return await _summarize_chunk(rows, user_prompt, sum_instructions)

    # ----------------------------------------------------------------
    # Otherwise, chunk the rows and summarize each chunk
    # ----------------------------------------------------------------
    partial_summaries = []
    total_chunks = ceil(len(rows) / chunk_size)

    logger.info(f"[_gpt_summarizer] Splitting {len(rows)} rows into {total_chunks} chunks of size {chunk_size}.")

    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        # Summarize this chunk
        chunk_summary = await _summarize_chunk(chunk, user_prompt, sum_instructions, is_partial=True, chunk_index=(i // chunk_size) + 1)
        partial_summaries.append(chunk_summary)

    # ----------------------------------------------------------------
    # If there's only 1 partial summary for some reason, return it
    # ----------------------------------------------------------------
    if len(partial_summaries) == 1:
        return partial_summaries[0]

    # ----------------------------------------------------------------
    # Otherwise, do a final "summary-of-summaries" pass
    # ----------------------------------------------------------------
    logger.info("[_gpt_summarizer] Combining partial summaries into final summary.")

    # We’ll build a user prompt that merges all partial summaries
    # so GPT can produce a single cohesive result.
    partials_text = "\n\n".join(
        f"Partial summary {idx+1}:\n{ps}" for idx, ps in enumerate(partial_summaries)
    )
    user_text = (
        "You have multiple partial summaries of a large conversation. "
        "Combine them into one cohesive final summary, following the original user instructions:\n\n"
        f"User's summary instructions: {user_prompt}\n\n"
        "Here are the partial summaries:\n"
        f"{partials_text}\n"
    )

    messages = [
        {"role": "system", "content": "You are a Summarizer AI. Merge partial summaries into one final coherent summary."},
        {"role": "user",   "content": user_text},
    ]

    try:
        final_summary = await get_gpt_response(
            messages=messages,
            temperature=0.7,
            max_tokens=2000
        )
        return final_summary.strip()
    except Exception as e:
        logger.exception("[_gpt_summarizer] Final merge pass error =>")
        return "SYSTEM: Summarization failed during final merge pass."


async def _summarize_chunk(rows_chunk: list, user_prompt: str, sum_instructions: str, is_partial=False, chunk_index=1) -> str:
    """
    Summarizes a single chunk of conversation logs with GPT.
    If is_partial=True, we'll label it a partial summary (helpful for logging).
    """
    # Convert rows into text lines
    lines = []
    for r in rows_chunk:
        sender = str(r.get("sender", "unknown"))
        body = str(r.get("body", ""))
        lines.append(f"{sender}: {body}")
    logs_text = "\n".join(lines)

    # Build system & user messages
    # If partial, you can tweak instructions for a more concise summary:
    system_text = sum_instructions
    if is_partial:
        system_text += (
            "\n\nReturn a concise partial summary. We'll combine it with other chunks later."
        )

    user_text = (
        f"Below are {len(rows_chunk)} logs from conversation.\n"
        f"User's summary instructions: {user_prompt}\n\n"
        f"Conversation logs:\n{logs_text}"
    )

    messages = [
        {"role": "system", "content": system_text},
        {"role": "user",   "content": user_text},
    ]

    try:
        summary = await get_gpt_response(
            messages=messages,
            temperature=0.7,
            max_tokens=2000
        )
        logger.info(f"[_summarize_chunk] Summarized chunk #{chunk_index}, length={len(rows_chunk)} => {len(summary)} chars")
        return summary.strip()
    except Exception as e:
        logger.exception("[_summarize_chunk] GPT Summarizer error =>")
        return f"SYSTEM: Summarization failed for chunk #{chunk_index}."
