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

import os
import urllib
import json
import markdown
import bleach
import asyncio
import json
import time
import requests
import logging
import json
import time
import html
import aiohttp
import re
from typing_extensions import TypedDict
from typing import Annotated, Dict, List

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from typing import Dict
from nio import AsyncClient, RoomMessageText, RoomSendResponse, RoomCreateResponse, RoomCreateError, RoomVisibility

from langchain.schema import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from luna.ai_functions import get_gpt_response
from luna.luna_command_extensions.create_and_login_bot import create_and_login_bot
from luna.luna_personas import update_bot
import luna.GLOBALS as g


##############################################################################
# Define a typed dict for the state
##############################################################################
from typing_extensions import TypedDict
from typing import List, Annotated
from langgraph.graph.message import add_messages

class RouterState(TypedDict):
    messages: Annotated[List, add_messages]
    macro_sequence: List[dict]
    macro_step_index: int
    room_id: str
    raw_args: str  # or optional?
    sender: str    # The user’s Matrix ID, e.g. "@alice:localhost"
    parent_event_id: str


def build_router_graph():
    """
    A small LangGraph flow:
      START -> router_node
        -> help_node -> END
        -> draw_node -> END
        -> chatbot_node -> END
        -> planner_node -> macro_node -> summarize_state_with_gpt -> loop or END

    'planner_node' is chosen if the user request involves multiple steps/sequences.
    'macro_node' can loop on itself until steps are complete, then end.
    Each node ends after producing output, returning control to the user
    (or in planner_node's / macro_node's case, it may handle multi-step logic).
    The next user message restarts from START again.
    """
    # Make sure we have a dictionary-of-dictionaries in g.NODE_REGISTRY
    # Each entry => "node_name": { "func": <callable>, "desc": <string> }
    g.NODE_REGISTRY.update({
        "gpt_router_node": {
            "func": gpt_router_node,
            "desc": "Router that uses GPT to pick the next node.",
            "scopes": ["system"],
            "args": {}
        },
        "help_node": {
            "func": help_node,
            "desc": "Provides a list of available commands.",
            "scopes": ["router"],
            "args": {}
        },
        "draw_node": {
            "func": draw_node,
            "desc": "Generates an image based on user input.",
            "scopes": ["planner"],
            "args": {
                "prompt": {
                    "type": "string",
                    "desc": "User-provided text describing the desired image.",
                    "required": True
                },
                "style": {
                    "type": "string",
                    "desc": "Optional. Style or additional constraints.",
                    "required": False
                }
            }
        },
        "chatbot_node": {
            "func": chatbot_node,
            "desc": "Handles general conversation using GPT.",
            "scopes": ["planner"],
            "args": {
                "context": {
                    "type": "string",
                    "desc": "Additional context for GPT.",
                    "required": False
                }
            }
        },
        "macro_node": {
            "func": macro_node,
            "desc": "Executes a sequence of node calls from state['macro_sequence'].",
            "scopes": ["system"],
            "args": {}
        },
        "planner_node": {
            "func": planner_node,
            "desc": "Determines a sequence of node calls for state['macro_sequence'].",
            "scopes": ["router"],
            "args": {}
        },
        "create_room3_node": {
            "func": create_room3_node,
            "desc": (
                "Creates a new Matrix room using JSON-style input parameters.\n"
                "Parameters:\n"
                "  - name: (string, required) The localpart for the new room alias and room name.\n"
                "  - prompt: (string, optional) The room topic or additional prompt for avatar generation.\n"
                "  - set_avatar: (boolean, optional) If true, the node will generate an image from the prompt "
                "and set it as the room avatar.\n"
                "  - invite: (list, optional) A list of user IDs (e.g. '@user:server') to invite to the room. The sender is automatically invited.\n"
                "  - additional_flag: (object, optional) A JSON object with extra parameters (e.g. {'style': 'fantasy'})."
            ),
            "scopes": ["planner"],
            "args": {
                "name": {
                    "type": "string",
                    "desc": "The required localpart for the new room alias and room name.",
                    "required": True
                },
                "prompt": {
                    "type": "string",
                    "desc": "Optional. The room topic or additional prompt for avatar generation.",
                    "required": False
                },
                "set_avatar": {
                    "type": "boolean",
                    "desc": "Optional. If true, the node will generate an image from the prompt and set it as the room avatar.",
                    "required": False
                },
                "invite": {
                    "type": "list",
                    "desc": "Optional. A list of user IDs to invite to the room.",
                    "required": False
                },
                "additional_flag": {
                    "type": "object",
                    "desc": "Optional. A JSON object containing extra parameters (e.g. {'style': 'fantasy'}).",
                    "required": False
                }
            }
        },
        "spawn_persona_node": {
            "func": spawn_persona_node,
            "desc": (
                "Generates and registers a new persona using a given descriptor. "
                "This node uses GPT to generate a persona JSON, logs in the persona as a bot, optionally "
                "generates a portrait, and returns an HTML character card along with the normalized bot ID."
            ),
            "scopes": ["planner"],
            "args": {
                "descriptor": {
                    "type": "string",
                    "desc": "A textual descriptor for the persona to be generated.",
                    "required": True
                }
            }
        }        
    })


    # Use RouterState (or dict) as needed
    builder = StateGraph(RouterState)

    # 1) Add node definitions
    builder.add_node("router_node", gpt_router_node)
    builder.add_node("help_node", help_node)
    builder.add_node("draw_node", draw_node)
    builder.add_node("chatbot_node", chatbot_node)
    builder.add_node("macro_node", macro_node)
    builder.add_node("planner_node", planner_node)
    builder.add_node("create_room3_node", create_room3_node)
    builder.add_node("spawn_persona_node", spawn_persona_node)
    
    # 2) Connect START => router_node
    builder.add_edge(START, "router_node")

    # 3) Add conditional edges from router_node
    builder.add_conditional_edges(
        "router_node",
        lambda state: state.get("__next_node__", "chatbot_node"),         # Default = 'chatbot_node'
        path_map={
            "help_node": "help_node",
            "draw_node": "draw_node",
            "chatbot_node": "chatbot_node",
            "planner_node": "planner_node",
            "create_room3_node": "create_room3_node",
            "spawn_persona_node": "spawn_persona_node"
        }
    )

    builder.add_conditional_edges(
        "macro_node",
        # Decide if we still have steps left
        lambda s: "macro_node" if s["macro_step_index"] < len(s["macro_sequence"]) 
                                    else END,
        path_map={
            "macro_node": "macro_node",
            END: END
        }
    )

    builder.add_edge("planner_node", "macro_node") # planner_node => macro_node
    builder.add_edge("create_room3_node", "chatbot_node") # planner_node => macro_node
    builder.add_edge("spawn_persona_node", "chatbot_node") # planner_node => macro_node
    builder.add_edge("help_node", END)
    builder.add_edge("draw_node", END)
    builder.add_edge("chatbot_node", END)
    
    graph = builder.compile()
    return graph

def gpt_router_node(state: dict) -> dict:
    """Uses GPT to determine the next node dynamically."""
    user_text = state["messages"][-1].content.strip()

    router_prompt_template = g.CONFIG["router_prompt"]
    planner_node_list_str = _list_nodes_by_scope("planner")
    router_node_list_str = _list_nodes_by_scope("router")
    router_prompt = router_prompt_template.format(router_node_list=router_node_list_str, planner_node_list=planner_node_list_str, user_input=user_text)

    g.LOGGER.info(f"Router Prompt created!")

    # Call GPT to determine the next node
    gpt = ChatOpenAI(model="gpt-4o", temperature=0.2)
    response = gpt.invoke(router_prompt)

    allowed_nodes = ["help_node", "draw_node", "chatbot_node", "planner_node"]
    next_node = response.content.strip().lower()
    if next_node not in allowed_nodes:
        g.LOGGER.warning(f"Invalid GPT response: {next_node}, defaulting to chatbot_node")
        next_node = "chatbot_node"

    g.LOGGER.info(f"Routing to: {next_node}")
    return {"__next_node__": next_node}

async def help_node(state: RouterState) -> dict:
    """
    Provide a more comprehensive help text, referencing both router-level
    and planner-level commands. Returns a Matrix-formatted message for HTML display.

    NOTE: We add to state['messages'] at the top level, ensuring final_state["messages"] is set.
    """
    import luna.GLOBALS as g
    from langchain.schema import AIMessage
    from langgraph.graph import END
    
    g.LOGGER.info("help_node: Invoked. Preparing help text...")

    # Separate nodes by scope
    router_nodes = []
    planner_nodes = []
    
    for node_name, info in g.NODE_REGISTRY.items():
        scopes = info.get("scopes", [])
        desc = info.get("desc", "")
        
        if "router" in scopes:
            router_nodes.append((node_name, desc))
        elif "planner" in scopes:
            planner_nodes.append((node_name, desc))

    def format_nodes_as_list(nodes):
        lines = []
        for n, d in nodes:
            lines.append(f"<li><strong>{n}</strong>: {d}</li>")
        return "\n".join(lines)

    router_list_html = format_nodes_as_list(router_nodes)
    planner_list_html = format_nodes_as_list(planner_nodes)

    # Build a nicely formatted HTML string
    help_html = f"""
<p>Hello, I’m <strong>Luna</strong>! Here’s how you can interact with me:</p>
<ul>
  <li>Type <code>help</code> at any time to see this menu.</li>
  <li>Type <code>draw something</code> to generate a mock image URL.</li>
  <li>Any other message => a GPT-based reply by default.</li>
</ul>

<p>Below are two categories of my known commands:</p>

<h3>Router-Level Commands</h3>
<ul>
  {router_list_html}
</ul>

<h3>Planner-Level Commands</h3>
<ul>
  {planner_list_html}
</ul>

<p><em>Note:</em> Planner-level commands are generally used in multi-step (macro) flows.</p>
""".strip()

    # Fallback text for non-HTML clients
    fallback_text = (
        "Hello, I’m Luna! Here’s how to interact with me:\n\n"
        "1) 'help' => see this menu\n"
        "2) 'draw something' => generate a mock image URL\n"
        "3) anything else => GPT-based reply.\n\n"
        "Router-Level Commands:\n"
        + "\n".join(f"- {n} => {d}" for n, d in router_nodes)
        + "\n\nPlanner-Level Commands:\n"
        + "\n".join(f"- {n} => {d}" for n, d in planner_nodes)
    )

    matrix_content = {
        "msgtype": "m.text",
        "body": fallback_text,
        "format": "org.matrix.custom.html",
        "formatted_body": help_html
    }

    help_ai_msg = AIMessage(
        content=fallback_text,
        additional_kwargs={"matrix_content": matrix_content}
    )

    # Append to the top-level messages
    updated_messages = state["messages"] + [help_ai_msg]

    g.LOGGER.info(f"help_node: updated_messages => {updated_messages!r}")

    # Return them as top-level "messages"
    return {
        "messages": updated_messages,
        "__next_node__": END
    }

async def draw_node(state: RouterState) -> dict:
    """
    A node that:
      1) Reads a 'prompt' from state (if present), otherwise parses the last user message.
      2) Calls OpenAI's DALL·E endpoint to generate an image.
      3) Downloads the image locally.
      4) Uploads it to Matrix (using direct_upload_image).
      5) Produces an AIMessage referencing the final image.

    Expected in state:
      - "messages": list of message objects
      - "prompt": optional string from the planner. If missing, we parse the last user msg.
      - "room_id": the Matrix room for displaying the image (optional)
      - Possibly other fields (like "size") if you want advanced DALL·E options.

    Returns:
      {
        "messages": updated_messages,
        "__next_node__": END
      }
    where updated_messages has a new AIMessage referencing the final image.
    """
    import luna.GLOBALS as g
    from langchain.schema import AIMessage
    from langgraph.graph import END
    import os, time, requests
    import asyncio

    g.LOGGER.info("draw_node: Invoked.")

    # 1) Retrieve user prompt
    user_prompt = state.get("prompt", "").strip()
    if not user_prompt:
        # fallback: parse from the last user message if any
        msgs = state.get("messages", [])
        if msgs and hasattr(msgs[-1], "content"):
            raw_text = msgs[-1].content.strip()
            if raw_text.lower().startswith("draw"):
                user_prompt = raw_text[4:].strip()
            else:
                user_prompt = raw_text
        else:
            user_prompt = "No drawing prompt provided"

    if not user_prompt:
        user_prompt = "No drawing prompt provided"

    g.LOGGER.info(f"draw_node: final user_prompt => {user_prompt!r}")

    dall_e_url = "https://api.openai.com/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {g.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    # If you want to allow 'size' from state or default
    size = state.get("size", "1024x1024")

    data = {
        "model": "dall-e-3",
        "prompt": user_prompt,
        "n": 1,
        "size": size
    }

    g.LOGGER.info(f"draw_node: calling DALL·E with prompt='{user_prompt}', size={size}")

    # 3) Call the DALL·E endpoint
    try:
        resp = requests.post(dall_e_url, headers=headers, json=data, timeout=90)
        resp.raise_for_status()
        response_data = resp.json()
        image_url = response_data["data"][0]["url"]
    except Exception as e:
        g.LOGGER.exception("draw_node: Error generating image => %s", e)
        error_msg = f"Failed to generate image from DALL·E for prompt: '{user_prompt}'"
        fallback_msg = AIMessage(content=error_msg)
        updated_messages = state["messages"] + [fallback_msg]
        return {"messages": updated_messages, "__next_node__": END}

    g.LOGGER.info(f"draw_node: received image_url => {image_url}")

    # 4) Download the image locally
    try:
        os.makedirs("data/images", exist_ok=True)
        timestamp = int(time.time())
        filename = f"data/images/dalle_{timestamp}.jpg"

        dl_resp = requests.get(image_url, timeout=30)
        dl_resp.raise_for_status()
        with open(filename, "wb") as f:
            f.write(dl_resp.content)

        g.LOGGER.info(f"draw_node: image saved to {filename}")
    except Exception as e:
        g.LOGGER.exception("draw_node: Error saving image => %s", e)
        error_msg = f"Failed to download/save image for prompt: '{user_prompt}'"
        fallback_msg = AIMessage(content=error_msg)
        updated_messages = state["messages"] + [fallback_msg]
        return {"messages": updated_messages, "__next_node__": END}

    # 5) Upload to Matrix via direct_upload_image
    room_id = state.get("room_id", "")
    mxc_uri = ""

    # If you have a single global client or something else, fetch it here:
    client = g.LUNA_CLIENT  # Or g.BOTS["lunabot"], etc.

    if not client or not room_id:
        g.LOGGER.warning("draw_node: missing client or room_id => skipping Matrix upload. (still returning image URL.)")
    else:
        try:
            mxc_uri = await _direct_upload_image(client, filename, "image/jpeg")
            g.LOGGER.info(f"draw_node: direct_upload_image => {mxc_uri}")
        except Exception as e:
            g.LOGGER.exception(f"draw_node: Error uploading image to Matrix => {e}")

    # 6) Produce the final AIMessage (with optional content referencing the MXC URI if present)
    if mxc_uri:
        final_text = f"Here is your image for prompt '{user_prompt}', uploaded to room => {mxc_uri}"

        file_size = os.path.getsize(filename)
        matrix_msg_content = {
            "msgtype": "m.image",
            "body": os.path.basename(filename),
            "url": mxc_uri,
            "info": {
                "mimetype": "image/jpeg",
                "size": file_size
            }
        }

        # 1) Actually post the image event directly to the room
        try:
            await client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=matrix_msg_content
            )
        except Exception as e:
            g.LOGGER.exception(f"draw_node: Error sending the 'm.image' event => {e}")

        # 2) Also store a textual AIMessage for the aggregator or final summary
        draw_ai_msg = AIMessage(
            content=final_text,
            additional_kwargs={"content": matrix_msg_content}
        )

    else:
        # fallback if no 'mxc_uri'
        final_text = f"Here is your image => {image_url}"
        draw_ai_msg = AIMessage(content=final_text)

    updated_messages = state["messages"] + [draw_ai_msg]

    return {
        "messages": updated_messages,
        "__next_node__": END
    }



async def create_room3_node(state: Dict) -> Dict:
    """
    Node that creates a new Matrix room using JSON-style inputs provided via Luna.
    
    Expects in state:
      - room_id: str, the room where the command was invoked (e.g. "!abc123:localhost")
      - sender: str, the user's Matrix ID (e.g. "@someone:localhost")
      - parent_event_id: str, the event ID to use for threading replies
      - name: str, required; the localpart for the new room alias and room name
      - prompt: str, optional; the room topic (and/or image generation prompt)
      - set_avatar: bool, optional; whether to generate and set a room avatar (default False)
      - invite: list of str, optional; additional user IDs to invite
      - additional_flag: dict, optional; extra data (e.g. style constraints for image generation)
    
    If any of these are missing the node will attempt to fallback or post error messages.
    """
    g.LOGGER.info("Entering create_room3_node...")

    # Extract basic parameters from state
    room_id          = state.get("room_id")
    sender           = state.get("sender")
    parent_event_id  = state.get("parent_event_id", "")
    name_localpart   = state.get("name")
    user_prompt      = state.get("prompt", "")
    set_avatar_flag  = bool(state.get("set_avatar", False))
    invite_list      = state.get("invite", [])
    additional_data  = state.get("additional_flag", {})

    g.LOGGER.info(
        "create_room3_node: room_id=%r, sender=%r, name=%r, prompt=%r, set_avatar=%r, invites=%r, parent_event_id=%r",
        room_id, sender, name_localpart, user_prompt, set_avatar_flag, invite_list, parent_event_id
    )

    # Validate required parameter "name"
    if not name_localpart:
        err = "Missing required 'name' parameter."
        g.LOGGER.warning(err)
        return {"error": err, "__next_node__": "chatbot_node"}

    # Fallback to global bot client if one is not provided in state
    bot_client = state.get("bot_client") or g.LUNA_CLIENT
    if not bot_client:
        err = "No bot client available."
        g.LOGGER.error(err)
        return {"error": err, "__next_node__": "chatbot_node"}

    # Start a keep-typing background task
    typing_task = asyncio.create_task(_keep_typing(bot_client, room_id))

    # Post an initial status update in-thread
    await _post_in_thread(
        bot_client,
        room_id,
        parent_event_id,
        "<p><strong>Processing your room creation request...</strong></p>",
        is_html=True
    )

    # --- 1) Create the room (public) ---
    g.LOGGER.info(f"Creating a public room with alias '#{name_localpart}:localhost'...")
    new_room_id = None
    try:
        resp = await bot_client.room_create(
            alias=name_localpart,
            name=name_localpart,
            topic=user_prompt,
            visibility=RoomVisibility.public
        )
        if isinstance(resp, RoomCreateError):
            err_msg = f"Room creation error: {resp.message or 'Unknown reason'} (status={resp.status_code})"
            g.LOGGER.error(err_msg)
            await _post_in_thread(
                bot_client,
                room_id,
                parent_event_id,
                f"<p><strong>Oops!</strong> {err_msg}</p>",
                is_html=True
            )
            typing_task.cancel()
            return {"error": err_msg, "__next_node__": "chatbot_node"}

        elif isinstance(resp, RoomCreateResponse):
            new_room_id = resp.room_id
            await _post_in_thread(
                bot_client,
                room_id,
                parent_event_id,
                f"Room created successfully! (ID: {new_room_id})",
                is_html=False
            )
        else:
            err_msg = f"Unexpected response type from room_create: {type(resp)}"
            g.LOGGER.error(err_msg)
            await _post_in_thread(
                bot_client,
                room_id,
                parent_event_id,
                f"<p><strong>Oops!</strong> {err_msg}</p>",
                is_html=True
            )
            typing_task.cancel()
            return {"error": err_msg, "__next_node__": "chatbot_node"}
    except Exception as e:
        err = f"Exception during room creation: {e}"
        g.LOGGER.exception(err)
        await _post_in_thread(
            bot_client,
            room_id,
            parent_event_id,
            f"<p><strong>Oops!</strong> {err}</p>",
            is_html=True
        )
        typing_task.cancel()
        return {"error": err, "__next_node__": "chatbot_node"}

    # --- 2) (Optional) Reset the topic explicitly if prompt was provided ---
    if user_prompt and new_room_id:
        try:
            await bot_client.room_put_state(
                new_room_id,
                event_type="m.room.topic",
                state_key="",
                content={"topic": user_prompt}
            )
            await _post_in_thread(
                bot_client,
                room_id,
                parent_event_id,
                "Topic set successfully.",
                is_html=False
            )
        except Exception as e:
            g.LOGGER.warning(f"Could not set topic: {e}")
            await _post_in_thread(
                bot_client,
                room_id,
                parent_event_id,
                f"Warning: Could not set topic: {e}",
                is_html=False
            )

    # --- 3) Generate and set room avatar if requested ---
    if set_avatar_flag and new_room_id:
        try:
            final_prompt = user_prompt if user_prompt else "A general chat room."
            if additional_data:
                style_snippet = " ".join(f"{k}={v}" for k, v in additional_data.items())
                final_prompt = f"{final_prompt} {style_snippet}"
            if len(final_prompt) > 4000:
                final_prompt = final_prompt[:4000]

            await _post_in_thread(
                bot_client,
                room_id,
                parent_event_id,
                "Generating room avatar, please wait...",
                is_html=False
            )
            image_url = await generate_image(final_prompt, size="1024x1024")
            g.LOGGER.info(f"Received image_url: {image_url}")

            filename = f"data/images/room_avatar_{int(time.time())}.jpg"
            os.makedirs("data/images", exist_ok=True)
            dl_resp = requests.get(image_url)
            dl_resp.raise_for_status()
            with open(filename, "wb") as f:
                f.write(dl_resp.content)

            mxc_url = await direct_upload_image(bot_client, filename, "image/jpeg")
            await bot_client.room_put_state(
                new_room_id,
                event_type="m.room.avatar",
                state_key="",
                content={"url": mxc_url}
            )
            await _post_in_thread(
                bot_client,
                room_id,
                parent_event_id,
                "Avatar generated and set successfully!",
                is_html=False
            )
        except Exception as e:
            g.LOGGER.exception(f"Avatar generation failed: {e}")
            await _post_in_thread(
                bot_client,
                room_id,
                parent_event_id,
                f"Avatar generation failed: {e}. Continuing...",
                is_html=False
            )

    # --- 4) Invite users (sender plus any additional invites) ---
    if new_room_id:
        try:
            # Invite the command sender
            inv_resp = await bot_client.room_invite(new_room_id, sender)
            if not (inv_resp and inv_resp.transport_response and inv_resp.transport_response.ok):
                g.LOGGER.warning(f"Could not invite the command sender {sender}: {inv_resp}")
            await _set_power_level(bot_client, new_room_id, sender, 100)

            # Invite additional users
            for user_id in invite_list:
                try:
                    iresp = await bot_client.room_invite(new_room_id, user_id)
                    if not (iresp and iresp.transport_response and iresp.transport_response.ok):
                        g.LOGGER.warning(f"Could not invite {user_id}: {iresp}")
                except Exception as e:
                    g.LOGGER.warning(f"Invite failed for {user_id}: {e}")
            await _post_in_thread(
                bot_client,
                room_id,
                parent_event_id,
                f"Invited {len(invite_list)+1} user(s). Promoted {sender} to PL100.",
                is_html=False
            )
        except Exception as e:
            g.LOGGER.exception(f"Error during invite/promote: {e}")
            await _post_in_thread(
                bot_client,
                room_id,
                parent_event_id,
                f"Error inviting or promoting: {e}",
                is_html=False
            )
    else:
        g.LOGGER.warning("No new_room_id available; skipping invite logic.")

    # --- 5) Post final summary ---
    summary_html = (
        "<p><strong>Room creation completed!</strong></p>"
        "<ul>"
        f"<li>Room alias: #{name_localpart}:localhost</li>"
        f"<li>Topic: {user_prompt}</li>"
        f"<li>Avatar: {'generated' if set_avatar_flag else 'not set'}</li>"
        f"<li>Invites: {len(invite_list)} user(s) invited</li>"
        "</ul>"
    )
    await _post_in_thread(
        bot_client,
        room_id,
        parent_event_id,
        summary_html,
        is_html=True
    )

    typing_task.cancel()
    g.LOGGER.info("Completed create_room3_node.")
    return {"__next_node__": "chatbot_node"}


async def chatbot_node(state: RouterState) -> dict:
    """
    Single-turn GPT logic: read the user's message, call g.LLM, store the reply.
    Ends immediately after returning the LLM response.

    NOTE: We append the reply to top-level state["messages"], so final_state["messages"] holds them.
    """
    import luna.GLOBALS as g
    from langchain.schema import AIMessage
    from langgraph.graph import END

    g.LOGGER.info(f"chatbot_node: total messages => {len(state['messages'])}")

    if g.LLM is None:
        g.LOGGER.error("Global LLM is None! Returning fallback message.")
        fallback_msgs = state["messages"] + [AIMessage(content="LLM not initialized.")]
        return {
            "messages": fallback_msgs,
            "__next_node__": END
        }

    # The last item in 'messages' is presumably the user's HumanMessage.
    response_msg = g.LLM.invoke(state["messages"])

    if not isinstance(response_msg, AIMessage):
        response_msg = AIMessage(content=str(response_msg))

    g.LOGGER.info(f"chatbot_node: response_msg => {response_msg!r}")

    updated_messages = state["messages"] + [response_msg]
    g.LOGGER.info(f"chatbot_node: updated_messages => {updated_messages!r}")
    g.LOGGER.info(f"chatbot_node: Exiting with updated messages, next => END")

    return {
        "messages": updated_messages,
        "__next_node__": END
    }

async def macro_node(state: RouterState) -> dict:
    """
    A generic node that executes a sequence of steps (node calls) one by one.

    Expected in `state`:
      - macro_sequence: list of dicts, each with "node" (str) and "args" (dict)
      - macro_step_index: current step index (int), defaults to 0 if not found

    If macro_step_index >= len(macro_sequence), we end.
    Otherwise, we call the indicated node with the provided args.
    """
    import luna.GLOBALS as g
    from langgraph.graph import END

    g.LOGGER.info("macro_node: Entered with state keys: %s", list(state.keys()))

    plan = state.get("macro_sequence", [])
    idx = state.get("macro_step_index")

    if not idx:
        g.LOGGER.info("macro_node: No macro_step_index found. Defaulting to 0.")
        idx = 0

    g.LOGGER.info("macro_node: Current step index => %d, plan length => %d", idx, len(plan))

    # If we've run all steps, transition to END (or any finishing node)
    if idx >= len(plan):
        g.LOGGER.info("macro_node: All steps exhausted (idx=%d). Transitioning to END.", idx)
        return {"__next_node__": END}

    # Extract the current step data
    step = plan[idx]
    node_name = step.get("node")
    args = step.get("args", {})

    g.LOGGER.info("macro_node: Processing step idx=%d => node=%r, args=%r", idx, node_name, args)

    if not node_name:
        error_msg = f"No node name found in macro_sequence step {idx}."
        g.LOGGER.warning("macro_node: %s", error_msg)
        state["macro_error"] = error_msg
        return {"__next_node__": END}

    # Look up the node function in the global registry
    node_info = g.NODE_REGISTRY.get(node_name)
    if not node_info:
        error_msg = f"Node '{node_name}' not found in NODE_REGISTRY."
        g.LOGGER.warning("macro_node: %s", error_msg)
        state["macro_error"] = error_msg
        return {"__next_node__": END}

    node_func = node_info.get("func")
    if not node_func:
        error_msg = f"No function found for node '{node_name}'."
        g.LOGGER.warning("macro_node: %s", error_msg)
        state["macro_error"] = error_msg
        return {"__next_node__": END}

    # Merge the step's "args" into state so the node can read them
    for k, v in args.items():
        g.LOGGER.debug("macro_node: Setting state[%r] = %r", k, v)
        state[k] = v

    # Call the target node function
    g.LOGGER.info("macro_node: Invoking node function => %r", node_func.__name__)
    updated_state = await node_func(state)

    # If the node function returned anything, merge that back into our state
    if updated_state:
        g.LOGGER.debug("macro_node: Merging updated_state into main state => %r", updated_state.keys())
        state.update(updated_state)

    # Move the pointer forward
    new_index = idx + 1
    state["macro_step_index"] = new_index
    g.LOGGER.info("macro_node: Incremented macro_step_index to %d", new_index)

    # Return to this same macro node until we exhaust the plan
    g.LOGGER.info("macro_node: Returning to 'macro_node' for the next step.")
    state["__next_node__"] = "macro_node"
    return state

def planner_node(state: RouterState) -> dict:
    """
    A node that uses GPT to produce a 'macro_sequence' of steps for multi-step tasks.
    
    Expected in `state`:
      - 'messages': a list of message objects. The last one is presumably the user's request.
    
    This node will:
      1) Extract the user's last message.
      2) Call GPT with a special prompt that requests a JSON plan (no code fences).
      3) Parse that JSON into a Python list, storing it in state["macro_sequence"].
      4) Set state["macro_step_index"] = 0.
      5) Return __next_node__ = "macro_node" so the macro node executes those steps.
    """
    g.LOGGER.info("Entered planner_node with state keys: %s", list(state.keys()))

    # 1) Grab the user's last message content
    user_text = ""
    if "messages" in state and state["messages"]:
        user_text = state["messages"][-1].content.strip()
    g.LOGGER.info("planner_node: extracted user_text => %r", user_text)

    # 2) Build the GPT prompt for planning
    planner_template = g.CONFIG.get("planner_prompt", "")
    g.LOGGER.info("planner_node: retrieved planner_template from config (length=%d).", len(planner_template))

    from luna.luna_lang_router import _list_nodes_by_scope
    node_list_str = _list_nodes_by_scope("planner")
    g.LOGGER.info("planner_node: node_list for scope='planner':\n%s", node_list_str)

    planner_prompt = planner_template.format(node_list=node_list_str, user_input=user_text)
    g.LOGGER.info(f"planner_node: constructed planner_prompt with nodes: {node_list_str}")

    # 3) Call GPT
    # Use g.LLM if available; otherwise create a new ChatOpenAI instance
    llm = g.LLM or ChatOpenAI(
        openai_api_key=g.OPENAI_API_KEY,
        model_name="gpt-4o",
        temperature=0.0
    )
    g.LOGGER.info("planner_node: calling GPT with the constructed planner prompt...")

    response = llm.invoke([HumanMessage(content=planner_prompt)])
    g.LOGGER.info("planner_node: raw GPT response content => %r", response.content)

    # 4) Parse the JSON from GPT
    try:
        plan_list = json.loads(response.content)
        if not isinstance(plan_list, list):
            raise ValueError("Planner output not a list.")
        g.LOGGER.info("planner_node: successfully parsed plan_list => %s", plan_list)
    except Exception as e:
        g.LOGGER.warning("planner_node: JSON parsing error => %s", e)
        # On failure, store an error or fallback
        state["planner_error"] = f"Planner produced invalid JSON: {e}"
        # fallback to a single-step plan calling chatbot_node
        state["macro_sequence"] = [
            { "node": "error_node", "args": {"error_details": str(e)}}
        ]
        state["macro_step_index"] = 0
        g.LOGGER.info("planner_node: falling back to chatbot_node with single-step plan.")
        return {"__next_node__": "macro_node"}

    # 5) Store the plan in state, reset the step index
    state["macro_sequence"] = plan_list
    state["macro_step_index"] = 0

    g.LOGGER.info("planner_node: stored macro_sequence in state. Next node => macro_node.")
    g.LOGGER.info(f"   with plan list: {plan_list}")

    state["__next_node__"] = "macro_node"
    return state

def summarize_state_with_gpt(state: dict) -> str:
    """
    Uses GPT (g.LLM) to produce a short text explanation of the current 'state' dictionary.
    We create a JSON-serializable copy by recursively converting any HumanMessage/AIMessage objects.
    """

    import json
    import luna.GLOBALS as g
    from langchain.schema import HumanMessage, AIMessage, SystemMessage, ChatMessage

    # A helper to recursively convert non-serializable items to plain dicts/strings
    def make_jsonable(value):
        # 1) If it's a dict, process each key recursively
        if isinstance(value, dict):
            return {k: make_jsonable(v) for k, v in value.items()}

        # 2) If it's a list, process each item
        if isinstance(value, list):
            return [make_jsonable(item) for item in value]

        # 3) If it's one of the LangChain message objects, convert to a dict
        if isinstance(value, HumanMessage):
            return {
                "type": "HumanMessage",
                "content": value.content
            }
        if isinstance(value, AIMessage):
            return {
                "type": "AIMessage",
                "content": value.content
            }
        if isinstance(value, SystemMessage):
            return {
                "type": "SystemMessage",
                "content": value.content
            }
        if isinstance(value, ChatMessage):
            return {
                "type": "ChatMessage",
                "role": value.role,
                "content": value.content
            }

        # 4) Otherwise, assume it's JSON-serializable already (e.g. str/int/bool/None)
        # or just cast it to string if you want to be extra safe.
        return value

    # Build a JSON-safe copy of state
    safe_state = make_jsonable(state)

    # Attempt to dump to JSON
    try:
        state_json = json.dumps(safe_state, indent=2)
    except TypeError as e:
        # If something else is un-serializable, just fallback
        return f"Could not serialize final state to JSON: {e}"

    # Retrieve the prompt from config (the same 'state_summary_prompt' we used before)
    prompt_template = g.CONFIG.get("state_summary_prompt", "")
    if not prompt_template:
        return "No 'state_summary_prompt' found in config.yaml"

    # Format the prompt by injecting the JSON
    prompt = prompt_template.format(state_json=state_json)

    # Check if LLM is ready
    if not g.LLM:
        return "LLM not initialized; cannot summarize state."

    # Call GPT
    from langchain.schema import HumanMessage
    response = g.LLM.invoke([HumanMessage(content=prompt)])

    return response.content.strip()

def _get_nodes_by_scope(desired_scope: str) -> Dict[str, dict]:
    """
    Returns a sub-dict of NODE_REGISTRY entries whose 'scopes' includes the desired_scope.
    """
    results = {}
    for node_name, info in g.NODE_REGISTRY.items():
        scopes = info.get("scopes", [])
        if desired_scope in scopes:
            results[node_name] = info
    return results

def _list_nodes_by_scope(desired_scope: str) -> str:
    subregistry = _get_nodes_by_scope(desired_scope)
    lines = []
    for node_name, info in subregistry.items():
        desc = info.get("desc", "")
        lines.append(f"- {node_name}: {desc}")
    return "\n".join(lines)

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

    # Log 
    g.LOGGER.debug(
        "handle_luna_message: Building initial state:\n%s",
        {
            "messages": ["<list of messages>"],  # or partial
            "macro_sequence": [],
            "macro_step_index": 0,
            "room_id": room.room_id,
            "raw_args": "",
            "sender": event.sender,
            "parent_event_id": event.event_id,
        }
    )


    # Build the initial RouterState with new fields:
    state: RouterState = {
        "messages": [HumanMessage(content=user_text)],
        "macro_sequence": [],
        "macro_step_index": 0,
        "room_id": room.room_id,
        # new fields
        "raw_args": "",   # If you detect the user typed something CLI-like
        "sender": event.sender,
        "parent_event_id": event.event_id,
    }

    final_state = None

    # Stream graph execution and log each step
    async for partial_state in g.ROUTER_GRAPH.astream(state):
        g.LOGGER.info(f"next_state => {partial_state!r}")
        final_state = partial_state

    # After we've streamed the graph to final_state...
    g.LOGGER.info(f"final_state => {final_state!r}")

    if "macro_node" in final_state:
        g.LOGGER.info("Ending on macro_node, generating final summary with GPT.")

        # 1) Summarize the final state (including messages, plan steps, etc.)
        summary_text = summarize_state_with_gpt(final_state)

        # 2) If we got nothing back, skip sending
        if not summary_text:
            g.LOGGER.warning("🚨 Summarizer returned empty text. Skipping send.")
            return

        g.LOGGER.info(f"Sending macro summary: {summary_text!r}")

        try:
            # If your 'summary_text' already contains Markdown syntax, you can convert it to HTML
            # using a Python library like 'markdown' (pip install markdown).
            import markdown
            summary_html = _convert_markdown_to_html(summary_text)

            content = {
                "msgtype": "m.text",
                "body": summary_text,  # plain-text fallback
                "format": "org.matrix.custom.html",
                "formatted_body": summary_html
            }

            await client.room_send(
                room_id=room.room_id,
                message_type="m.room.message",
                content=content
            )

        except Exception as e:
            g.LOGGER.exception(f"Error sending message => {e}")
        finally:
            await _stop_typing(client, room.room_id)

        # Ensure the processed events set doesn't grow infinitely
        if len(g.PROCESSED_EVENTS) > 10000:
            g.PROCESSED_EVENTS.clear()

    else:
    # 1) Attempt to read top-level "messages" first
        msgs = final_state.get("messages", None)

        if not msgs:
            # 2) If not found, see if any final node subdict has messages
            for node_name, node_data in final_state.items():
                if node_name not in ("macro_node", "messages"):  # skip macro or direct
                    if isinstance(node_data, dict) and "messages" in node_data:
                        msgs = node_data["messages"]
                        g.LOGGER.info(f"Found messages under final node '{node_name}'.")
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

def _convert_markdown_to_html(md_text: str) -> str:
    # 1) Convert to HTML with the official extensions you want
    raw_html = markdown.markdown(
        md_text,
        extensions=[
            "markdown.extensions.admonition",
            "markdown.extensions.attr_list",
            "markdown.extensions.def_list",
            "markdown.extensions.fenced_code",
            "markdown.extensions.footnotes",
            "markdown.extensions.meta",
            "markdown.extensions.sane_lists",
            "markdown.extensions.smarty",
            "markdown.extensions.tables",
            "markdown.extensions.toc",
            "markdown.extensions.wikilinks",
        ]
    )
    # 2) Make sure Bleach allows typical block/inline tags
    #    so it doesn't remove <p>, <table>, etc.
    allowed_tags = list(bleach.sanitizer.ALLOWED_TAGS) + [
        "p", "h1", "h2", "h3", "h4", "h5", "h6",
        "table", "thead", "tbody", "tr", "th", "td",
        "hr", "span", "div", "pre", "code", "br"
    ]
    safe_html = bleach.clean(
        raw_html,
        tags=allowed_tags,
        strip=False
    )
    return safe_html


def _convert_markdown_to_html_dep(md_text: str) -> str:
    # Convert the Markdown (including fenced code blocks) to HTML

    raw_html = markdown.markdown(
        md_text,
        extensions=[
            # Official built-ins
            "markdown.extensions.admonition",
            "markdown.extensions.attr_list",
            "markdown.extensions.def_list",
            "markdown.extensions.fenced_code",
            "markdown.extensions.footnotes",
            "markdown.extensions.meta",
            "markdown.extensions.nl2br",
            "markdown.extensions.sane_lists",
            "markdown.extensions.smarty",
            "markdown.extensions.tables",
            "markdown.extensions.toc",
            "markdown.extensions.wikilinks",
            # You can also add "markdown.extensions.extra"
            # but note 'extra' is largely a shortcut for a subset of the above.
        ]
    )

    # Because ALLOWED_TAGS is a frozenset, we convert it to a list first
    base_tags = list(bleach.sanitizer.ALLOWED_TAGS)
    base_tags.extend(["pre", "code"])  # Add tags we want to allow

    # If you also want to tweak allowed attributes:
    base_attrs = dict(bleach.sanitizer.ALLOWED_ATTRIBUTES)

    # Now pass your lists/dicts to bleach.clean
    safe_html = bleach.clean(
        raw_html,
        tags=base_tags,          # previously: bleach.sanitizer.ALLOWED_TAGS + [...]
        attributes=base_attrs,
        strip=False
    )
    return safe_html

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

async def _direct_upload_image(
    client: AsyncClient,
    file_path: str,
    content_type: str = "image/jpeg"
) -> str:
    """
    Manually upload a file to Synapse's media repository, explicitly setting
    Content-Length (avoiding chunked requests).
    
    Returns the mxc:// URI if successful, or raises an exception on failure.
    """
    if not client.access_token or not client.homeserver:
        raise RuntimeError("AsyncClient has no access_token or homeserver set.")

    base_url = client.homeserver.rstrip("/")
    filename = os.path.basename(file_path)
    encoded_name = urllib.parse.quote(filename)
    upload_url = f"{base_url}/_matrix/media/v3/upload?filename={encoded_name}"

    file_size = os.path.getsize(file_path)
    headers = {
        "Authorization": f"Bearer {client.access_token}",
        "Content-Type": content_type,
        "Content-Length": str(file_size),
    }

    g.LOGGER.debug("[direct_upload_image] POST to %s, size=%d", upload_url, file_size)

    async with aiohttp.ClientSession() as session:
        with open(file_path, "rb") as f:
            async with session.post(upload_url, headers=headers, data=f) as resp:
                if resp.status == 200:
                    body = await resp.json()
                    content_uri = body.get("content_uri")
                    if not content_uri:
                        raise RuntimeError("No 'content_uri' in response JSON.")
                    g.LOGGER.debug("[direct_upload_image] Uploaded. content_uri=%s", content_uri)
                    return content_uri
                else:
                    err_text = await resp.text()
                    raise RuntimeError(
                        f"Upload failed (HTTP {resp.status}): {err_text}"
                    )


async def _post_in_thread(
    bot_client: AsyncClient,
    room_id: str,
    parent_event_id: str,
    message_text: str,
    is_html: bool = False
) -> None:
    """
    Helper to post partial or final messages in the same “thread” 
    referencing the user’s original event. Using the 'm.in_reply_to' 
    or 'rel_type=m.thread' approach depending on your Element client version.

    For a modern approach: 
      "m.relates_to": {
        "rel_type": "m.thread",
        "event_id": parent_event_id
      }
    """
    # 1) Build content
    content = {}
    if not is_html:
        # Plain text
        content["msgtype"] = "m.text"
        content["body"] = message_text
    else:
        # HTML
        content["msgtype"] = "m.text"
        content["body"] = _strip_html_tags(message_text)
        content["format"] = "org.matrix.custom.html"
        content["formatted_body"] = message_text

    # 2) Add thread relation
    content["m.relates_to"] = {
        "rel_type": "m.thread",
        "event_id": parent_event_id
    }

    # 3) Send
    try:
        resp = await bot_client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content=content
        )
        if isinstance(resp, RoomSendResponse):
            g.LOGGER.info(f"Posted a message in-thread => event_id={resp.event_id}")
        else:
            g.LOGGER.warning(f"Could not post in-thread => {resp}")
    except Exception as e:
        g.LOGGER.exception(f"[command_helpers] Error posting in-thread => {e}")


def _strip_html_tags(text: str) -> str:
    """
    Removes all HTML tags from the given text string.
    """
    return re.sub(r"<[^>]*>", "", text or "").strip()


async def _keep_typing(bot_client: AsyncClient, room_id: str, refresh_interval=3):
    """
    Periodically refresh the typing indicator in 'room_id' every
    'refresh_interval' seconds. Cancel this task to stop the typing
    indicator when done.
    """
    try:
        while True:
            # 'typing=True' with a 30s timeout
            await bot_client.room_typing(
                room_id=room_id,
                typing=True,
                timeout=30000
            )
            g.LOGGER.info(f"[command_helpers] Set keep typing for {room_id}")
            await asyncio.sleep(refresh_interval)
    except asyncio.CancelledError:
        # Optionally send a final "typing=False" to clear the indicator
        # before exiting.
        try:
            await bot_client.room_typing(
                room_id=room_id,
                typing=False,
                timeout=0
            )
        except Exception:
            pass

async def _set_power_level(bot_client: AsyncClient, room_id: str, user_id: str, power: int):
    """
    Helper to set a user's power level in a given room.
    Copied or adapted from your existing code.
    """
    try:
        state_resp = await bot_client.room_get_state_event(room_id, "m.room.power_levels", "")
        current_content = state_resp.event.source.get("content", {})
        users_dict = current_content.get("users", {})
        users_dict[user_id] = power
        current_content["users"] = users_dict

        await bot_client.room_send_state(
            room_id=room_id,
            event_type="m.room.power_levels",
            state_key="",
            content=current_content,
        )
    except Exception as e:
        g.LOGGER.warning(f"Could not set power level {power} for {user_id} in {room_id} => {e}")

async def direct_upload_image(
    client: AsyncClient,
    file_path: str,
    content_type: str = "image/jpeg"
) -> str:
    """
    Manually upload a file to Synapse's media repository, explicitly setting
    Content-Length (avoiding chunked requests).
    
    Returns the mxc:// URI if successful, or raises an exception on failure.
    """
    if not client.access_token or not client.homeserver:
        raise RuntimeError("AsyncClient has no access_token or homeserver set.")

    base_url = client.homeserver.rstrip("/")
    filename = os.path.basename(file_path)
    encoded_name = urllib.parse.quote(filename)
    upload_url = f"{base_url}/_matrix/media/v3/upload?filename={encoded_name}"

    file_size = os.path.getsize(file_path)
    headers = {
        "Authorization": f"Bearer {client.access_token}",
        "Content-Type": content_type,
        "Content-Length": str(file_size),
    }

    g.LOGGER.info("[direct_upload_image] POST to %s, size=%d", upload_url, file_size)

    async with aiohttp.ClientSession() as session:
        with open(file_path, "rb") as f:
            async with session.post(upload_url, headers=headers, data=f) as resp:
                if resp.status == 200:
                    body = await resp.json()
                    content_uri = body.get("content_uri")
                    if not content_uri:
                        raise RuntimeError("No 'content_uri' in response JSON.")
                    g.LOGGER.info("[direct_upload_image] Uploaded. content_uri=%s", content_uri)
                    return content_uri
                else:
                    err_text = await resp.text()
                    raise RuntimeError(
                        f"Upload failed (HTTP {resp.status}): {err_text}"
                    )

async def generate_image(prompt: str, size: str = "1024x1024") -> str:
    """
    Generates an image using OpenAI's API and returns the URL of the generated image.
    """
    # -----------------------------------------------------------------
    # 1) Merge the global style with the user's prompt
    # -----------------------------------------------------------------
    from luna.luna_command_extensions.command_router import GLOBAL_PARAMS
    style = GLOBAL_PARAMS.get("global_draw_prompt_appendix", "").strip()
    if style:
        final_prompt = f"{prompt.strip()}. {style}"
    else:
        final_prompt = prompt.strip()

    try:
        url = "https://api.openai.com/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {g.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": "dall-e-3",
            "prompt": final_prompt,
            "n": 1,
            "size": size,
        }

        g.LOGGER.debug("Sending request to OpenAI: %s", data)
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        image_url = response.json()["data"][0]["url"]
        g.LOGGER.info("Generated image URL: %s", image_url)
        return image_url
    except Exception as e:
        g.LOGGER.exception("Failed to generate image.")
        raise e

import logging
import json
import time
import os
import html
import requests

from luna.ai_functions import get_gpt_response, generate_image
from luna.luna_command_extensions.create_and_login_bot import create_and_login_bot
from luna.luna_personas import update_bot
from luna.luna_functions import getClient
from luna.luna_command_extensions.image_helpers import direct_upload_image
from luna.luna_command_extensions.command_helpers import _post_in_thread

import luna.GLOBALS as g

logger = logging.getLogger(__name__)

async def spawn_persona_node(state: dict) -> dict:
    """
    Node that creates a new persona (character) from a provided descriptor and posts
    both the portrait (if generated) and a complete character card in-thread.

    Expects in state:
      - descriptor: str, a text description for the persona.
      - room_id: (optional) str, the room where the command was invoked.
      - parent_event_id: (optional) str, the event ID for threading replies.
      - bot_client: (optional) the client to use for posting; defaults to g.LUNA_CLIENT.

    The node will:
      1) Call GPT to generate a persona JSON.
      2) Parse the JSON and validate required fields.
      3) Create and log in the new persona via create_and_login_bot.
      4) Optionally generate and upload a portrait.
      5) Build an HTML character card with persona details.
      6) Post the portrait (if available) and the character card in thread.
    
    Returns state updated with:
      - html: str, the final persona card HTML.
      - bot_id: str, the normalized bot ID.
      - __next_node__: str, e.g. "chatbot_node"
    """
    logger.info("Entering spawn_persona_node...")

    # 1) Extract required input
    descriptor = state.get("descriptor", "").strip()
    if not descriptor:
        err = "Missing required 'descriptor' parameter."
        logger.error(err)
        return {"error": err, "__next_node__": "chatbot_node"}

    # Get the posting client (fallback to global client)
    bot_client = state.get("bot_client") or g.LUNA_CLIENT

    # 2) Build GPT messages to generate persona JSON.
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
    logger.info("Requesting persona JSON from GPT with descriptor: %s", descriptor)
    try:
        gpt_response = await get_gpt_response(
            messages=messages,
            model="gpt-4",
            temperature=0.7,
            max_tokens=5000
        )
    except Exception as e:
        logger.exception("GPT error in spawn_persona_node")
        return {"error": f"GPT error: {e}", "__next_node__": "chatbot_node"}

    # 3) Parse persona JSON and check for required fields.
    try:
        persona_data = json.loads(gpt_response)
    except json.JSONDecodeError as e:
        logger.exception("JSON parse error in spawn_persona_node")
        return {"error": f"Invalid JSON from GPT: {e}", "__next_node__": "chatbot_node"}

    required_keys = ["localpart", "password", "displayname", "system_prompt", "traits"]
    missing = [key for key in required_keys if key not in persona_data]
    if missing:
        err = f"Persona missing required fields: {missing}"
        logger.error(err)
        return {"error": err, "__next_node__": "chatbot_node"}

    localpart     = persona_data["localpart"]
    password      = persona_data["password"]
    displayname   = persona_data["displayname"]
    system_prompt = persona_data["system_prompt"]
    traits        = persona_data.get("traits") or {}
    biography     = persona_data.get("biography", "")
    backstory     = persona_data.get("backstory", "")

    # 4) Register & login the persona.
    try:
        bot_result = await create_and_login_bot(
            bot_id=f"@{localpart}:localhost",
            password=password,
            displayname=displayname,
            system_prompt=system_prompt,
            traits=traits
        )
    except Exception as e:
        logger.exception("Error during create_and_login_bot in spawn_persona_node")
        return {"error": f"Persona creation failed: {e}", "__next_node__": "chatbot_node"}

    if not bot_result.get("ok", False):
        error_details = bot_result.get("error", "Unknown error")
        err = f"Persona creation failed: {error_details}"
        logger.error(err)
        return {"error": err, "__next_node__": "chatbot_node"}

    bot_id = bot_result.get("bot_id", "")
    ephemeral_bot_client = bot_result.get("client")
    # Normalize bot_id: remove '@' prefix and ':localhost' suffix.
    if bot_id.startswith('@'):
        bot_id = bot_id[1:]
    if bot_id.endswith(':localhost'):
        bot_id = bot_id[:-10]

    # 5) Attempt to generate & upload a portrait using the descriptor as prompt.
    final_prompt = descriptor  # EXACT prompt used
    portrait_mxc = None
    try:
        portrait_url = await generate_image(final_prompt, size="1024x1024")
        if portrait_url:
            portrait_mxc = await _download_and_upload_portrait(
                portrait_url,
                localpart,
                password,
                system_prompt,
                traits,
                ephemeral_bot_client
            )
    except Exception as e:
        logger.warning("Portrait generation/upload error: %s", e)

    # 6) Build the final persona card HTML.
    global_draw_appendix = g.GLOBAL_PARAMS.get("global_draw_prompt_appendix", "")
    card_html = _build_persona_card(
        localpart=localpart,
        displayname=displayname,
        biography=biography,
        backstory=backstory,
        system_prompt=system_prompt,
        dall_e_prompt=final_prompt,
        traits=traits,
        portrait_mxc=portrait_mxc,
        global_draw_appendix=global_draw_appendix
    )

    # 7) Post the portrait (if any) and the persona card in-thread.
    room_id = state.get("room_id")
    parent_event_id = state.get("parent_event_id", "")
    if room_id:
        if portrait_mxc:
            portrait_html = f"<p><strong>Portrait</strong></p><img src='{portrait_mxc}' alt='Portrait' width='300'/>"
            try:
                await _post_in_thread(bot_client, room_id, parent_event_id, portrait_html, is_html=True)
            except Exception as e:
                logger.warning("Error posting portrait in thread: %s", e)
        try:
            await _post_in_thread(bot_client, room_id, parent_event_id, card_html, is_html=True)
        except Exception as e:
            logger.warning("Error posting character card in thread: %s", e)

    logger.info("Completed spawn_persona_node for persona %s", localpart)
    # Update state with the resulting HTML and bot ID, and set the next node.
    state.update({
        "html": card_html,
        "bot_id": bot_id,
        "__next_node__": "chatbot_node"
    })
    return state

# ----------------------------
# Internal helper functions
# ----------------------------

async def _download_and_upload_portrait(
    portrait_url: str,
    localpart: str,
    password: str,
    system_prompt: str,
    traits: dict,
    ephemeral_bot_client
) -> str:
    """
    Downloads the image from portrait_url, uploads it to Matrix,
    updates the persona record, and sets the bot's avatar.
    Returns the mxc:// URI or None on failure.
    """
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
    # Update persona record with portrait URL.
    traits["portrait_url"] = portrait_mxc
    update_bot(
        f"@{localpart}:localhost",
        {
            "password": password,
            "system_prompt": system_prompt,
            "traits": traits
        }
    )
    # Attempt to set the avatar on the ephemeral client.
    if ephemeral_bot_client:
        try:
            await ephemeral_bot_client.set_avatar(portrait_mxc)
        except Exception as e:
            logger.warning("Error setting avatar: %s", e)
    return portrait_mxc

def _build_persona_card(
    localpart: str,
    displayname: str,
    biography: str,
    backstory: str,
    system_prompt: str,
    dall_e_prompt: str,
    traits: dict,
    portrait_mxc: str,
    global_draw_appendix: str
) -> str:
    """
    Builds and returns an HTML character card for the persona. The card includes:
      - A title (localpart) and italicized displayname.
      - An optional portrait.
      - A table of details including biography, backstory, system prompt, DALL·E prompt,
        draw prompt appendix, traits (as a nested table), and a version number.
    """
    def esc(text):
        return html.escape(str(text))

    # Build nested table for traits.
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

    def row(label, val):
        return (
            "<tr>"
            f"<td style='padding:4px 8px; vertical-align:top;'><b>{esc(label)}</b></td>"
            f"<td style='padding:4px 8px;'>{val}</td>"
            "</tr>"
        )

    # Build portrait HTML if available.
    portrait_html = ""
    if portrait_mxc:
        portrait_html = (
            f"<div style='margin-bottom:8px;'>"
            f"<img src='{esc(portrait_mxc)}' alt='Portrait' width='300'/>"
            "</div>"
        )

    # Build rows for the main table.
    table_rows = "".join([
        row("Localpart", esc(localpart)),
        row("DisplayName", esc(displayname)),
        row("Biography", esc(biography)),
        row("Backstory", esc(backstory)),
        row("System Prompt", esc(system_prompt)),
        row("DALL·E Prompt", esc(dall_e_prompt)),
        row("Draw Prompt Appendix", esc(global_draw_appendix)),
        row("Traits", traits_subtable),
        row("Version", "1.0")
    ])

    table_html = (
        "<table border='1' style='border-collapse:collapse;'>"
        f"<tbody>{table_rows}</tbody>"
        "</table>"
    )

    # Combine header, optional portrait, and table.
    final_html = (
        f"<h2 style='margin-bottom:2px;'>{esc(localpart)}</h2>"
        f"<p style='margin-top:0; margin-bottom:10px;'><em>{esc(displayname)}</em></p>"
        f"{portrait_html}"
        f"{table_html}"
        "<p><em>Persona creation complete!</em></p>"
    )
    return final_html

async def spawn_persona_node_dep2(state: dict) -> dict:
    """
    Node that creates a new persona from a descriptor provided via JSON.
    
    Expects in state:
      - descriptor: str, a textual description for the persona.
      - room_id: str, the room where the command was invoked.
      - parent_event_id: str, the event ID for threading.
      - sender: str, the user's Matrix ID.
    
    The node will:
      1) Call GPT to generate a persona JSON.
      2) Parse the JSON and validate required fields.
      3) Create and log in the new persona (bot) via create_and_login_bot.
      4) Optionally generate and upload a portrait.
      5) Build an HTML character card containing persona details.
    
    Returns state with additional keys:
      - html: str, the final persona card HTML.
      - bot_id: str, the normalized bot ID.
      - __next_node__: str, e.g. "chatbot_node"
    """
    g.LOGGER.info("Entering spawn_persona_node...")
    
    # Retrieve required fields
    descriptor = state.get("descriptor", "").strip()
    room_id = state.get("room_id")
    parent_event_id = state.get("parent_event_id", "")
    sender = state.get("sender")
    
    # Use global bot client if not provided
    bot_client = state.get("bot_client") or g.LUNA_CLIENT
    if not bot_client:
        err = "No bot client available."
        g.LOGGER.error(err)
        return {"error": err, "__next_node__": "chatbot_node"}

    # Start keep-typing indicator (optional)
    typing_task = asyncio.create_task(_keep_typing(bot_client, room_id))
    
    if not descriptor:
        err = "Missing required 'descriptor' parameter."
        g.LOGGER.error(err)
        await _post_in_thread(
            bot_client,
            room_id,
            parent_event_id,
            f"<p><strong>Error:</strong> {err}</p>",
            is_html=True
        )
        typing_task.cancel()
        return {"error": err, "__next_node__": "chatbot_node"}

    # Post initial status update
    await _post_in_thread(
        bot_client,
        room_id,
        parent_event_id,
        "<p><strong>Starting persona creation...</strong></p>",
        is_html=True
    )

    # Build GPT messages
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

    g.LOGGER.info("Requesting persona JSON from GPT with descriptor: %s", descriptor)
    try:
        gpt_response = await get_gpt_response(
            messages=messages,
            model="gpt-4",
            temperature=0.7,
            max_tokens=5000
        )
        await _post_in_thread(
            bot_client,
            room_id,
            parent_event_id,
            "<p>Received GPT response.</p>",
            is_html=True
        )
    except Exception as e:
        g.LOGGER.exception("GPT error in spawn_persona_node")
        await _post_in_thread(
            bot_client,
            room_id,
            parent_event_id,
            f"<p><strong>Error:</strong> GPT error: {e}</p>",
            is_html=True
        )
        typing_task.cancel()
        return {"error": f"GPT error: {e}", "__next_node__": "chatbot_node"}

    # Parse persona JSON
    try:
        persona_data = json.loads(gpt_response)
    except json.JSONDecodeError as e:
        g.LOGGER.exception("JSON parse error in spawn_persona_node")
        await _post_in_thread(
            bot_client,
            room_id,
            parent_event_id,
            f"<p><strong>Error:</strong> Invalid JSON from GPT: {e}</p>",
            is_html=True
        )
        typing_task.cancel()
        return {"error": f"Invalid JSON from GPT: {e}", "__next_node__": "chatbot_node"}

    required_keys = ["localpart", "password", "displayname", "system_prompt", "traits"]
    missing = [key for key in required_keys if key not in persona_data]
    if missing:
        err = f"Persona missing required fields: {missing}"
        g.LOGGER.error(err)
        await _post_in_thread(
            bot_client,
            room_id,
            parent_event_id,
            f"<p><strong>Error:</strong> {err}</p>",
            is_html=True
        )
        typing_task.cancel()
        return {"error": err, "__next_node__": "chatbot_node"}

    localpart     = persona_data["localpart"]
    password      = persona_data["password"]
    displayname   = persona_data["displayname"]
    system_prompt = persona_data["system_prompt"]
    traits        = persona_data.get("traits") or {}
    biography     = persona_data.get("biography", "")
    backstory     = persona_data.get("backstory", "")

    await _post_in_thread(
        bot_client,
        room_id,
        parent_event_id,
        f"<p>Persona JSON received. Creating persona for '{localpart}'.</p>",
        is_html=True
    )

    # Create and log in the persona
    try:
        bot_result = await create_and_login_bot(
            bot_id=f"@{localpart}:localhost",
            password=password,
            displayname=displayname,
            system_prompt=system_prompt,
            traits=traits
        )
    except Exception as e:
        g.LOGGER.exception("Error during create_and_login_bot in spawn_persona_node")
        await _post_in_thread(
            bot_client,
            room_id,
            parent_event_id,
            f"<p><strong>Error:</strong> Persona creation failed: {e}</p>",
            is_html=True
        )
        typing_task.cancel()
        return {"error": f"Persona creation failed: {e}", "__next_node__": "chatbot_node"}

    if not bot_result.get("ok", False):
        error_details = bot_result.get("error", "Unknown error")
        err = f"Persona creation failed: {error_details}"
        g.LOGGER.error(err)
        await _post_in_thread(
            bot_client,
            room_id,
            parent_event_id,
            f"<p><strong>Error:</strong> {err}</p>",
            is_html=True
        )
        typing_task.cancel()
        return {"error": err, "__next_node__": "chatbot_node"}

    bot_id = bot_result.get("bot_id", "")
    ephemeral_bot_client = bot_result.get("client")
    if bot_id.startswith('@'):
        bot_id = bot_id[1:]
    if bot_id.endswith(':localhost'):
        bot_id = bot_id[:-10]

    await _post_in_thread(
        bot_client,
        room_id,
        parent_event_id,
        f"<p>Persona created successfully with bot ID: {bot_id}.</p>",
        is_html=True
    )

    # Generate and upload a portrait
    final_prompt = descriptor  
    portrait_mxc = None
    try:
        portrait_url = await generate_image(final_prompt, size="1024x1024")
        if portrait_url:
            portrait_mxc = await _download_and_upload_portrait(
                portrait_url,
                localpart,
                password,
                system_prompt,
                traits,
                ephemeral_bot_client
            )
    except Exception as e:
        g.LOGGER.warning("Portrait generation/upload error: %s", e)
        await _post_in_thread(
            bot_client,
            room_id,
            parent_event_id,
            f"<p>Warning: Portrait generation/upload error: {e}</p>",
            is_html=True
        )

    # Build the final persona card HTML
    global_draw_appendix = g.GLOBAL_PARAMS.get("global_draw_prompt_appendix", "")
    card_html = _build_persona_card(
        localpart=localpart,
        displayname=displayname,
        biography=biography,
        backstory=backstory,
        system_prompt=system_prompt,
        dall_e_prompt=final_prompt,   # EXACT prompt used
        traits=traits,
        portrait_mxc=portrait_mxc,
        global_draw_appendix=global_draw_appendix 
    )

    await _post_in_thread(
        bot_client,
        room_id,
        parent_event_id,
        "<p>Persona creation complete!</p>",
        is_html=True
    )
    
    typing_task.cancel()
    g.LOGGER.info("Completed spawn_persona_node for persona %s", localpart)
    state.update({
        "html": card_html,
        "bot_id": bot_id,
        "__next_node__": "chatbot_node"
    })
    return state

async def spawn_persona_node_dep(state: dict) -> dict:
    """
    Node that creates a new persona from a descriptor provided via JSON.
    
    Expects in state:
      - descriptor: str, a textual description for the persona.
    
    The node will:
      1) Call GPT to generate a persona JSON.
      2) Parse the JSON and validate required fields.
      3) Create and log in the new persona (bot) via create_and_login_bot.
      4) Optionally generate and upload a portrait.
      5) Build an HTML character card containing persona details.
    
    Returns state with additional keys:
      - html: str, the final persona card HTML.
      - bot_id: str, the normalized bot ID.
      - __next_node__: str, e.g. "chatbot_node"
    """
    g.LOGGER.info("Entering spawn_persona_node...")

    # 1) Extract input from state
    descriptor = state.get("descriptor", "").strip()
    if not descriptor:
        err = "Missing required 'descriptor' parameter."
        g.LOGGER.error(err)
        return {"error": err, "__next_node__": "chatbot_node"}

    # Build GPT messages
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

    g.LOGGER.info("Requesting persona JSON from GPT with descriptor: %s", descriptor)
    try:
        gpt_response = await get_gpt_response(
            messages=messages,
            model="gpt-4",
            temperature=0.7,
            max_tokens=5000
        )
    except Exception as e:
        g.LOGGER.exception("GPT error in spawn_persona_node")
        return {"error": f"GPT error: {e}", "__next_node__": "chatbot_node"}

    # 2) Parse persona JSON
    try:
        persona_data = json.loads(gpt_response)
    except json.JSONDecodeError as e:
        g.LOGGER.exception("JSON parse error in spawn_persona_node")
        return {"error": f"Invalid JSON from GPT: {e}", "__next_node__": "chatbot_node"}

    required_keys = ["localpart", "password", "displayname", "system_prompt", "traits"]
    missing = [key for key in required_keys if key not in persona_data]
    if missing:
        err = f"Persona missing required fields: {missing}"
        g.LOGGER.error(err)
        return {"error": err, "__next_node__": "chatbot_node"}

    localpart     = persona_data["localpart"]
    password      = persona_data["password"]
    displayname   = persona_data["displayname"]
    system_prompt = persona_data["system_prompt"]
    traits        = persona_data.get("traits") or {}
    biography     = persona_data.get("biography", "")
    backstory     = persona_data.get("backstory", "")

    # 3) Register & login the persona
    try:
        bot_result = await create_and_login_bot(
            bot_id=f"@{localpart}:localhost",
            password=password,
            displayname=displayname,
            system_prompt=system_prompt,
            traits=traits
        )
    except Exception as e:
        g.LOGGER.exception("Error during create_and_login_bot in spawn_persona_node")
        return {"error": f"Persona creation failed: {e}", "__next_node__": "chatbot_node"}

    if not bot_result.get("ok", False):
        error_details = bot_result.get("error", "Unknown error")
        err = f"Persona creation failed: {error_details}"
        g.LOGGER.error(err)
        return {"error": err, "__next_node__": "chatbot_node"}

    bot_id = bot_result.get("bot_id", "")
    ephemeral_bot_client = bot_result.get("client")
    # Normalize bot_id: remove '@' prefix and ':localhost' suffix.
    if bot_id.startswith('@'):
        bot_id = bot_id[1:]
    if bot_id.endswith(':localhost'):
        bot_id = bot_id[:-10]

    # 4) Generate and upload a portrait
    # We'll use the original descriptor as the prompt for the portrait.
    final_prompt = descriptor  
    portrait_mxc = None
    try:
        portrait_url = await generate_image(final_prompt, size="1024x1024")
        if portrait_url:
            portrait_mxc = await _download_and_upload_portrait(
                portrait_url,
                localpart,
                password,
                system_prompt,
                traits,
                ephemeral_bot_client
            )
    except Exception as e:
        g.LOGGER.warning("Portrait generation/upload error: %s", e)

    # 5) Build the final persona card HTML
    global_draw_appendix = g.GLOBAL_PARAMS.get("global_draw_prompt_appendix", "")
    card_html = _build_persona_card(
        localpart=localpart,
        displayname=displayname,
        biography=biography,
        backstory=backstory,
        system_prompt=system_prompt,
        dall_e_prompt=final_prompt,   # EXACT prompt used
        traits=traits,
        portrait_mxc=portrait_mxc,
        global_draw_appendix=global_draw_appendix 
    )

    g.LOGGER.info("Completed spawn_persona_node for persona %s", localpart)
    # Return the resulting HTML card and bot_id; move to the next node (e.g. chatbot_node)
    state.update({
        "html": card_html,
        "bot_id": bot_id,
        "__next_node__": "chatbot_node"
    })
    return state

# ----------------------------
# Internal helper functions
# ----------------------------

async def _download_and_upload_portrait(
    portrait_url: str,
    localpart: str,
    password: str,
    system_prompt: str,
    traits: dict,
    ephemeral_bot_client
) -> str:
    """
    Downloads an image from portrait_url, uploads it to Matrix, updates the persona record,
    and sets the bot's avatar. Returns the mxc:// URI or None on failure.
    """
    os.makedirs("data/images", exist_ok=True)
    filename = f"data/images/portrait_{int(time.time())}.jpg"
    dl_resp = requests.get(portrait_url)
    dl_resp.raise_for_status()
    with open(filename, "wb") as f:
        f.write(dl_resp.content)

    portrait_mxc = await direct_upload_image(ephemeral_bot_client, filename, "image/jpeg")
    # Update persona record with portrait URL
    traits["portrait_url"] = portrait_mxc
    update_bot(
        f"@{localpart}:localhost",
        {
            "password": password,
            "system_prompt": system_prompt,
            "traits": traits
        }
    )
    # Attempt to set the avatar on the ephemeral client
    if ephemeral_bot_client:
        try:
            await ephemeral_bot_client.set_avatar(portrait_mxc)
        except Exception as e:
            g.LOGGER.warning("Error setting avatar: %s", e)
    return portrait_mxc

def _build_persona_card(
    localpart: str,
    displayname: str,
    biography: str,
    backstory: str,
    system_prompt: str,
    dall_e_prompt: str,
    traits: dict,
    portrait_mxc: str,
    global_draw_appendix: str
) -> str:
    """
    Builds and returns an HTML character card for the persona.
    The card includes:
      1) A title (the localpart),
      2) An italicized displayname,
      3) An optional portrait image,
      4) A table listing biography, backstory, system prompt, DALL·E prompt,
         draw prompt appendix, traits (as a nested table), and a version number.
    """
    def esc(text):
        return html.escape(str(text))

    # Build a nested table for traits.
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

    def row(label, val):
        return (
            "<tr>"
            f"<td style='padding:4px 8px; vertical-align:top;'><b>{esc(label)}</b></td>"
            f"<td style='padding:4px 8px;'>{val}</td>"
            "</tr>"
        )

    # Build portrait HTML if available.
    portrait_html = ""
    if portrait_mxc:
        portrait_html = (
            f"<div style='margin-bottom:8px;'>"
            f"<img src='{esc(portrait_mxc)}' alt='Portrait' width='300'/>"
            "</div>"
        )

    # Build rows for the main table.
    table_rows = "".join([
        row("Localpart", esc(localpart)),
        row("DisplayName", esc(displayname)),
        row("Biography", esc(biography)),
        row("Backstory", esc(backstory)),
        row("System Prompt", esc(system_prompt)),
        row("DALL·E Prompt", esc(dall_e_prompt)),
        row("Draw Prompt Appendix", esc(global_draw_appendix)),
        row("Traits", traits_subtable),
        row("Version", "1.0")
    ])

    table_html = (
        "<table border='1' style='border-collapse:collapse;'>"
        f"<tbody>{table_rows}</tbody>"
        "</table>"
    )

    # Combine header, optional portrait, and table.
    final_html = (
        f"<h2 style='margin-bottom:2px;'>{esc(localpart)}</h2>"
        f"<p style='margin-top:0; margin-bottom:10px;'><em>{esc(displayname)}</em></p>"
        f"{portrait_html}"
        f"{table_html}"
        "<p><em>Persona creation complete!</em></p>"
    )
    return final_html
