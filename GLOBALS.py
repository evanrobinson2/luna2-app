# GLOBALS.py - Global variables for Luna
# This file contains the global variables used by Luna, such as the OpenAI API key, the ChatOpenAI instance, and the bot messages database path.
#

import logging
from typing import Dict, List, Optional, Any
import asyncio
from nio import AsyncClient  # or wherever AsyncClient is actually imported from
import time
from datetime import datetime, timezone
from typing_extensions import TypedDict
from typing import Annotated

# LangGraph imports
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

# OpenAI wrapper from langchain_openai
from langchain_openai import ChatOpenAI
from langchain.schema import AIMessage, HumanMessage  # optionally for clarity

LUNA_VERSION: str = "Version 2025.01.25"
ROUTER_GRAPH: StateGraph = None
DATABASE_PATH: str  = "data/bot_messages.db"
CONFIG_PATH: str    = "data/config/config.yaml"
CONFIG: Dict[str, Any] = {} 
DATABASE_PATH: str  = "data/bot_messages.db" # The path to the bot messages database
HOMESERVER_URL="http://localhost:8008"
LUNA_USERNAME="lunabot"
LUNA_PASSWORD="12345"
PERSONALITIES_FILE="data/luna_personalities.json"
BOT_START_TIME = time.time() * 1000
OPENAI_API_KEY: str = ""
LLM: ChatOpenAI = None
SHOULD_SHUT_DOWN: bool = False
LOGGER: logging.Logger = None
BOTS: Dict[str, AsyncClient] = {} # A dict mapping localpart (str) -> AsyncClient for each bot
BOT_TASKS: List[asyncio.Task] = [] # A list of asyncio.Tasks for each bot’s sync loop
MAIN_LOOP: Optional[asyncio.AbstractEventLoop] = None # The main event loop (None until it’s assigned)
GLOBAL_PARAMS: Dict[str, str] = {} # A dictionary of global parameters for the bot
LUNA_LOCK_FILE = "/tmp/luna.pid"
# Store processed event IDs globally (or in a cache with TTL)
PROCESSED_EVENTS: set = set()

class State(TypedDict):
    # We annotate with add_messages so returning {"messages": [some_new_msg]}
    # appends it instead of overwriting.
    messages: Annotated[list, add_messages]
