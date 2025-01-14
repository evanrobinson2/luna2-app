# bot_message_handler.py

import logging
import time
import re
from nio import RoomMessageText, RoomSendResponse

from luna import bot_messages_store2
import luna.context_helper as context_helper
from luna import ai_functions
from luna_invocable import run_action_command

logger = logging.getLogger(__name__)

# Suppose we define a simple pattern like:
ACTION_PATTERN = re.compile(r"```action:(.+)```", re.IGNORECASE)

async def handle_bot_room_message(bot_client, bot_localpart, room, event):
    """
    Steps:
      1) Must not be from ourselves.
      2) Store inbound.
      3) Build GPT context (all prior messages).
      4) Let GPT produce text, possibly with "```action:some_command(args)```" at the end.
      5) Post GPT text as the reply.
      6) If an action directive is found, parse & run it => post results or handle it quietly.
      7) Store outbound message.
    """

    if not isinstance(event, RoomMessageText):
        return

    bot_full_id = bot_client.user
    if event.sender == bot_full_id:
        logger.debug(f"[handle_bot_room_message] ignoring our own message.")
        return

    user_text = event.body or ""
    logger.debug(f"[handle_bot_room_message] inbound from user => '{user_text}'")

    # check if we already stored it
    existing_msgs = bot_messages_store2.get_messages_for_bot(bot_localpart)
    if any(m["event_id"] == event.event_id for m in existing_msgs):
        logger.info(f"[handle_bot_room_message] Duplicate event={event.event_id}, skipping.")
        return

    # Store inbound
    bot_messages_store2.append_message(
        bot_localpart=bot_localpart,
        room_id=room.room_id,
        event_id=event.event_id,
        sender=event.sender,
        timestamp=event.server_timestamp,
        body=user_text
    )

    # We always respond, or you could do a mention/dm check if you want
    config = {"max_history": 10}
    gpt_context = context_helper.build_context(bot_localpart, room.room_id, config)

    # Example: add a system instruction that GPT can “invoke an action”
    # by including a code block with `action:some_command(...)`
    # You might refine or replace this with your own approach:
    system_directive = (
        "You are Luna, a digital agent with special powers. If the user wants an action "
        "like 'create a pirate bot', you can produce a code-fence directive, e.g.:\n"
        "```action:spawn_squad(1,\"pirates\")```\n"
        "Then also produce your normal reply. Always keep your final answer user-friendly.\n"
    )
    # Insert this at the front or overwrite the system_prompt if you prefer
    # We’ll just prepend it as an extra “system message”
    gpt_context.insert(0, {"role": "system", "content": system_directive})

    # Now call GPT
    gpt_reply_text = await ai_functions.get_gpt_response(
        messages=gpt_context,
        model="gpt-4",
        temperature=0.7,
        max_tokens=400
    )

    # We'll post GPT’s text right away
    resp = await bot_client.room_send(
        room_id=room.room_id,
        message_type="m.room.message",
        content={"msgtype": "m.text", "body": gpt_reply_text},
    )

    # Optionally store that outbound
    if isinstance(resp, RoomSendResponse) and resp.event_id:
        bot_messages_store2.append_message(
            bot_localpart=bot_localpart,
            room_id=room.room_id,
            event_id=resp.event_id,
            sender=bot_full_id,
            timestamp=int(time.time()*1000),
            body=gpt_reply_text
        )

    # 6) Check if there's an action directive
    match = ACTION_PATTERN.search(gpt_reply_text)
    if match:
        action_line = match.group(1).strip()  # e.g. 'spawn_squad(1,"pirates")'
        logger.info(f"[handle_bot_room_message] GPT invoked an action => {action_line}")

        # We attempt to parse & run
        action_result = await run_action_command(action_line, bot_client.loop)
        # Then we post the result if you want
        if action_result:
            final_msg = f"**Action Result**:\n{action_result}"
            second_resp = await bot_client.room_send(
                room_id=room.room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": final_msg},
            )
            # optionally store that too
            if isinstance(second_resp, RoomSendResponse) and second_resp.event_id:
                bot_messages_store2.append_message(
                    bot_localpart=bot_localpart,
                    room_id=room.room_id,
                    event_id=second_resp.event_id,
                    sender=bot_full_id,
                    timestamp=int(time.time()*1000),
                    body=final_msg
                )
