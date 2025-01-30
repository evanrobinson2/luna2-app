#!/usr/bin/env python3
"""
luna_lang_router.py

A more advanced handle_luna_message that:
- uses a router_node to decide if user said 'help', 'draw', or something else
- calls the appropriate node
- returns the final AIMessage

We import handle_luna_message in run_luna_lang.py to route
any inbound Matrix message through this subgraph-based logic.

NOTES on LangGraph usage:
 - Each node returns one dict.
 - To branch, include "__next_node__": "node_id" in the dict.
 - Use .stream(...) to iterate states until the final one.

This version implements a single-turn approach: each user message restarts the
graph from START, routes to the correct node, and ends. This avoids infinite
loops and recursion-limit errors.
"""

import luna.GLOBALS as g
from langchain.schema import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from typing_extensions import TypedDict
from typing import Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from datetime import datetime, timezone
from nio import AsyncClient, RoomMessageText
import yaml

##############################################################################
# Define a typed dict for the state
##############################################################################
class RouterState(TypedDict):
    # 'messages' is a list of user + assistant messages
    messages: Annotated[list, add_messages]

##############################################################################
# Node functions
##############################################################################
def _get_available_nodes():
    """Dynamically retrieve all nodes and their descriptions."""
    nodes = {
        "help_node": "Provides a list of available commands.",
        "draw_node": "Generates an image based on user input.",
        "chatbot_node": "Handles general conversation using GPT."
    }
    return "\n".join([f"- {key}: {desc}" for key, desc in nodes.items()])

def gpt_router_node(state: dict) -> dict:
    """Uses GPT to determine the next node dynamically."""
    user_text = state["messages"][-1].content.strip()

    # Load the router prompt template from config.yaml
    prompt_template = g.CONFIG["router_prompt"]

    # Fill in the placeholders with runtime values
    filled_prompt = prompt_template.format(
        node_list= _get_available_nodes(),
        user_input=user_text
    )

    g.LOGGER.info(f"Router Prompt:\n{filled_prompt}")

    # Call GPT to determine the next node
    gpt = ChatOpenAI(model="gpt-4o", temperature=0.2)
    response = gpt.invoke(filled_prompt)

    # Extract and sanitize response
    next_node = response.content.strip().lower()
    if next_node not in ["help_node", "draw_node", "chatbot_node"]:
        g.LOGGER.warning(f"Invalid GPT response: {next_node}, defaulting to chatbot_node")
        next_node = "chatbot_node"

    g.LOGGER.info(f"Routing to: {next_node}")
    return {"__next_node__": next_node}

def router_node(state: RouterState) -> dict:
    """
    If user typed 'help' => help_node
    If user typed 'draw' => draw_node
    else => chatbot_node

    Return a single dict with optional '__next_node__' for dynamic branching.
    """
    g.LOGGER.info("router_node called. Checking messages...")

    if not state["messages"]:
        g.LOGGER.info("No messages in state. Defaulting to chatbot_node.")
        return {"__next_node__": "chatbot_node"}

    last_msg = state["messages"][-1]
    g.LOGGER.info(f"Last message: {last_msg!r}")
    
    g.LOGGER.info(state["messages"])
    if isinstance(last_msg, HumanMessage):
        user_text = last_msg.content.strip().lower()
        g.LOGGER.info(f"Interpreted user_text => {user_text!r}")
        if user_text == "help":
            g.LOGGER.info("Routing to help_node.")
            return {"__next_node__": "help_node"}
        elif user_text.startswith("draw"):
            g.LOGGER.info("Routing to draw_node.")
            return {"__next_node__": "draw_node"}

    g.LOGGER.info("Default routing => chatbot_node.")
    g.LOGGER.info(f"Exiting {__name__} with state: {state}")
    return {"__next_node__": "chatbot_node"}

def help_node(state: RouterState) -> dict:
    """
    Provide a short help text.
    Ends immediately after returning the help message.
    """
    g.LOGGER.info("help_node: Invoked. Preparing help text...")

    help_text = (
        "Available actions:\n"
        "1) 'help' => see this menu\n"
        "2) 'draw' => attempt to generate an image\n"
        "3) anything else => GPT-based reply.\n"
    )
    updated_messages = state["messages"] + [AIMessage(content=help_text)]
    g.LOGGER.info(f"Exiting {__name__} with state: {state}")
    g.LOGGER.info(f"help_node: updated_messages => {updated_messages!r}")
    return {
        "messages": updated_messages,
        "__next_node__": END  # Ensure termination
    }

def draw_node(state: RouterState) -> dict:
    """
    Minimal mock for image generation.
    """
    g.LOGGER.info("draw_node: Invoked. Returning mock drawing link.")

    content = "Here's your (mock) drawing: https://example.com/dalle_mock.jpg"
    updated_messages = state["messages"] + [AIMessage(content=content)]

    g.LOGGER.info(f"draw_node: updated_messages => {updated_messages!r}")
    g.LOGGER.info(f"Exiting {__name__} with state: {state}")
    return {
        "messages": updated_messages,
        "__next_node__": END  # Ensure termination
    }  

def chatbot_node(state: RouterState) -> dict:
    """
    Single-turn GPT logic: read the user's message, call g.LLM, store the reply.
    Ends immediately after returning the LLM response.
    """
    g.LOGGER.info(f"total messages => {len(state['messages'])}")

    if g.LLM is None:
        g.LOGGER.error("Global LLM is None! Returning fallback message.")
        fallback_msgs = state["messages"] + [AIMessage(content="LLM not initialized.")]
        return {"messages": fallback_msgs}

    # The last item in 'messages' is presumably the user's HumanMessage.
    response_msg = g.LLM.invoke(state["messages"])

    if not isinstance(response_msg, AIMessage):
        response_msg = AIMessage(content=str(response_msg))

    g.LOGGER.info(f"response_msg => {response_msg!r}")
    
    updated_messages = state["messages"] + [response_msg]
    g.LOGGER.info(f"response_msg => {updated_messages!r}")
    g.LOGGER.info(f"Exiting {__name__} with state: {state}")
    return {
        "messages": updated_messages,
        "__next_node__": END  # Ensure termination
    }

##############################################################################
# Build the subgraph
##############################################################################
def build_router_graph():
    """
    A small LangGraph with a single-turn flow:
      START -> router_node 
      Then help_node OR draw_node OR chatbot_node -> END

    Each node ends the flow once it has produced its output.
    The next user message restarts the flow from START again.
    """
    builder = StateGraph(RouterState)

    # 1) Add the four node definitions
    builder.add_node("router_node", gpt_router_node)
    builder.add_node("help_node", help_node)
    builder.add_node("draw_node", draw_node)
    builder.add_node("chatbot_node", chatbot_node)

    # 2) Connect START => router_node
    builder.add_edge(START, "router_node")

    # 3) Add **conditional** edges from router_node
    builder.add_conditional_edges(
        "router_node",
        lambda state: state.get("__next_node__", "chatbot_node"),  # Default to chatbot_node if undefined
        path_map={
            "help_node": "help_node",
            "draw_node": "draw_node",
            "chatbot_node": "chatbot_node",
        }
    )

    # 4) Each final node goes to END
    builder.add_edge("help_node", END)
    builder.add_edge("draw_node", END)
    builder.add_edge("chatbot_node", END)

    graph = builder.compile()

    return graph


##############################################################################
# The handle_luna_message function used by run_luna_lang.py
##############################################################################
async def handle_luna_message(client: AsyncClient, localpart: str, room, event):
    """
    Invoked once per incoming user message. Runs the graph from START, 
    generating a single response (via the node chain) and ends.
    """
    g.LOGGER.info(f"Entering handle_luna_message with {event.event_id}")

    # Ignore self-sent messages
    if event.sender == client.user_id:
        g.LOGGER.info("Ignoring self message => %s", event.event_id)
        return  
    if not isinstance(event, RoomMessageText):
        g.LOGGER.info("Ignoring event of type not equal to 'RoomMessageText' => %s", event.event_id)
        return  
    if event.server_timestamp < g.BOT_START_TIME:
        g.LOGGER.info("Ignoring old event => %s", event.event_id)
        return

    # Extract and validate user message
    user_text = (event.body or "").strip()
    if not user_text:
        g.LOGGER.info("Ignoring message with no user_text => %s", event.event_id)
        return

    # Ignore duplicate event processing
    if event.event_id in g.PROCESSED_EVENTS:
        g.LOGGER.info(f"Skipping duplicate event {event.event_id}")
        return  

    g.PROCESSED_EVENTS.add(event.event_id)  
    g.LOGGER.info(f"Adding {event.event_id} to PROCESSED_EVENTS")
    g.LOGGER.info("user_text => %r", user_text)

    # Start typing indicator
    await _start_typing(client, room.room_id)

    # Build the initial state with the user's message
    state: RouterState = {
        "messages": [HumanMessage(content=user_text)]
    }

    final_state = None

    # Stream graph execution and log each step
    for partial_state in g.ROUTER_GRAPH.stream(state):
        g.LOGGER.info(f"partial_state => {partial_state!r}")
        final_state = partial_state

    g.LOGGER.info(f"final_state => {final_state!r}")

    # Look for a response in any terminal node
    msgs = None
    for node in ["chatbot_node", "help_node", "draw_node"]:
        if node in final_state and "messages" in final_state[node]:
            msgs = final_state[node]["messages"]
            g.LOGGER.info(f"Response found in {node}.")
            break  

    if not msgs:
        g.LOGGER.warning("🚨 No response message found. Skipping send.")
        return

    # Extract the last AIMessage
    last_msg = msgs[-1]
    response_text = last_msg.content if isinstance(last_msg, AIMessage) else str(last_msg)

    g.LOGGER.info(f"Sending response: {response_text!r}")

    # Send the final response to the Matrix room
    try:
        await client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": response_text}
        )
    except Exception as e:
        g.LOGGER.exception(f"Error sending message => {e}")
    finally:
        await _stop_typing(client, room.room_id)

    # Ensure the processed events set doesn't grow infinitely
    if len(g.PROCESSED_EVENTS) > 10000:  
        g.PROCESSED_EVENTS.clear()  


async def handle_luna_message_dep(client: AsyncClient, localpart: str, room, event):
    """
    Invoked once per incoming user message. Runs the graph from START, 
    generating a single response (via the node chain) and ends.
    """
    g.LOGGER.info(f"Entering handle_luna_message with {event.event_id}")

    if event.sender == client.user_id:
        g.LOGGER.info("Ignoring self message => %s", event.event_id)
        return  # ignore our own messages
    if not isinstance(event, RoomMessageText):
        g.LOGGER.info("Ignoring event of type not equal to 'RoomMessageText' => %s", event.event_id)
        return  # ignore non-text events
    
    if event.server_timestamp < g.BOT_START_TIME:
        g.LOGGER.info("Ignoring old event => %s", event.event_id)
        return

    user_text = (event.body or "").strip()
    if not user_text:
        g.LOGGER.info("Ignoring message with no user_text => %s", event.event_id)
        return
    
    # ignore multiple events so we don't process the same message multiple times.
    if event.event_id in g.PROCESSED_EVENTS:
        g.LOGGER.info(f"Skipping duplicate event {event.event_id}")
        return  # Ignore duplicate processing

    g.PROCESSED_EVENTS.add(event.event_id)  # Mark event as processed
    g.LOGGER.info(f"Adding {event.event_id} to PROCESSED_EVENTS")
    g.LOGGER.info("user_text => %r", user_text)
    
    await _start_typing(client, room.room_id)

    # Build the initial state with the user's message
    state: RouterState = {
        "messages": [HumanMessage(content=user_text)]
    }

    final_state = None

    # .stream(...) runs the graph until END. 
    for partial_state in g.ROUTER_GRAPH.stream(state):
        g.LOGGER.info(f"partial_state => {partial_state!r}")
        final_state = partial_state

    g.LOGGER.info(f"final_state => {final_state!r}")

    # Look for the chatbot_node output
    if not final_state:
        return
    if "chatbot_node" not in final_state:
        return
    if "messages" not in final_state["chatbot_node"]:
        return

    msgs = final_state["chatbot_node"]["messages"]
    if not msgs:
        return

    for step in g.ROUTER_GRAPH.stream({"messages": []}, debug=True):
        g.LOGGER.info(f"Graph Execution Step: {step}")

    # The final AIMessage is the system's reply
    last_msg = msgs[-1]
    if isinstance(last_msg, AIMessage):
        response_text = last_msg.content
    else:
        response_text = str(last_msg)

    # Post the final text to the Matrix room
    try:
        await client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": response_text}
        )
    except Exception as e:
        g.LOGGER.exception(f"Error sending message => {e}")
    finally:
        await _stop_typing(client, room.room_id)

    # Ensure the set doesn't grow infinitely
    if len(g.PROCESSED_EVENTS) > 10000:  # Adjust limit as needed
        g.PROCESSED_EVENTS.clear()    

async def _start_typing(bot_client: AsyncClient, room_id: str):
    try:
        await bot_client.room_typing(room_id, True, timeout=5000)
        g.LOGGER.info("Typing start => %s", room_id)
    except Exception as e:
        g.LOGGER.warning("Could not send typing start => %s", e)

async def _stop_typing(bot_client: AsyncClient, room_id: str):
    try:
        await bot_client.room_typing(room_id, False, timeout=0)
    except Exception as e:
        g.LOGGER.warning("Could not send typing stop => %s", e)
