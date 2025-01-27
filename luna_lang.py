# luna_lang.py
import asyncio
import logging

from nio import RoomMessageText, AsyncClient
from langchain.schema import AIMessage, HumanMessage

import luna.GLOBALS as g
from luna.GLOBALS import State
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict
from typing import Annotated

def chatbot_node(state: State):
    """
    A single node function that uses the global LLM to respond to user messages.
    state["messages"] is a list of user/assistant messages (HumanMessage / AIMessage).
    We'll call g.LLM.invoke(...) with that list, then return the new assistant message.
    """

    g.LOGGER.info("chatbot_node called with %d messages", len(state["messages"]))

    if g.LLM is None:
        g.LOGGER.error("Global LLM is None! Did _init_globals not run properly?")
        raise RuntimeError("Global LLM not initialized.")

    # Actually call the LLM
    response_msg = g.LLM.invoke(state["messages"])

    g.LOGGER.info("LLM returned an AIMessage of type: %s", type(response_msg).__name__)
    return {"messages": [response_msg]}


async def handle_user_message(client: AsyncClient, localpart: str, room, event):
    """
    New version of the message handler. Replaces handle_luna_message5.
    Invoked when a RoomMessageText is received in Matrix. 
    It calls chatbot_node(...) to get an AI response, then sends it back to the room.
    """
    # Ignore our own messages to prevent echo loops
    if event.sender == client.user_id:
        return

    # Only handle text messages
    if not isinstance(event, RoomMessageText):
        return

    bot_full_id = client.user
    if event.sender == bot_full_id:
        g.LOGGER.info("Ignoring message from myself: %s", event.sender)
        return

    # 1) ignore old / from self
    if event.server_timestamp < g.BOT_START_TIME:
        g.LOGGER.info("Ignoring old event => %s", event.event_id)
        return
    
    # Extract the user's message text
    user_text = event.body or ""
    user_text = user_text.strip()
    if not user_text:
        return

    g.LOGGER.info(f"[handle_luna_message6] Received message in room {room.display_name or room.room_id} "
                  f"from {event.sender}: {user_text}")

    # Build the “state” for chatbot_node
    # For now, we pass a single new HumanMessage. In real usage, 
    # you might retrieve prior conversation from a store or dictionary, etc.
    state = {
        "messages": [
            HumanMessage(content=user_text)
        ]
    }

    # Call your node function
    result = chatbot_node(state)
    # 'result' is expected to contain {"messages": [AIMessage(...)]}

    if "messages" in result and len(result["messages"]) > 0:
        # Get the new AIMessage
        ai_message = result["messages"][-1]
        if isinstance(ai_message, AIMessage):
            response_text = ai_message.content
        else:
            # Just in case
            response_text = str(ai_message)
    else:
        response_text = "No response."

    # Send the reply back to the Matrix room
    try:
        await client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={
                "msgtype": "m.text",
                "body": response_text
            },
        )
    except Exception as e:
        g.LOGGER.error(f"Error sending message to room {room.room_id}: {e}")
