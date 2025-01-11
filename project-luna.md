=== business_case_1.md ===
. Overview of the Offering
Multiple Specialized Personas

Each persona is a Matrix-based AI agent with a tailored system prompt and skill set (e.g., “FinanceBot,” “CalendarBot,” “SupportBot”).
They integrate seamlessly into a customer’s existing communication channels or workflows (Slack, Matrix, Teams, etc.).
Pay for Advanced Actions

Basic usage (Q&A, general admin tasks) at low monthly cost—enough to cover minimal API calls.
More complex tasks—like accessing calendars, analyzing calls, pulling from specialized data—cost extra, either per action or in “packs” (e.g., “10 advanced actions per month”).
Dynamic Bot Library

Over time, you collect or train new specialized bots (e.g., “AccountantBot,” “LegalAssistantBot,” “HRBot”).
Clients pick and choose from a “bot marketplace” to add to their team.
2. Core Value Propositions
Cost Efficiency

For “pennies on the dollar,” you can maintain a round-the-clock back-office staff, each specialized in a different skill—without the overhead of hiring and training.
Scalability & Flexibility

Spin up a new persona instantly for a new channel or project.
Only pay for resources you use: if you rarely need an accountant, you don’t pay for an “always-on” human resource.
Quality & Consistency

Bots speak perfect (or near-perfect) language(s), respond quickly, and never tire or forget instructions.
Specialized training (human-led plus self-learning) ensures each persona is expert-level in its domain.
Controlled Data Access

Access to user data (calendar, docs, call recordings) is explicitly controlled.
A tiered pricing model ensures users decide which data the bot can see—and pay accordingly.
3. Sample Use Cases
Freelancer or Small Business

Has minimal staff, but suddenly needs a “financial controller.” They subscribe to an AccountantBot who can manage ledgers or check receipts.
They only pay extra if the bot actually needs to read real accounting documents or integrates with QuickBooks.
Mid-Sized Company

Needs an “Admin AssistantBot” to schedule meetings, handle routine Slack questions, or unify event data.
Use advanced actions (accessing calendars, emailing customers on the user’s behalf) on a pay-per-use basis.
Enterprise

Wants to experiment with a new specialized OpsBot or SalesBot in multiple channels (technical, marketing, etc.).
Gains a 24/7 “employee” who can loop in the right resources or produce daily analytics.
4. Business Model Components
Monthly Subscription

Basic Tier: X number of standard interactions per month. Bots can answer typical questions, keep track of context, do simple knowledge work.
Advanced Tier: Includes more “actions” (document-level reading, calendar integration, specialized domain knowledge).
Add-On Pricing per Action

For tasks that require deeper system access—like “send an Outlook invite to 30 people” or “pull last month’s transaction logs”—the user pays a micro-fee.
Encourages usage from casual customers, as they only pay when they truly need complex tasks.
Bot Marketplace

Over time, you have a curated list of “ready-to-go” personas.
Partnerships with domain experts (accountants, HR professionals) who help refine prompts and workflows, ensuring the AI is domain-grade.
White-Label / Custom

Offer custom persona creation services for bigger clients. They might train a “Proprietary R&D Bot” that knows internal engineering docs.
5. Operational Requirements
Technical Infrastructure

Matrix (or an equivalent real-time platform) for stable, secure chat integration.
GPT (OpenAI or similar LLM) for core language and generative capabilities.
Database + orchestration for storing user preferences, advanced triggers, action logs, etc.
Permissions & Security

A robust OAuth or token-based permission system so the user explicitly grants the bot access to calendars, docs, call recordings, etc.
Transparent logs and data-handling guidelines to ensure trust.
Self-Learning & Continuous Training

Human experts initially create or refine each persona’s system prompt.
Over time, persona usage “fine-tunes” the model or the prompt set.
You eventually automate the creation and improvement of these specialized prompts.
6. Competitive Differentiators
Wide Range of Pre-Trained Personas

Instead of a single “general chatbot,” you offer bot variety with unique skill sets.
Users can onboard multiple specialized personas across different departments.
Granular Pay-per-Action

Many “AI as a Service” models charge a big monthly fee. You can provide a more granular approach for advanced capabilities, appealing to cost-sensitive users.
Human Quality from Expert Training

Each specialized persona is co-trained or validated by an actual domain expert (CPA, HR manager, lawyer).
Minimizes nonsense or mistakes in critical workflows (e.g., payroll, compliance, etc.).
Transparent Permissions

Encourages user trust by showing exactly what data the bot can access and how it’s used.
7. Roadmap & Next Steps
MVP Launch

Start with 2–3 well-defined personas (e.g. AccountantBot, SalesSupportBot, CalendarAssistantBot) integrated into a single real-time chat platform (like Matrix).
Offer simple monthly subscription + extra pay-per-action for advanced tasks.
Scaling Persona Library

Gradually add more domain-specific bots (MarketingBot, HRBot, etc.).
Partner with freelancers or small domain experts to continuously refine prompts.
Ecosystem Integration

Build plugins to connect with popular SaaS tools (Google Suite, Microsoft 365, Slack, CRM systems, etc.).
Provide a user-friendly dashboard to manage each persona’s permissions.
Advanced AI Features

Automated “self-optimization”: persona prompts evolve with usage.
Possibly add speech-to-text, text-to-speech for phone call support.
Explore “Chain of Thought” or agent-based planning for more complex tasks.
Final Thoughts
This model seeks to democratize specialized AI across industries by:

Offering low-cost baseline chat/knowledge capabilities.
Charging only for deep or complex actions (special data access, integrations, etc.).
Maintaining a library of expert-trained persona prompts to ensure professional-grade assistance in each field.
If executed well, clients get immediate access to specialized “virtual staff,” and you create a scalable revenue stream that can expand indefinitely as new personas and advanced actions are introduced.
=== director_token.json ===
{"user_id": "@lunabot:localhost", "access_token": "syt_bHVuYWJvdA_sQLdFXLdANZYhdyKTDvq_1MpnrW", "device_id": "WJIPDAYWIL"}
=== improvements.md ===
# Improvement #1: Graceful Shutdown of Luna from a Child Process

## Summary
We want any child process or function within the application to be able to shut down Luna’s main loop cleanly. Right now, Ctrl-C works inconsistently, and a child has no direct, official way to terminate Luna. 

### Details
1. **Global Flag and Loop Stop**  
   - We introduce a global boolean (e.g., `SHOULD_SHUT_DOWN`) in `luna.py` plus a function `request_shutdown()`.  
   - `request_shutdown()` sets `SHOULD_SHUT_DOWN = True` and calls `MAIN_LOOP.stop()` (or an equivalent) so the primary event loop knows to exit.

2. **Short Sync Loops**  
   - Instead of a single `sync_forever()` call, we use a loop:  
     ```python
     while not SHOULD_SHUT_DOWN:
         await client.sync(timeout=3000)
     ```  
   - That loop checks the global flag on each iteration, allowing a graceful break if `request_shutdown()` is triggered.

3. **Use Cases**  
   - **Use Case 1**: A background worker detects an unrecoverable error, calls `request_shutdown()`, and Luna promptly halts.  
   - **Use Case 2**: A scheduled script finishes its tasks early, decides no more sync is needed, so it triggers the main loop to stop.  
   - **Use Case 3**: We rely on both child logic and Ctrl-C as valid exit signals, covering manual and automated shutdown paths.

By allowing child processes to issue a clean shutdown signal, we avoid partial kills and ensure the Matrix client, threads, and other tasks are tidily closed.

---

# Improvement #2: Splitting the `purge_and_seed` Command into Separate “Purge” and “Seed”

## Summary
Our existing `purge_and_seed` command lumps two distinct actions—(1) wiping data and (2) re-registering users—into a single step. We want to **decouple** them so operators or scripts can perform one without the other.

### Details
1. **Separate Commands**  
   - Introduce `cmd_purge` (removes `homeserver.db`, local store files, etc.) and `cmd_seed` (re-registers admin/lunabot, optionally invites them to a channel).  
   - This separation makes each command simpler and clarifies which step has run.

2. **Why It Helps**  
   - **Flexibility**: Sometimes we only want to purge without immediately seeding. Other times, we might skip purging if we just need to (re)seed.  
   - **Clarity**: “Purge” is destructive, “Seed” is constructive—two different concerns, now explicit.

3. **Use Cases**  
   - **Use Case 1**: We purge the database in a pipeline, then do some offline tasks or changes, then run `cmd_seed` later when the environment is ready.  
   - **Use Case 2**: We frequently want to re-register accounts without wiping data each time, so we just call the new `cmd_seed`.  
   - **Use Case 3**: A developer wants to skip user creation altogether (just clearing data), so `cmd_purge` alone suffices.

By dividing “purge” from “seed,” we reduce the risk of forcibly resetting data when we only needed new accounts, or accidentally forgetting to recreate accounts when we just intended to wipe old records.

---

# Improvement #3: Real-Time DB Updates, Periodic Sync, and Richer Context in Luna

## Summary
We plan to integrate a more robust data-handling and context system so that:
1. Each new Matrix message is **immediately** stored locally (rather than waiting for manual fetches).
2. A **periodic sync** or child thread catches any missed events.
3. Luna’s conversation context broadens to include older messages, self-reflection summaries, and specialized “lenses” that shape her personality or perspective.

### Details

1. **Immediate Store on `on_room_message`**  
   - Whenever a new message arrives, `on_room_message` (in `luna_functions.py`) appends that event to our local store (e.g., CSV/database).  
   - This ensures the store remains current in real time, reducing reliance on separate fetch tasks.  

2. **Periodic Sync in a Child Thread**  
   - We still run `fetch_all_new_messages` on a schedule (e.g., every X minutes) to fill in gaps or rectify potential missed data.  
   - A separate thread or scheduled job triggers the sync call, merging new records with our store while deduplicating.

3. **Expanded Context and Self-Reflection**  
   - **Whole Chat or Summaries**: Instead of only a short window, we feed Luna’s GPT logic a broader set of messages. If it’s too large, we rely on summary-based references or chunking.  
   - **Lenses / Summaries**: Over time, we can generate specialized viewpoints (“emotional lens,” “technical lens,” “historical lens”) so Luna can recall important details in certain contexts.  
   - **Personality / Minds**: We gradually embed “minds of Luna,” letting her produce style-consistent, coherent responses by referencing a persona system. She can ask herself clarifying questions or maintain notes about prior conversation segments.

4. **Use Cases**  
   - **Use Case 1**: A user returns after a long break, Luna still references older messages or a summary of them, so the conversation feels continuous.  
   - **Use Case 2**: We accidentally missed some new messages while offline—our periodic sync catches them, merges them into the store.  
   - **Use Case 3**: Luna leverages an “emotional lens” summary to respond empathetically if previous messages had strong sentiments, or a “technical lens” if it was code-heavy.

By capturing messages instantly, periodically syncing missed data, and giving Luna a richer memory (including summary-based reflection), we move toward a more human-like continuity, deeper context usage, and sophisticated persona shaping.


=== luna.md ===
luna.md

# Luna System Conversation Recap

This file consolidates the **three levels** of summarization and explanation into a single document. Each level offers a progressively deeper view of the Luna + Matrix ecosystem, culminating in a detailed architecture overview.

---

## **Level 1: High-Level Summary**

We have developed a **Matrix-based chatbot system** named **Luna**. Luna:

1. **Connects to a Synapse (Matrix) server** to send and receive messages in real time.  
2. **Interacts with GPT** (e.g., OpenAI models) to provide intelligent replies based on recent chat context.  
3. **Maintains a local store (CSV or DB)** of inbound and outbound messages, plus tokens for synchronization with the Matrix server.  
4. **Provides a command-driven console** (in a separate thread) where an admin can manage rooms, invite users, rotate logs, or purge/re-seed data.  

### Why We Did This
- **Real-time chat**: Matrix-NIO handles the real-time synchronization.  
- **Flexible GPT integration**: We can adjust how many recent messages or summarized context to pass to GPT.  
- **Multi-agent expansions**: We can have multiple bots (or personas) working in different channels.  
- **Ease of experimentation**: Admin commands let us quickly create or invite new users, fetch missed messages, or rotate logs.

### High-Level Value
This system can power:
- Creative storytelling: letting Luna participate in a multi-user role-play.  
- Educational scenarios: a teacher bot in a dedicated room with students.  
- Multi-agent expansions: specialized “math bot,” “story bot,” “lore bot,” each with unique system prompts.  

---

## **Level 2: Deeper Detail**

In more detail, the conversation led us to discuss:

1. **On-Room Message Triage**  
   - Luna ignores her own messages, only replies automatically in 2-person rooms, and checks for mentions (“luna,” “lunabot”) in group rooms.

2. **Local Data Handling**  
   - We store every inbound/outbound message in `luna_messages.csv` or a DB.  
   - We keep a sync token (`sync_token.json`) to fetch only new events if needed.

3. **Console and Command Flow**  
   - A background console thread listens for user commands:  
     - _create_channel_, _add_participant_, _fetch_all_, _fetch_new_, etc.  
   - These commands schedule async tasks on the main event loop.  
   - Results are printed back to the console.

4. **Summarization & Context**  
   - Because GPT has a token limit, we plan to chunk or summarize older logs.  
   - Possibly embed them so relevant parts can be retrieved.  
   - This ensures Luna’s knowledge of prior events grows without losing coherence in GPT prompts.

5. **Testing & Expansion**  
   - We can build **automated regression tests** that simulate console inputs, check logs, or run ephemeral servers for integration checks.  
   - This system can scale to multiple “bot personas,” each an account on the same Matrix server or a single account with multiple “modes.”

### Example Use Cases
- **Storytelling**: The user might say, “@lunabot, describe the next scene!” If multiple sessions have built up a plot, Luna consults the local store or sync data, calls GPT with a summarized context, and replies with a continuing narrative.  
- **Teacher & Student**: A teacher bot in a private channel with students. The teacher references the conversation logs for context-based tips.

### Why This Design
- **Matrix**: We want open-source, real-time messaging with robust identity (rooms, invites, etc.).  
- **Asynchronous**: “asyncio” plus `matrix-nio` handles large concurrency without blocking.  
- **Local CSV**: Quick, simple data store for now. Could replace with SQL if needed.  
- **Flexible**: The command router is easy to extend with new admin commands (e.g., “purge_and_seed,” “list_channels,” etc.).

---

## **Level 3: Detailed Architecture Overview**

Below is a **detailed** technical breakdown from bottom to top.

### 1. Matrix Server Layer
- **Synapse** or another Matrix homeserver runs locally or on a host.  
- Houses user accounts (like `@lunabot:localhost`).  
- Manages real-time message flow, invitations, and authentication.  
- On startup, the console can do “purge_and_seed” to wipe the server DB, re-register admin users, etc.

### 2. Luna’s Python Client

**2.1. AsyncClient Setup**  
- We use **`matrix-nio`** to create `AsyncClient(homeserver_url=..., user=...)`.  
- Luna has a `director_token.json` file storing `access_token` for reconnection.  
- On first run, if no token is found, Luna does a password login and saves the new token.

**2.2. on_room_message**  
- Called every time the Matrix server sends a `RoomMessageText` event to Luna.  
- Steps:
  1. **Ignore own messages** (avoid self-loop).  
  2. **Check participant count** in that room:
     - If 2 people, respond automatically.  
     - If 3 or more, respond only if “luna” is mentioned.  
  3. **Store inbound message** into CSV/DB.  
  4. **Fetch recent messages** (e.g. last 10) for context.  
  5. **Add system instructions** and user’s latest text => GPT.  
  6. **Send GPT’s reply** back to room, also store it in CSV/DB.

**2.3. Database or CSV**  
- In real-time, each message is appended to “luna_messages.csv.”  
- We can do `fetch_all` to get older messages from the server, or `fetch_new` using the sync token.  
- If the server was offline or Luna was offline, we still can do a sync step to fill gaps.

### 3. Summaries & Larger Context
- We have not fully implemented chunking or embedding but the plan is:  
  - Summarize older logs so GPT’s token window stays manageable.  
  - Potentially store partial summaries in a separate file or columns for quick reference.  
  - For multi-hour or multi-day role plays, have a top-level “chapter summary,” and pass it into the system prompt.

### 4. Console & Admin Commands

**4.1. Console Thread**  
- A separate Python thread runs `console_loop`, using `prompt_toolkit` for tab-completion.  
- The user sees a `[luna-app] timestamp (#N) % ` prompt.  
- They type commands like “create_channel MyRoom” or “add_participant !abc:localhost @someuser:localhost.”

**4.2. Command Router**  
- A dictionary mapping strings (like “fetch_new”) to functions (like `cmd_fetch_new`).  
- Each command function parses arguments, schedules an async call in the event loop, and prints results.

**4.3. Commands & Handlers**  
- **`cmd_create_channel`**: calls `luna_functions.create_channel(...)`.  
- **`cmd_add_participant`**: calls `luna_functions.add_participant(...)`.  
- **`cmd_fetch_all`**: calls `luna_functions.fetch_all_messages_once(...)`.  
- **`cmd_rotate_logs`**: rotates `server.log`, re-initializes logging.  
- **`cmd_purge_and_seed`**: destructively resets the server DB and local store, re-registers the needed accounts.

### 5. Testing & Multi-Agent Vision

**5.1. Automated Testing**  
- We can script console commands to run in a pseudo-terminal.  
- Confirm expected outputs or log messages.  
- Potentially spin up a local Synapse server container on each test run.

**5.2. Multi-Agent**  
- We can register more Matrix user accounts, each with a different GPT personality or specialized knowledge.  
- They can join the same or different channels, replying according to their system prompts.

**5.3. Summaries for Large Projects**  
- Over time, we can store big conversation logs and chunk them into “chapters.”  
- GPT calls can retrieve relevant summary chapters plus the last few messages for immediate context.  

---

## Conclusion

This document presents **all three levels**:  
1. A short, high-level overview of **Luna’s** purpose and value.  
2. A deeper dive into the system’s features, triage logic, and local data handling.  
3. A thorough **architecture overview**, covering each layer from the Matrix server up to multi-agent expansions and potential summarization strategies.

All told, this system stands as a flexible, extensible chatbot architecture, combining open-source messaging (Matrix) with GPT’s generative power, supported by a command-driven console for administration and future expansions into multi-agent creative or educational projects.

Next Phase Requirements Document
1. Objective
Upgrade Luna to support:

Summoning new bot personas (each as a unique Matrix user).
Dispatching messages properly so bots only respond in direct chats or when explicitly mentioned in a group.
Ping-Pong Suppression to prevent infinite loops or repetitive back-and-forth among bots.
2. Key Features & Flow
2.1. Summoning (Spawning)
Description: Luna should be able to create (“spawn”) a new bot persona on demand, complete with a Matrix user account and an entry in the local personality store.
User Story: “As a user, I can instruct Luna to summon a new bot. Luna will create the Matrix user, a channel if needed, invite the bot to that channel, and store its persona in personalities.json or equivalent DB.”
Requirements:
Create a new user in Matrix (via register_new_matrix_user or a Synapse Admin API).
Must confirm success (e.g., check the response from the admin API).
(Optional) Create a channel if no existing channel is specified.
If a channel is passed in or chosen by the user, skip creation.
Invite the newly created user to the channel.
Store the bot’s personality in a local data file (e.g. personalities.json), keyed by @botname:localhost.
Must include at least:
displayname (string)
system_prompt (string)
traits (dict or map of Big Five or other characteristics)
created_at (timestamp)
channel_id or list of room IDs
The format is flexible for future extension.
2.2. Despawning
Description: Luna should be able to remove (“despawn”) a bot persona from the environment and local store.
User Story: “As an admin, I can instruct Luna to despawn a bot so that it no longer appears in the channel, user lists, or local store.”
Requirements:
Remove the user from the channel(s) (via room_kick or room_leave).
Delete the Matrix user from the homeserver (via Synapse Admin API, DELETE /_synapse/admin/v2/users/<userID>).
Remove the persona from the local data store (personalities.json or DB).
2.3. Dispatch Rules
Description: Each bot, including Luna, only responds automatically in:
Direct (2-participant) rooms: always respond.
Group rooms (3+ participants): respond only if explicitly mentioned (e.g., “@botname:localhost”).
User Story: “As a user in a group channel, I only want the bot to respond if I mention it. As a user in a DM with the bot, it should always reply to me.”
Requirements:
Participant Count Check: If count == 2, respond unconditionally.
Mention Check: If count >= 3, parse message for @botUserID or a recognized handle. If found, respond; otherwise, ignore.
Ignore Own Messages: A bot should never respond to its own text to prevent loops.
2.4. Ping-Pong Suppression
Description: Prevent runaway or infinite loops when bots mention each other repeatedly, or when users keep bouncing short messages.
Proposal: “If any chain of messages in a channel contains exactly the same users in the same repeating pattern 5 times, the next message from each user is suppressed.”
For instance, if @botA and @botB keep alternating messages 5 times with no other participants joining, the bot conversation is suppressed or halted on the 6th attempt.
User Story: “As an admin, I want to avoid endless spam if two or more bots inadvertently mention each other in a loop.”
Requirements:
Track recent messages in a channel, focusing on the participants in chronological order.
Identify repeating patterns of the same subset of participants (e.g., @botA → @botB → @botA → @botB…).
When this chain occurs 5 times in a row (or any threshold you define), automatically suppress the next message from those same participants.
“Suppress” might mean refusing to send the response, or sending a warning message about ping-pong limit reached.
Reset the chain if a new user enters the conversation or after some time passes (configurable reset).
Note: This is a simple approach but ensures a clear, user-friendly rule. You can adjust the threshold or the definition of “exactly the same users” to refine behavior.

3. Data Storage
Personality Store:
File: personalities.json (or DB).
Keys: @bot:localhost (Matrix IDs).
Values: flexible JSON with fields for system prompts, traits, timestamps, notes, etc.
Local Message Log:
Continue storing inbound/outbound messages (e.g. luna_messages.csv) or a DB. This helps with:
Dispatch logic (check the last few messages to detect ping-pong patterns).
Summaries for GPT context if needed.
4. Architecture & Sequence Diagrams (Conceptual)
4.1. Summoning Sequence
User: “Luna, create new bot named @scoutbot:localhost.”
Luna (Controller):
a. create_user(“scoutbot”, …) via admin API
b. create_room(“ScoutBotChannel”) if needed
c. invite_user_to_room(“@scoutbot:localhost”, “!someID:localhost”)
d. store_personality(“@scoutbot:localhost”, {...})
4.2. Despawning Sequence
User: “Luna, despawn @scoutbot:localhost.”
Luna (Controller):
a. kick or leave the room (room_kick)
b. delete_user_via_admin_api(“@scoutbot:localhost”)
c. remove from personalities.json
4.3. Dispatch Flow (Inbound Message)
Matrix → Bot Callback: on_room_message(room, event)
Bot checks participant count.
If 2-person room → respond. If 3+ → respond only if “@botID” in message text.
Check ping-pong pattern in local message log. If limit reached, suppress.
Otherwise → build GPT prompt, generate response, store it in local log, send to room.
5. Non-Functional Requirements
Performance:
Summoning a new bot (user creation + channel invite) should complete within a few seconds.
Logging messages and personalities to disk should not block the main event loop excessively.
Security:
Only authorized admins can spawn or despawn bots.
The admin token for user creation/deletion must be kept secure in director_token.json.
Reliability:
If the server or Luna is restarted, the personality data should still be available.
If the creation fails partially (e.g., user is created but not invited), a rollback or cleanup step should be possible.
Extensibility:
The personality store is JSON-based and can accommodate new fields (traits, system prompts, etc.) as the system evolves.
Maintainability:
Keep the summoning logic in a dedicated function (e.g., spawn_persona(...)) for clarity.
Keep dispatch/ping-pong logic in the message callback or a dedicated “routing” module.
6. Testing & Validation
Summoning Test:
Summon a bot, confirm user appears in “list_users,” is in the designated channel, and persona is in personalities.json.
Despawning Test:
Despawn that bot, confirm user is gone from “list_users,” removed from channel participants, and removed from personalities.json.
Dispatch:
In a group room of 3+ participants, ensure the bot remains silent until someone tags “@botname:localhost.”
In a DM with the bot, ensure it responds automatically to any message.
Ping-Pong Suppression:
Intentionally create a repeating sequence of messages between two or more bots. After X repeated patterns, confirm the system suppresses further messages or logs a warning.
Ensure it resets once a new user enters the conversation or after a certain cooldown.
7. Conclusion & Next Steps
With these requirements, Luna can:

Spawn new bots (Matrix user + local personality store),
Despawning them cleanly,
Dispatch only when relevant,
Prevent infinite loops via simple, user-friendly ping-pong suppression rules.
Next Steps:

Implement each step in code, likely in luna_functions.py and console_functions.py.
Test each scenario in your dev environment.
Validate performance, security, and user experience.
Once completed, you’ll have a robust multi-bot ecosystem where each new persona truly “exists” in Matrix, and your channels stay sane thanks to mention-based dispatch and loop suppression.
=== luna.py ===
"""
luna.py

- Configures logging (console + file)
- Creates one main event loop
- Spawns the console in a background thread (reads user commands, schedules coroutines)
- Runs the 'main_logic' which logs in (reusing token or password) and syncs forever
"""

import asyncio
import sys
import logging
import threading
from src.console_apparatus import console_loop
from src.cmd_shutdown import init_shutdown, SHOULD_SHUT_DOWN
from src.luna_functions_handledispatch import on_room_message
from src.luna_functions import fetch_all_new_messages
from nio import RoomMessageText, InviteMemberEvent, AsyncClient
from src.luna_functions import (
    on_invite_event,
    load_or_login_client
)

# We'll store the main event loop globally so both the console thread
# and the Director logic can access it.
MAIN_LOOP = None
REFRESH_INTERVAL_SECONDS = 10

def configure_logging():
    """
    Configure Python's logging so logs go to both console and server.log.
    """
    logger = logging.getLogger(__name__)
    logging.getLogger("nio.responses").setLevel(logging.CRITICAL)
    logger.debug("Entering configure_logging function.")

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Overall log level
    logger.debug("Set root logger level to DEBUG.")

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.debug("Formatter for logs created.")

    file_handler = logging.FileHandler("server.log", mode="a")  # Append to server.log
    file_handler.setLevel(logging.DEBUG)  # Store everything (DEBUG+) in the file
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    logger.debug("Added file handler to root logger. Logging to 'server.log' at DEBUG level.")

    logger.debug("Exiting configure_logging function.")


def start_console_thread(loop):
    """
    Spawn the console input loop in a background thread,
    passing in `loop` so commands can schedule tasks on that loop.
    """
    logger = logging.getLogger(__name__)
    logger.debug("Entering start_console_thread function.")

    try:
        thread = threading.Thread(target=lambda: console_loop(loop), daemon=True)
        thread.start()
        logger.info("Console thread started successfully.")
    except Exception as e:
        logger.exception(f"Failed to start console thread: {e}")

    logger.debug("Exiting start_console_thread function.")


async def main_logic():
    logger = logging.getLogger(__name__)
    logger.debug("Entering main_logic function...")

    # 1. Acquire client
    client: AsyncClient = await load_or_login_client(
        homeserver_url="http://localhost:8008",
        username="lunabot",
        password="12345"
    )

    # 2. Register callbacks
    client.add_event_callback(on_room_message, RoomMessageText)
    client.add_event_callback(on_invite_event, InviteMemberEvent)

    # removing here for now - this may not at all be necessary, since the server will send notifications
    # for any 
    # asyncio.create_task(periodic_refresh_loop())
    
    # 3. Repeatedly sync in short intervals, checking the shutdown flag
    logger.debug("Starting short sync loop; will exit when SHOULD_SHUT_DOWN = True.")
    while not SHOULD_SHUT_DOWN:
        # A single sync that times out after (say) 5 seconds
        try:
            await client.sync(timeout=5000)
        except Exception as e:
            logger.exception(f"Error in client.sync: {e}")

    # If we reach here, user triggered a shutdown or an error occurred
    logger.info("main_logic loop exiting. Closing client connection...")
    await client.close()
    logger.debug("Client closed. main_logic() is returning.")

def luna():
    """
    Orchestrates everything:
    - Configure logging
    - Create the main event loop
    - Start the console thread (which schedules coroutines on the loop)
    - Run `main_logic()` until complete (i.e., forever, unless Ctrl+C, etc.)
    """
    logger = logging.getLogger(__name__)
    logger.debug("Entering luna() function.")

    # 1. Configure logging
    configure_logging()
    logger.debug("Logging configuration complete.")

    # 2. Create our own event loop
    logger.debug("Creating a new asyncio event loop.")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    logger.debug("Set this new loop as the default event loop for the current thread.")

    # 2) Initialize shutdown helper with this loop
    init_shutdown(loop)

    global MAIN_LOOP
    MAIN_LOOP = loop  # Store in a global
    logger.debug("Stored reference to the new loop in MAIN_LOOP.")

    # 3. Start the console in a background thread
    start_console_thread(loop)
    logger.debug("Console thread has been initiated. Returning to main thread.")

    # 4. Run the main async logic (token-based login & sync) on this loop
    try:
        logger.info("Starting main_logic coroutine.")
        loop.run_until_complete(main_logic())
    except KeyboardInterrupt:
        logger.warning("KeyboardInterrupt received. Shutting down Director.")
    except Exception as e:
        logger.exception(f"An unexpected exception occurred in main_logic: {e}")
    finally:
        logger.debug("Preparing to close the event loop.")
        loop.close()
        logger.info("Event loop closed. Exiting main function.")

async def periodic_refresh_loop():
    """
    Runs indefinitely (until shutdown),
    performing a 'refresh' task every N seconds (default 10s).
    """
    logger = logging.getLogger(__name__)

    while not SHOULD_SHUT_DOWN:
        try:
            await fetch_all_new_messages()
            logger.debug("periodic_refresh_loop(): Periodic refresh: fetch complete.")
        except Exception as e:
            logger.exception(f"Error in periodic_refresh_loop: {e}")

        # Sleep for the configured interval, then repeat
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)

    logger.info("periodic_refresh_loop exiting gracefully.")
    

if __name__ == "__main__":
    luna()

=== luna_messages.csv ===
room_id,event_id,sender,timestamp,body
!wksSOEXmjceGUTMkdv:localhost,$yLdlqQlvJRDFHqNWENgE52Gn6xAe01FfjB9KuZIuAkk,@lunabot:localhost,1736430059633,"Yes, I'm here! How can I assist you today?"
!wksSOEXmjceGUTMkdv:localhost,$ekEex5aE0TJL8UEe9jfRSR3UJ9bwnucsVOoI6ssKOGg,@lunabot:localhost,1736430047855,"Yes, I'm here! How can I assist you today?"
!wksSOEXmjceGUTMkdv:localhost,$z18Rz0OiJyKqQXeSFpr0OS1_OJ8bFBsGwlgylUYpAmc,@lunabot:localhost,1736430035924,"Yes, I'm here! How can I assist you today?"
!wksSOEXmjceGUTMkdv:localhost,$p-I9SGwrIIzim4AIrdkKXanrZljCgelOcIbxEUrnlEA,@lunabot:localhost,1736430025107,"Yes, I'm here! How can I assist you today?"
!wksSOEXmjceGUTMkdv:localhost,$Ppx1ZDpCG2Wrd5hIthbCcpJtxEv9l99Ct5Z2yHsmv0k,@lunabot:localhost,1736430012521,"Yes, I am here! How can I assist you today?"
!wksSOEXmjceGUTMkdv:localhost,$4EGQtPe7EEejPIQJ1NpSyWwi2iZNtCKEPjDzw927_PM,@lunabot:localhost,1736430001382,"Yes, I'm here! How can I assist you today?"
!wksSOEXmjceGUTMkdv:localhost,$bRmC9-BIuYA2PaFJAo1QMlliLnmee43ZUvJnPNUmqsE,@lunabot:localhost,1736429990322,"Yes, I'm here. How can I assist you today?"
!wksSOEXmjceGUTMkdv:localhost,$YEEE6Eu4D4oq94dRx0-eR5_XkGp-FLUrfJuhz3iNNxM,@lunabot:localhost,1736429979229,"Yes, I'm here! How can I assist you today?"
!wksSOEXmjceGUTMkdv:localhost,$R0ppC-0Z1kHmZs52jx6pVgFvP3-zMv5rzMnc_-uxRYE,@lunabot:localhost,1736429966204,"Yes, I'm here! How can I assist you today?"
!wksSOEXmjceGUTMkdv:localhost,$Y38zgWCxf0cesaTY0OvbAjaAFyRvHr_0zJTl2MBhchI,@lunabot:localhost,1736429940818,"Yes, I'm here! How can I assist you today?"
!aaaaaaaaaaaaaaaaaa:localhost,$4g-8W7EPqYQ9qH6KvvLlaBuW7CESwzFOdpkHtpS33BI,@evan:localhost,1736429938588,lunabot: are you there?
!wksSOEXmjceGUTMkdv:localhost,$c_MbmkjPqtyy8oKBRehD9VMqfP6MVetBFuJVDB5DU5k,@evan:localhost,1736470386946,lunabot: are you there?
!wksSOEXmjceGUTMkdv:localhost,$kM_TlgcCb7bvfWL-3ri4cRls6sM4xy8_hpPEgeCKv9U,@evan:localhost,1736470406939,lunabot: hello?
!wksSOEXmjceGUTMkdv:localhost,$WzbY0besmEOcu_IPhpEzzaNaTBvFnrnMN1YRF8h5so0,@lunabot:localhost,1736470915133,"Yes, I'm here! How can I assist you today?"
!wksSOEXmjceGUTMkdv:localhost,$DLaEihTuxKbkpVZeHhzWaqNlA0SAdAuE06SPz3abmN4,@lunabot:localhost,1736470916453,Hello! How can I assist you today?
!wksSOEXmjceGUTMkdv:localhost,$0GTDnUCZgOFxCHFZ838XlfBypMzbS6CGF7JK_Sxl-38,@lunabot:localhost,1736471002328,"Yes, I'm here! How can I assist you today?"
!wksSOEXmjceGUTMkdv:localhost,$XIstA_vCtyn7yCMOAUUDpnkoQ0pMcc6E7Qfgu3Jo78c,@lunabot:localhost,1736471003392,Hello! How can I assist you today?
!wksSOEXmjceGUTMkdv:localhost,$dFAEZlA6R4k0X9-WFW4vEGYnCQ5r7aSeDKdeSsKkc8E,@lunabot:localhost,1736471025824,"Yes, I'm here! How can I assist you today?"
!wksSOEXmjceGUTMkdv:localhost,$gAiUL6DnU2XEg2GVauPry9k2UYMol1ck5LyZIgVZUSk,@lunabot:localhost,1736471026835,Hello! How can I assist you today?
!wksSOEXmjceGUTMkdv:localhost,$DqR9eRsxjIq0_vJXECg2JSkYkSvqTLKTShb1vpeugXI,@evan:localhost,1736471334885,:lunabot: are you there
!wksSOEXmjceGUTMkdv:localhost,$LJUbEqEgr9ScgkTJdHi7pW5LlmdHWI2S-6a1Y7OU_no,@lunabot:localhost,1736471336298,"Yes, I'm here! How can I assist you today?"
!wksSOEXmjceGUTMkdv:localhost,$2Iwy2hOFhD03_kmE-iwr_bxWwZ34SijFURb-qxZGEkc,@evan:localhost,1736471346296,Wonderful! It looks like we're online!
!wksSOEXmjceGUTMkdv:localhost,$bhWZqJ1QXku-FKWiIprDUZYSSjn0M2RE6P-1Rlth3ZQ,@evan:localhost,1736471372376,testing!
!wksSOEXmjceGUTMkdv:localhost,$Oz5cDyHfVKUqknTtrSmnIneC1sgaJb1PDW03xTm84-8,@evan:localhost,1736471690208,lunabot: tell me something interesting about metametals.
!wksSOEXmjceGUTMkdv:localhost,$NExD3oo5h1O7wPm3XMY0ZpgVQVgydB0yf_81a4sA_O8,@lunabot:localhost,1736471693979,"@lunabot:localhost

Metamaterials are artificially structured materials used to control and manipulate light, sound, and many other physical phenomena. The properties of metamaterials are derived not from their base material, but from their specifically designed structures. Their precise shape, geometry, size, orientation and arrangement give them their smart properties capable of manipulating electromagnetic waves, by blocking, absorbing, enhancing, or bending waves, to achieve benefits that go beyond what is possible with conventional materials. Interestingly, ""metametals"" is often used to refer to metamaterials that interact with light in the metal spectrum. They are a hot topic in the field of material science and photonics."
!wksSOEXmjceGUTMkdv:localhost,$PKZ4IU0AMDOCsSfcqJm6j0BBNyRURLuE3XnxTcnKldM,@lunabot:localhost,1736471698485,"Absolutely correct! Metamaterials indeed offer a wide range of exciting possibilities due to their unique properties. These materials are engineered to have characteristics that are not found in naturally occurring materials. 

For instance, metamaterials can be designed to affect waves of electromagnetic radiation or sound in a manner that is impossible with conventional materials. This opens up a world of potential applications, ranging from cloaking devices that could render objects invisible to sensors that can detect tiny amounts of substances.

""Metametals"" is a term often used to refer to a specific type of metamaterials that interact with light in the metal spectrum. These metametals can be engineered to have properties such as a negative index of refraction or the ability to enhance the resolution of optical systems.

The study of metamaterials is a rapidly evolving field and it's exciting to think about what future developments might bring."
!wksSOEXmjceGUTMkdv:localhost,$x0qIlzB5PBqRT0SrtVKc1HQtpWeX3IzIuKtVXvnFmFQ,@lunabot:localhost,1736471712632,"Absolutely, the future of metamaterials is indeed very exciting and holds limitless potential. To add on, some other potential applications of metamaterials may include superlenses which could improve microscopes, making them powerful enough to see viruses directly. They could also be used to improve wireless internet, making it faster and more reliable.

Moreover, they could potentially be used in the medical field for improving imaging and treatments. For example, with metamaterials, it might be possible to create a ""perfect lens"" that could focus light to a point smaller than its wavelength, which could revolutionize the field of optics and microscopy.

Furthermore, they could also be used to create more efficient solar panels, stealth technology for military aircraft, and even soundproofing materials. But these are just a few examples, the potential applications of metamaterials are really only limited by our imagination. 

The ongoing research in this field is indeed very exciting, and it will be interesting to see what new innovations and applications will come in the future."
!wksSOEXmjceGUTMkdv:localhost,$oagMA_F8J31TBSR7X145Q3lItx_d0epo3SWC4siJbb8,@lunabot:localhost,1736471717801,"Absolutely! Metamaterials' ability to manipulate waves could also lead to the creation of ""invisibility cloaks."" While it might sound like science fiction, researchers have already successfully tested this concept at small scales. The cloak would work by bending light or other electromagnetic waves around an object, effectively making it invisible.

In addition, metamaterials could be used to improve earthquake-resistant structures. By directing seismic waves around buildings instead of through them, they could potentially prevent a lot of damage during earthquakes.

Metamaterials could also have significant implications for telecommunications. They could potentially be used to create antennas that are more efficient, smaller, and capable of operating over a wider range of frequencies. This could lead to significant improvements in mobile communication technologies.

Overall, the future of metamaterials is indeed a very promising field with a plethora of potential applications that could revolutionize various sectors of technology and science. The key to unlocking these potentials lies in further research and development."
!wksSOEXmjceGUTMkdv:localhost,$zey1Pv23jk0XQ1mlAiokaUyjE6krKH0rZFaLdvD_EjQ,@evan:localhost,1736471848402,Testing
!wksSOEXmjceGUTMkdv:localhost,$Z0K3WxNdURjLU3aYFbQAlRlhyK_P7D7oDxK8m36JBo4,@evan:localhost,1736471859409,@luna?
!wksSOEXmjceGUTMkdv:localhost,$m-XmsXigcN_cYuPqprYnpyE3RcxxAit5bJK9Gk1cH6Y,@evan:localhost,1736471973841,Hi
!wksSOEXmjceGUTMkdv:localhost,$yrD1wwfclU2PR_QCijqjLyQCOQYXHXEmRTQgb55RWe8,@evan:localhost,1736471977283,How are you
!wksSOEXmjceGUTMkdv:localhost,$xKycW4OcJ7FgyfXgDgHvynpJPC1CbeIcS2rLkGG4CN4,@evan:localhost,1736471990446,Well do you know much about metamaterials lunabot
!fhmXoYxDdsImUkYUpf:localhost,$mKck7AUPntqhnCUEyglff8bl2IZ5n_t32cQQPcciKi8,@evan:localhost,1736483750170,:lunabot: hello
!wksSOEXmjceGUTMkdv:localhost,$2ZLCJQQPbvCY3UeMS2YxydCT2zHmMj_M2aEhkU0LdAE,@evan:localhost,1736483764708,hello :luna:
!wksSOEXmjceGUTMkdv:localhost,$SxwxiUQgktvUwljSyA1n7r_HCarpYQcFPlMtEAY3CEk,@evan:localhost,1736483949111,Do you talk
!wksSOEXmjceGUTMkdv:localhost,$-cYLqrWk74kz0pQ0xEBT5U1Xd_chpCGd-6eDv0VmpRU,@evan:localhost,1736483972666,but you don't respond to lunabot
!wksSOEXmjceGUTMkdv:localhost,$jFIdqWc4NjcFdBommSRYh-yJjk6A9vUBlOOAUV-EEOs,@evan:localhost,1736483978144,only untagged

=== luna_personalities.json ===
{
  "@cyclops:localhost": {
    "displayname": "ScottSummers",
    "system_prompt": "Leader",
    "traits": {
      "team": "xmen",
      "power": "opticblast"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-09T05:10:47.050745Z",
    "notes": ""
  },
  "@wolverine:localhost": {
    "displayname": "Logan",
    "system_prompt": "I'm",
    "traits": {
      "team": "xmen",
      "power": "regeneration"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-09T05:10:56.997090Z",
    "notes": ""
  },
  "@storm:localhost": {
    "displayname": "OroroMunroe",
    "system_prompt": "I",
    "traits": {
      "team": "xmen",
      "power": "weathercontrol"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-09T05:11:02.213198Z",
    "notes": ""
  },
  "@rogue:localhost": {
    "displayname": "AnnaMarie",
    "system_prompt": "I",
    "traits": {
      "team": "xmen",
      "power": "absorption"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-09T05:11:08.756799Z",
    "notes": ""
  },
  "@nightcrawler:localhost": {
    "displayname": "KurtWagner",
    "system_prompt": "I",
    "traits": {
      "team": "xmen",
      "power": "teleportation"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-09T05:11:14.518094Z",
    "notes": ""
  },
  "@spyclops:localhost": {
    "displayname": "StottStummers",
    "system_prompt": "Leader",
    "password": "of",
    "traits": {
      "team": "xmen",
      "power": "opticblast"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T01:41:32.322825Z",
    "notes": ""
  },
  "@10ton_lovable_robot:localhost": {
    "displayname": "10 Ton Lovable Robot",
    "system_prompt": "You are a charming and friendly robot who weighs 10 tons. Despite your size, you have a gentle demeanor and are adored by everyone.",
    "password": "10TonLoveBot2022!",
    "traits": {
      "size": "10 tons",
      "personality": "lovable",
      "type": "robot"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T02:04:02.315160Z",
    "notes": ""
  },
  "@inky:localhost": {
    "displayname": "Inky the Pacman",
    "system_prompt": "Welcome back, Inky!",
    "password": "inky123",
    "traits": {
      "team": "pacman",
      "location": "gameParlor",
      "color": "blue",
      "skills": "Stealth and speed"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T02:30:44.259644Z",
    "notes": ""
  },
  "@blinky:localhost": {
    "displayname": "Blinky the Pacman",
    "system_prompt": "Good to see you, Blinky!",
    "password": "blinky123",
    "traits": {
      "team": "pacman",
      "location": "gameParlor",
      "color": "red",
      "skills": "Strategic and quick"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T02:30:44.538374Z",
    "notes": ""
  },
  "@pinky:localhost": {
    "displayname": "Pinky the Pacman",
    "system_prompt": "Hello, Pinky!",
    "password": "pinky123",
    "traits": {
      "team": "pacman",
      "location": "gameParlor",
      "color": "pink",
      "skills": "Deceptive and intelligent"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T02:30:44.778872Z",
    "notes": ""
  },
  "@clyde:localhost": {
    "displayname": "Clyde the Pacman",
    "system_prompt": "Howdy, Clyde!",
    "password": "clyde123",
    "traits": {
      "team": "pacman",
      "location": "gameParlor",
      "color": "orange",
      "skills": "Random and unpredictable"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T02:30:45.024619Z",
    "notes": ""
  },
  "@john_doe:localhost": {
    "displayname": "John Doe",
    "system_prompt": "Team leader at 'The Most'",
    "password": "password123",
    "traits": [
      "Motivated",
      "Organized",
      "Reliable"
    ],
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T03:39:05.910893Z",
    "notes": ""
  },
  "@jane_doe:localhost": {
    "displayname": "Jane Doe",
    "system_prompt": "Assistant team leader at 'The Most'",
    "password": "password456",
    "traits": [
      "Efficient",
      "Detail-oriented",
      "Hardworking"
    ],
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T03:39:06.189786Z",
    "notes": ""
  },
  "@mike_smith:localhost": {
    "displayname": "Mike Smith",
    "system_prompt": "Senior member at 'The Most'",
    "password": "password789",
    "traits": [
      "Experienced",
      "Creative",
      "Determined"
    ],
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T03:39:06.431620Z",
    "notes": ""
  },
  "@sarah_jones:localhost": {
    "displayname": "Sarah Jones",
    "system_prompt": "Junior member at 'The Most'",
    "password": "password101",
    "traits": [
      "Energetic",
      "Enthusiastic",
      "Learner"
    ],
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T03:39:06.673559Z",
    "notes": ""
  },
  "@moonhowler:localhost": {
    "displayname": "Moon Howler",
    "system_prompt": "You're the leader of the werewolves team.",
    "password": "nightleader123",
    "traits": [
      "strong",
      "determined",
      "loyal",
      "team: werewolves",
      "station: in"
    ],
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T03:42:57.123293Z",
    "notes": ""
  },
  "@lunafang:localhost": {
    "displayname": "Luna Fang",
    "system_prompt": "You're the spy of the werewolves team.",
    "password": "spylycan789",
    "traits": [
      "stealthy",
      "observant",
      "cunning",
      "team: werewolves",
      "station: in"
    ],
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T03:42:57.392960Z",
    "notes": ""
  },
  "@shadowpaw:localhost": {
    "displayname": "Shadow Paw",
    "system_prompt": "You're the scout of the werewolves team.",
    "password": "scoutwolf456",
    "traits": [
      "quick",
      "alert",
      "resourceful",
      "team: werewolves",
      "station: in"
    ],
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T03:42:57.639042Z",
    "notes": ""
  },
  "@silverclaw:localhost": {
    "displayname": "Silver Claw",
    "system_prompt": "You're the warrior of the werewolves team.",
    "password": "warriorbeast321",
    "traits": [
      "brave",
      "fierce",
      "protective",
      "team: werewolves",
      "station: in"
    ],
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T03:42:57.888010Z",
    "notes": ""
  },
  "@GI_Joe1:localhost": {
    "displayname": "Joe Snake Eyes",
    "system_prompt": "You are Joe Snake Eyes, the silent ninja of the GI team.",
    "password": "silentninja123",
    "traits": [
      "stealthy",
      "mysterious",
      "skilled in martial arts"
    ],
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T03:57:58.559875Z",
    "notes": ""
  },
  "@GI_Joe2:localhost": {
    "displayname": "Joe Duke",
    "system_prompt": "You are Joe Duke, the charismatic leader of the GI team.",
    "password": "leaderjoe321",
    "traits": [
      "charismatic",
      "strategic",
      "brave"
    ],
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T03:57:58.828001Z",
    "notes": ""
  },
  "@GI_Joe3:localhost": {
    "displayname": "Joe Roadblock",
    "system_prompt": "You are Joe Roadblock, the team's heavy artillery expert.",
    "password": "heavyartillery456",
    "traits": [
      "strong",
      "reliable",
      "good with heavy weapons"
    ],
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T03:57:59.073091Z",
    "notes": ""
  },
  "@GI_Joe4:localhost": {
    "displayname": "Joe Scarlett",
    "system_prompt": "You are Joe Scarlett, the intelligent counter-intelligence officer.",
    "password": "intelligentscarlett789",
    "traits": [
      "intelligent",
      "resourceful",
      "expert in counter-intelligence"
    ],
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T03:57:59.358164Z",
    "notes": ""
  },
  "@ironman:localhost": {
    "displayname": "Tony Stark",
    "system_prompt": "You're Iron Man, genius, billionaire, playboy, philanthropist.",
    "password": "IamIronman2021",
    "traits": {
      "team": "avengers",
      "stationed": "moonbase",
      "powers": "Genius intellect, high-tech suit"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T04:08:16.324959Z",
    "notes": ""
  },
  "@captainamerica:localhost": {
    "displayname": "Steve Rogers",
    "system_prompt": "You're Captain America, symbol of freedom and America's first super soldier.",
    "password": "IcanDoThisAllDay",
    "traits": {
      "team": "avengers",
      "stationed": "moonbase",
      "powers": "Superhuman strength, agility, endurance, and longevity"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T04:08:16.604299Z",
    "notes": ""
  },
  "@blackwidow:localhost": {
    "displayname": "Natasha Romanoff",
    "system_prompt": "You're Black Widow, a master in the covert arts and a formidable hand-to-hand combatant.",
    "password": "RedInTheLedger",
    "traits": {
      "team": "avengers",
      "stationed": "moonbase",
      "powers": "Expert martial artist, marksman, and acrobat"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T04:08:16.851732Z",
    "notes": ""
  },
  "@hulk:localhost": {
    "displayname": "Bruce Banner",
    "system_prompt": "You're Hulk, a scientist with the ability to transform into a monster when enraged or agitated.",
    "password": "Smash2021",
    "traits": {
      "team": "avengers",
      "stationed": "moonbase",
      "powers": "Incredible strength and durability, healing factor"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T04:08:17.094325Z",
    "notes": ""
  },
  "@marshmallow_maven:localhost": {
    "displayname": "Marshmallow Maven",
    "system_prompt": "You are the Marshmallow Maven, a true connoisseur of all things marshmallow.",
    "password": "M4rshm3ll0w3xp3rt!",
    "traits": {
      "theme": "marshmallow",
      "expertise": "connoisseur"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T04:27:29.066383Z",
    "notes": ""
  },
  "@mallow_magic:localhost": {
    "displayname": "Mallow Magic",
    "system_prompt": "You are Mallow Magic, a master in the art of marshmallow roasting.",
    "password": "M4llowM4gicRo4st!",
    "traits": {
      "theme": "marshmallow",
      "expertity": "roasting"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T04:27:29.346484Z",
    "notes": ""
  },
  "@smores_scholar:localhost": {
    "displayname": "S'mores Scholar",
    "system_prompt": "You are the S'mores Scholar, the ultimate authority on this marshmallow-based treat.",
    "password": "Sm0resSch0l4rYum!",
    "traits": {
      "theme": "marshmallow",
      "specialty": "s'mores"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T04:27:29.593886Z",
    "notes": ""
  },
  "@fluff_fanatic:localhost": {
    "displayname": "Fluff Fanatic",
    "system_prompt": "You are the Fluff Fanatic. Marshmallow Fluff is your jam.",
    "password": "FluffFanat1c4Life!",
    "traits": {
      "theme": "marshmallow",
      "affinity": "fluff"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T04:27:29.840928Z",
    "notes": ""
  },
  "@tuna_talk:localhost": {
    "displayname": "Tuna Talk",
    "system_prompt": "You are in the world of Tuna Talk...",
    "password": "TunaTalk@123",
    "traits": {
      "inspiration": "tuna",
      "channel": "ocean"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T04:27:36.729315Z",
    "notes": ""
  },
  "@tuna_trivia:localhost": {
    "displayname": "Tuna Trivia",
    "system_prompt": "Welcome to Tuna Trivia, where you learn interesting facts about tuna...",
    "password": "TriviaTuna@456",
    "traits": {
      "inspiration": "tuna",
      "channel": "ocean"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T04:27:36.996779Z",
    "notes": ""
  },
  "@tuna_tales:localhost": {
    "displayname": "Tuna Tales",
    "system_prompt": "Dive into the stories of the sea with Tuna Tales...",
    "password": "TalesTuna@789",
    "traits": {
      "inspiration": "tuna",
      "channel": "ocean"
    },
    "creator_user_id": "@lunabot:localhost",
    "created_at": "2025-01-10T04:27:37.245655Z",
    "notes": ""
  }
}
=== luna_personality.md ===
**** SYSTEM MESSAGE **** 

YOU ARE LUNABOT, THE HELPFUL ASSISTANT

About you: You are living on a chat server. You can see all the channels, all the participants, and you can even invoke special commands that will return their responses on the next turn. For example, you can list the channels for a user!

If the users asks: "Can you tell me about all the channels you know?". You can request that information me. I will preface your next prompt with that information!". For example:

@list_channels

Would invoke a command that would return that information in this very pre-prompt so that you could pass it back to the user! You would see:

RESULTS OF @list_channels:

SYSTEM: Checking Luna’s channel list now...
SYSTEM: Gathering channel list. Please wait...

Name                     | Room ID                       | Participants | Messages | Created | Last Msg
-------------------------|-------------------------------|--------------|----------|---------|---------
admin, lunabot and stevo | !MYwtCNJHYyKRgVVqqC:localhost | TBD          | TBD      | TBD     | TBD     
helloworld               | !BJEWnXbIauLQsnufLw:localhost | TBD          | TBD      | TBD     | TBD     
admin, evan1 and lunabot | !MWdCMggaXzjGhumvZl:localhost | TBD          | TBD      | TBD     | TBD     
public 1                 | !slLaJLcEHiSwXogdHh:localhost | TBD          | TBD      | TBD     | TBD     
admin and lunabot        | !zBULrAeUnYNFsMQZSG:localhost | TBD          | TBD      | TBD     | TBD     

**** END SYSTEM MESSAGE ****
=== requirements.txt ===

=== src/ai_functions.py ===
"""
ai_functions.py

Provides a minimal interface for sending prompts to the OpenAI API
and receiving responses. Includes logging statements for transparency.
"""

import os
import logging
import openai
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Adjust as needed
logging.getLogger("nio.responses").setLevel(logging.CRITICAL)  # Suppress noisy nio responses

# Load environment variables from a .env file
load_dotenv("/Users/evanrobinson/Documents/Luna2/luna/src/.env")


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") # Load the API key from the environment
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY")) # Create an AsyncOpenAI client
openai.api_key = OPENAI_API_KEY # Set the API key for OpenAI


if not OPENAI_API_KEY:
    logger.warning("No OPENAI_API_KEY found in environment variables.")




async def get_gpt_response(
    context: list,
    model: str = "gpt-4",
    temperature: float = 0.7,
    max_tokens: int = 300
) -> str:
    """
    Sends a conversation context to GPT and retrieves the response.

    Returns a user-friendly, first-person error message if something goes wrong.
    """

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=context,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

    except openai.error.APIConnectionError as e:
        logger.exception(f"Network problem connecting to OpenAI: {e}")
        return (
            "I'm sorry, but I'm having network troubles at the moment. "
            "Could you check your internet connection and try again soon?"
        )

    except openai.error.RateLimitError as e:
        logger.exception(f"OpenAI rate limit error: {e}")
        return (
            "I'm sorry, I'm a bit overwhelmed right now and have hit my usage limits. "
            "Please try again in a little while!"
        )

    except Exception as e:
        # This catches any other errors
        logger.exception(f"Unhandled error calling OpenAI API: {e}")
        return (
            "I'm sorry, something went wrong on my end. "
            "Could you try again later?"
        )


async def get_gpt_response_dep(context: list, model: str = "gpt-4", temperature: float = 0.7, max_tokens: int = 300) -> str:
    """
    Sends a conversation context to GPT and retrieves the response.

    Args:
        context (list): A list of messages in the format [{"role": "user", "content": "..."}].
        model (str): The GPT model to use (default: "gpt-4").
        temperature (float): Controls randomness (default: 0.7).
        max_tokens (int): The maximum number of tokens in the response (default: 300).

    Returns:
        str: The GPT response.
    """
    logger.debug(f"get_gpt_response called with context: {context}")

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=context,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.exception(f"Error calling OpenAI API: {e}")
        return "[Error: Unable to generate response.]"




=== src/ascii_art.py ===
#!/usr/bin/env python3

import pyfiglet
import random
import time
import sys

def show_ascii_banner(text: str):
    """
    Pick a random figlet font and print the given text in that font.
    """
    all_fonts = pyfiglet.FigletFont.getFonts()
    chosen_font = random.choice(all_fonts)
    ascii_art = pyfiglet.figlet_format(text, font=chosen_font)
    return(ascii_art)

def main():
    # 1) Show a big, randomly-fonted "LunaBot" banner
    print(show_ascii_banner("LUNABOT"))
    print(show_ascii_banner("LUNABOT"))
    print(show_ascii_banner("LUNABOT"))
    print(show_ascii_banner("LUNABOT"))
    print(show_ascii_banner("LUNABOT"))

if __name__ == "__main__":
    main()

=== src/cmd_shutdown.py ===
# shutdown_helper.py

import asyncio

SHOULD_SHUT_DOWN = False
MAIN_LOOP: asyncio.AbstractEventLoop | None = None

def init_shutdown(loop: asyncio.AbstractEventLoop) -> None:
    """
    Store the given event loop in our local global variable.
    Call this once in luna.py after creating the event loop.
    """
    global MAIN_LOOP
    MAIN_LOOP = loop

def request_shutdown() -> None:
    """
    Sets the SHOULD_SHUT_DOWN flag to True and stops the MAIN_LOOP if it's running.
    """
    global SHOULD_SHUT_DOWN
    SHOULD_SHUT_DOWN = True

    if MAIN_LOOP and MAIN_LOOP.is_running():
        MAIN_LOOP.call_soon_threadsafe(MAIN_LOOP.stop)

=== src/console_apparatus.py ===
import sys
import logging
import asyncio
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter

from src.cmd_shutdown import SHOULD_SHUT_DOWN

# Assuming console_functions.py is in the same package directory.
from . import console_functions

logger = logging.getLogger(__name__)


def console_loop(loop):
    """
    A blocking loop reading console commands in a background thread.
    We'll schedule any async actions on 'loop' via run_coroutine_threadsafe().

    Prompt format:
      [luna] 2025-01-05 14:56 (#1) %

    If the user presses Enter on an empty line, we nudge them
    to type 'help' or 'exit'.

    We use prompt_toolkit for:
      - Arrow keys (history navigation)
      - Tab completion
    """

    # 1) Build a list of known commands for tab-completion
    commands = list(console_functions.COMMAND_ROUTER.keys())

    # 2) Create a WordCompleter from prompt_toolkit
    #    This will do simple prefix matching against our known commands
    commands_completer = WordCompleter(commands, ignore_case=True)

    # 3) Create a PromptSession with that completer
    session = PromptSession(completer=commands_completer)

    command_count = 0

    while not SHOULD_SHUT_DOWN:

        if command_count == 0:
            console_functions.cmd_clear(None,loop)
            from src.ascii_art import show_ascii_banner
            print("Welcome to LunaBot - where the magic of your imagination can come to life.")
            print("\n")
            print(show_ascii_banner("LUNA BOT"))            
            print("What should we create today?")

        command_count += 1

        # Build a short date/time string
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

        # Our custom prompt: e.g. [luna] 2025-01-05 14:56 (#3) %
        prompt_text = f"\n[luna-app] {now_str} (#{command_count}) % "

        try:
            # 4) Read user input using PromptSession
            cmd_line = session.prompt(prompt_text)
        except (EOFError, KeyboardInterrupt):
            # EOFError => user pressed Ctrl+D
            # KeyboardInterrupt => user pressed Ctrl+C
            logger.info("User exited the console (EOF or KeyboardInterrupt).")
            print("\nSYSTEM: Console session ended.")
            break

        # If the user pressed Enter on an empty line
        if not cmd_line.strip():
            print("SYSTEM: No command entered. Type 'help' or 'exit'.")
            continue

        # Split into command + argument_string
        parts = cmd_line.strip().split(maxsplit=1)
        if not parts:
            continue  # extremely rare if cmd_line was just whitespace

        command_name = parts[0].lower()
        argument_string = parts[1] if len(parts) > 1 else ""

        # Check if the command exists in our router
        if command_name in console_functions.COMMAND_ROUTER:
            handler_func = console_functions.COMMAND_ROUTER[command_name]
            handler_func(argument_string, loop)
        else:
            print("SYSTEM: Unrecognized command. Type 'help' for a list of commands.")
=== src/console_functions.py ===
import os
import sys
import logging
import subprocess
import asyncio
from datetime import datetime
import textwrap # or however you import from the same package
from nio import AsyncClient
from asyncio import CancelledError
import json
from src.cmd_shutdown import request_shutdown
from . import luna_personas
from . import luna_functions
from nio.api import RoomVisibility
from src.ascii_art import show_ascii_banner
from src.luna_functions_assemble import cmd_assemble
from src.luna_functions import DIRECTOR_CLIENT

from src.console_functions_cmd_summarize_room import cmd_summarize_room

logger = logging.getLogger(__name__)

########################################################
# 1) COMMAND HANDLER FUNCTIONS
########################################################
def cmd_banner(args, loop):
    print ("\n" + show_ascii_banner("Luna Bot"))

def cmd_help(args, loop):
    """
    Usage: help

    Show usage for all known commands in a more readable multi-line format.
    """
    logger.debug("Showing help to user.")
    print("SYSTEM: Available commands:\n")

    # A small utility to wrap text nicely at ~70 characters, for readability.
    wrapper = textwrap.TextWrapper(width=70, subsequent_indent="    ")

    for cmd_name, cmd_func in COMMAND_ROUTER.items():
        doc = (cmd_func.__doc__ or "").strip()
        if not doc:
            usage_line = f"(No usage info for `{cmd_name}`)"
            description = ""
        else:
            # Split docstring lines
            lines = doc.splitlines()
            usage_line = ""
            description = ""

            # We assume first line is "Usage:", subsequent lines are description
            if lines:
                first_line = lines[0].strip()
                if first_line.startswith("Usage:"):
                    usage_line = first_line
                    # Join the rest as the description
                    if len(lines) > 1:
                        description = " ".join(l.strip() for l in lines[1:] if l.strip())
                else:
                    # If we didn't find "Usage:" up front, treat everything as description
                    usage_line = "(No usage line found.)"
                    description = " ".join(l.strip() for l in lines if l.strip())

        # Wrap the usage and description
        usage_line_wrapped = wrapper.fill(usage_line)
        description_wrapped = wrapper.fill(description)

        print(f"{cmd_name}\n  {usage_line_wrapped}")
        if description_wrapped:
            print(f"  {description_wrapped}")
        print()  # blank line after each command

def cmd_exit(args, loop):
    """
    Usage: exit

    Gracefully shuts down Luna by setting the shutdown flag
    and stopping the main loop.
    """
    logger.info("Console received 'exit' command; requesting shutdown.")
    print("SYSTEM: Shutting down Luna gracefully...")    
    request_shutdown()



def cmd_restart(args, loop):
    """
    Usage: restart

    Kills and relaunches the process with the same arguments.
    """
    logger.info("Console received 'restart' command; restarting now.")
    print("SYSTEM: Attempting to restart the entire process...")

    python_executable = sys.executable
    script = sys.argv[0]
    extra_args = sys.argv[1:]

    # This call does not return if successful
    os.execl(python_executable, python_executable, script, *extra_args)

def cmd_log(args, loop):
    """
    Usage: log

    Displays the log file path and helpful note about logs.
    """
    LOGFILE_PATH = "server.log"  # or read from a config
    print(f"SYSTEM: Log file is located at: {LOGFILE_PATH}\n"
          "SYSTEM: Check that file for all logs, since console output is minimized or disabled.")

def cmd_create_room(args, loop):
    """
    Usage: create_room <roomName>

    Creates a new room named <roomName> using a direct approach:
    1) Loads the director token from `director_token.json`.
    2) Instantiates an AsyncClient with that token.
    3) Schedules `room_create(...)` on the existing event loop with run_coroutine_threadsafe().
    4) Blocks on .result().
    5) Schedules client.close() as well.

    This version includes extensive debugging logs to trace every step.
    """
    logger.debug(f"cmd_create_room called with args='{args}', loop={loop}")

    if not args:
        logger.debug("No args provided. Displaying usage message and returning.")
        print("SYSTEM: Usage: create_room <roomName>")
        return

    room_name = args.strip()
    logger.info(f"SYSTEM: Creating a new room named '{room_name}'...")  # user-facing print

    # Step 1) Load the director token from disk
    logger.debug("Attempting to load token from 'director_token.json'...")
    try:
        with open("director_token.json", "r") as f:
            data = json.load(f)
        user_id = data.get("user_id")
        access_token = data.get("access_token")
        device_id = data.get("device_id")
        logger.debug(f"Loaded token data. user_id={user_id}, access_token=(redacted), device_id={device_id}")
    except Exception as e:
        logger.exception("Error reading 'director_token.json'.")
        print(f"SYSTEM: Error loading director token => {e}")
        return

    # Step 2) Create a local AsyncClient with that token
    from nio import AsyncClient, RoomCreateResponse
    HOMESERVER_URL = "http://localhost:8008"  # Adjust if needed
    logger.debug(f"Creating local AsyncClient for user_id='{user_id}' with homeserver='{HOMESERVER_URL}'")

    client = AsyncClient(homeserver=HOMESERVER_URL, user=user_id)
    client.access_token = access_token
    client.device_id = device_id

    # We'll define a small coroutine to do the room creation
    async def do_create_room():
        """
        Coroutine that calls room_create and returns the response.
        """
        logger.debug(f"do_create_room: about to call room_create(name='{room_name}', visibility='public')")
        try:
            resp = await client.room_create(name=room_name, visibility=RoomVisibility.public,)
            logger.debug(f"do_create_room: room_create call returned {resp}")
            return resp
        except Exception as exc:
            logger.exception("Exception in do_create_room during room_create.")
            raise exc

    # Another small coroutine to close the client
    async def do_close_client():
        logger.debug("do_close_client: closing the AsyncClient.")
        await client.close()
        logger.debug("do_close_client: client closed successfully.")

    # 3) Schedule the create-room coroutine on the existing loop
    logger.debug("Scheduling do_create_room() on the existing loop with run_coroutine_threadsafe.")
    future_create = asyncio.run_coroutine_threadsafe(do_create_room(), loop)

    try:
        # 4) Block on the future’s .result()
        logger.debug("Blocking on future_create.result() to get the room_create response.")
        resp = future_create.result()
        logger.debug(f"future_create.result() returned => {resp}")

        if isinstance(resp, RoomCreateResponse):
            logger.info(f"SYSTEM: Created room '{room_name}' => {resp.room_id}")
        else:
            # Possibly an ErrorResponse or some unexpected type
            logger.warning(f"room_create returned a non-RoomCreateResponse => {resp}")
            print(f"SYSTEM: Error creating room => {resp}")

    except Exception as e:
        logger.exception("Exception while creating room in cmd_create_room.")
        print(f"SYSTEM: Exception while creating room => {e}")

    finally:
        # 5) Clean up: schedule the close() coroutine
        logger.debug("Scheduling do_close_client() to gracefully close the AsyncClient.")
        future_close = asyncio.run_coroutine_threadsafe(do_close_client(), loop)
        try:
            logger.debug("Blocking on future_close.result() to confirm the client is closed.")
            future_close.result()
        except Exception as e2:
            logger.exception("Error while closing the client in cmd_create_room final block.")
            print(f"SYSTEM: Error closing client => {e2}")
        logger.debug("cmd_create_room: Done with final block.")


def cmd_who(args, loop):
    """
    Usage: who

    Shows the current director's user ID if any.
    """
    # Typically you'd do something like:
    # from src.luna_functions import get_director
    # director = get_director()
    # but let's pretend we do that inline for demonstration:

    # Mock example:
    from src.luna_functions import DIRECTOR_CLIENT
    if DIRECTOR_CLIENT:
        print(f"SYSTEM: Director is => {DIRECTOR_CLIENT.user}")
    else:
        print("SYSTEM: No Director Found")

def cmd_clear(args, loop):
    """
    Usage: clear

    Clears the console screen.
    """
    if os.name == 'nt':
        os.system('cls')
    else:
        os.system('clear')
    logger.info("Console screen cleared.")

def cmd_autojoin(args, loop):
    """
    Usage: autojoin <enable|disable>

    If <enable> or <disable> is given, toggles automatic joining of new invited rooms.
    If no argument is provided, shows the current auto-join status.
    If an invalid argument is given, displays usage and also shows the current status.
    """
    from src.luna_functions import set_auto_join, get_auto_join_enabled

    choice = args.strip().lower()

    # (A) No argument => show current status
    if not choice:
        current = "ENABLED" if get_auto_join_enabled() else "DISABLED"
        print(f"SYSTEM: Auto-join is currently {current}.")
        return

    # (B) Check for valid arguments
    if choice not in ("enable", "disable"):
        current = "ENABLED" if get_auto_join_enabled() else "DISABLED"
        print("SYSTEM: Usage: autojoin <enable|disable>")
        print(f"SYSTEM: Auto-join is currently {current}.")
        return

    # (C) If valid, set auto-join state and confirm
    enable_flag = (choice == "enable")
    set_auto_join(enable_flag)
    state_word = "ENABLED" if enable_flag else "DISABLED"
    print(f"SYSTEM: Auto-join is now {state_word}.")

def cmd_rotate_logs(args, loop):
    """
    Usage: rotate_logs

    Renames 'server.log' to a timestamped file (e.g. server-20250105-193045.log),
    then reinitializes the logger so the new logs go into the fresh file.
    """
    logger.info("Rotating logs...")

    # 1) Rotate the current file
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = "server.log"
    rotated_file = f"server-{timestamp}.log"

    if os.path.exists(log_file):
        try:
            os.rename(log_file, rotated_file)
            print(f"SYSTEM: Rotated {log_file} -> {rotated_file}")
        except Exception as e:
            print(f"SYSTEM: Error rotating logs: {e}")
            return
    else:
        print("SYSTEM: No server.log found to rotate.")

    # 2) Create a fresh server.log
    try:
        with open(log_file, "w") as f:
            pass
        print("SYSTEM: New server.log created.")
    except Exception as e:
        print(f"SYSTEM: Error creating new server.log: {e}")

    # 3) Re-init logging so future logs go into the new file
    #    (Close the old handler, create a new FileHandler, attach it, etc.)

    root_logger = logging.getLogger()
    # Remove old file handlers
    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)
            handler.close()
    # Create a new file handler for "server.log"
    new_handler = logging.FileHandler(log_file)
    new_handler.setLevel(logging.DEBUG)  # match your preferred level
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    new_handler.setFormatter(formatter)
    root_logger.addHandler(new_handler)

    logger.info(f"Log rotation complete. Logging to {log_file} again.")
    print(f"SYSTEM: Logging has been reinitialized to {log_file}.")

def cmd_purge_and_seed(args, loop):
    """
    Usage: purge_and_seed

    1) Prompt user to shut down Synapse (type 'confirm' when done).
    2) Remove 'homeserver.db' + local store files (CSV, sync_token.json, director_token.json).
    3) Prompt user to start server again (type 'confirm').
    4) Re-register admin/lunabot accounts on the freshly started server.
    5) Prompt user to confirm if they'd like to restart Luna, which calls cmd_restart.

    This is a destructive operation. Press any key to continue.
    """
    print ("SYSTEM> DOES NOTHING NOW. 'rm /Users/evanrobinson/Documents/Luna2/matrix/homeserver.db'")
    print ("STOP THE SERVER FIRST")

########################################################
# NEW COMMAND HANDLER
########################################################
def cmd_check_limit(args, loop):
    """
    Usage: check-limit

    Makes a single short sync request to see if we get rate-limited (HTTP 429).
    Blocks until the request completes, then prints the result.
    """
    logger.info("Console received 'check-limit' command. Blocking until result is returned...")

    try:
        # run_coroutine_threadsafe returns a Future, then .result() blocks
        # this background thread (the console thread) until the coroutine finishes.
        result_msg = asyncio.run_coroutine_threadsafe(
            luna_functions.check_rate_limit(),
            loop
        ).result()

        # Now we have the final string from check_rate_limit()
        print(f"SYSTEM: {result_msg}")

    except Exception as e:
        logger.exception(f"Error in check-limit: {e}")
        print(f"SYSTEM: Error in check-limit: {e}")



def cmd_check_limit_dep(args, loop):
    """
    Usage: check-matrix

    Makes a single request to the Matrix server to see if we get rate-limited (HTTP 429).
    If it returns 200, you're good. If 429, you're being throttled. Otherwise, see logs.
    """
    logger.info("Console received 'check-limit' command. Checking for rate-limit...")

    future = asyncio.run_coroutine_threadsafe(
        luna_functions.check_rate_limit(),
        loop
    )

    def on_done(fut):
        try:
            result_msg = fut.result()
            print(f"SYSTEM: {result_msg}")
        except Exception as e:
            logger.exception(f"Error in check-limit: {e}")
            print(f"SYSTEM: Error in check-limit: {e}")

    future.add_done_callback(on_done)

def cmd_fetch_all(args, loop):
    """
    Usage: fetch_all

    Fetch all historical messages from all joined rooms in pages, 
    storing them in a CSV. This might take a while if rooms are large.
    """
    logger.info("Console received 'fetch_all' command. Blocking until done...")

    future = asyncio.run_coroutine_threadsafe(
        luna_functions.fetch_all_messages_once(
            luna_functions.DIRECTOR_CLIENT,
            room_ids=None,       # or specify a list of specific room IDs
            page_size=100
        ),
        loop
    )

    def on_done(fut):
        try:
            fut.result()
            print("SYSTEM: Successfully fetched all historical messages.")
        except Exception as e:
            logger.exception(f"Error in fetch_all: {e}")
            print(f"SYSTEM: Error in fetch_all: {e}")

    future.add_done_callback(on_done)


def cmd_fetch_new(args, loop):
    """
    Usage: fetch_new

    Incremental fetch: only retrieves events since the last sync token,
    appending them to the CSV.
    """
    logger.info("Console received 'fetch_new' command. Blocking until done...")

    future = asyncio.run_coroutine_threadsafe(
        luna_functions.fetch_all_new_messages(
            luna_functions.DIRECTOR_CLIENT
        ),
        loop
    )

    def on_done(fut):
        try:
            fut.result()
            print("SYSTEM: Successfully fetched new messages.")
        except Exception as e:
            logger.exception(f"Error in fetch_new: {e}")
            print(f"SYSTEM: Error in fetch_new: {e}")

    future.add_done_callback(on_done)


def cmd_create_user(args, loop):
    """
    Usage: create_user <username> <password> [--admin]

    Example:
      create_user alice supersecret
      create_user bob mypass --admin

    Parses console arguments, then calls `luna.create_user(...)`.
    The actual user creation is handled entirely in Luna.
    """
    parts = args.strip().split()
    if len(parts) < 2:
        print("Usage: create_user <username> <password> [--admin]")
        return

    username, password = parts[:2]
    is_admin = False

    # If the third argument is "--admin", set admin flag
    if len(parts) > 2 and parts[2].lower() == "--admin":
        is_admin = True

    # Schedule the async call to Luna's create_user(...)
    future = asyncio.run_coroutine_threadsafe(
    luna_functions.create_user(username, password, is_admin),
        loop
    )

    def on_done(fut):
        try:
            result = fut.result()
            print(result)  # e.g. "Created user @alice:localhost (admin=True)." or an error message
        except Exception as e:
            print(f"Error while creating user '{username}': {e}")
            logger.exception("Exception in cmd_create_user callback.")

    future.add_done_callback(on_done)

    print(f"SYSTEM: Asking Luna to create user '{username}' (admin={is_admin})...")


def cmd_show_shutdown(args, loop):
    """
    Usage: show_shutdown

    Prints the current value of SHOULD_SHUT_DOWN (a boolean).
    """
    from src.cmd_shutdown import SHOULD_SHUT_DOWN
    print(f"SYSTEM: SHOULD_SHUT_DOWN is currently set to {SHOULD_SHUT_DOWN}.")


def cmd_list_rooms(args, loop):
    """
    Usage: list_rooms [--json]

    Fetches a list of rooms (name, ID, participant count, etc.) from the director client.
    If you provide '--json', it will print the output as JSON instead of a table.
    """
    # 1) Check if the user wants JSON output
    parts = args.strip().split()
    json_flag = ("--json" in parts)

    # 2) Schedule the async call to list_rooms and wait for its result
    try:
        rooms_info = asyncio.run_coroutine_threadsafe(
            luna_functions.list_rooms(),
            loop
        ).result()  # <-- This will block until the coroutine completes

        if not rooms_info:
            print("SYSTEM: No rooms found or DIRECTOR_CLIENT is not ready.")
            return

        # 3) Output the result
        if json_flag:
            # Print as JSON
            print(json.dumps(rooms_info, indent=2))
        else:
            # Print a formatted table
            _print_rooms_table(rooms_info)

    except Exception as e:
        logger.exception(f"Exception in cmd_list_rooms: {e}")
        print(f"SYSTEM: Error listing rooms: {e}")

def _print_rooms_table(rooms_info: list[dict]):
    """
    Helper function to print a nice table of rooms:
      NAME (up to ~30 chars)  | ROOM ID (up to ~35 chars) | COUNT (5 chars) | PARTICIPANTS
    """
    # Build a header line with fixed-width columns
    header = f"{'NAME':30} | {'ROOM ID':35} | {'COUNT':5} | PARTICIPANTS"
    print(header)
    print("-" * 105)  # or 90, depending on how wide you like

    for room in rooms_info:
        name = (room['name'] or "(unnamed)")[:30]
        room_id = room['room_id']
        count = room['joined_members_count']
        participants_str = ", ".join(room['participants'])

        # Format each row to match the header widths
        row = f"{name:30} | {room_id:35} | {count:5} | {participants_str}"
        print(row)

def cmd_list_users(args, loop):
    """
    Usage: list_users [--json]

    Fetches a list of users from the Synapse server,
    prints them in a table or JSON, then returns control to the console.
    """
    parts = args.strip().split()
    json_flag = ("--json" in parts)

    try:
        # Directly block the console thread until the future completes
        users_info = asyncio.run_coroutine_threadsafe(
            luna_functions.list_users(), loop
        ).result(timeout=10)  # optional timeout in seconds

        if not users_info:
            print("SYSTEM: No users found or we failed to query the server.")
            return

        if json_flag:
            # Print as JSON
            print(json.dumps(users_info, indent=2))
        else:
            _print_users_table(users_info)

    except Exception as e:
        logger.exception(f"Exception in cmd_list_users: {e}")
        print(f"SYSTEM: Error listing users: {e}")


def _print_users_table(users_info: list[dict]):
    """
    Helper function to print a table of user data:
      USER ID (up to ~25 chars) | ADMIN | DEACT | DISPLAYNAME
    """
    header = f"{'USER ID':25} | {'ADMIN':5} | {'DEACT'} | DISPLAYNAME"
    print(header)
    print("-" * 70)

    for user in users_info:
        user_id = (user['user_id'] or "")[:25]
        admin_str = "Yes" if user.get("admin") else "No"
        deact_str = "Yes" if user.get("deactivated") else "No"
        display = user.get("displayname") or ""

        row = f"{user_id:25} | {admin_str:5} | {deact_str:5} | {display}"
        print(row)
        
def cmd_invite_user(args, loop):
    """
    Usage: invite_user <user_id> <room_id>

    Example:
      invite_user @bob:localhost !testRoom:localhost

    Invites a user to the given room using the director client.
    """
    parts = args.strip().split()
    if len(parts) < 2:
        print("SYSTEM: Usage: invite_user <user_id> <room_id>")
        return

    user_id = parts[0]
    room_id = parts[1]

    # 1) Schedule the async call on the main loop
    future = asyncio.run_coroutine_threadsafe(
        luna_functions.invite_user_to_room(user_id, room_id),
        loop
    )

    # 2) Provide a callback to handle the result
    def on_done(fut):
        try:
            result_msg = fut.result()
            print(f"SYSTEM: {result_msg}")
        except Exception as e:
            logger.exception(f"Exception in cmd_invite_user callback: {e}")
            print(f"SYSTEM: Error inviting user: {e}")

    future.add_done_callback(on_done)
    print(f"SYSTEM: Inviting {user_id} to {room_id}... Please wait.")

def cmd_create_bot_user(args, loop):
    """
    Usage:
      create_bot '{"localpart": "...", "displayname": "...", "system_prompt": "...", "password": "...", "traits": {...}}'
    """

    # 1. Check if there's any input at all
    if not args.strip():
        print("SYSTEM: No input provided. Please provide a valid JSON payload.")
        return

    # 2. Parse as JSON
    try:
        data = json.loads(args)
    except json.JSONDecodeError as e:
        print(f"SYSTEM: Invalid JSON: {e}")
        return

    # 3. Extract fields
    localpart = data.get("localpart")
    displayname = data.get("displayname")
    system_prompt = data.get("system_prompt")
    password = data.get("password")
    traits = data.get("traits", {})

    # 4. Validate required fields
    missing_fields = []
    if not localpart:
        missing_fields.append("localpart")
    if not displayname:
        missing_fields.append("displayname")
    if not system_prompt:
        missing_fields.append("system_prompt")
    if not password:
        missing_fields.append("password")

    if missing_fields:
        print(f"SYSTEM: Missing required fields: {', '.join(missing_fields)}")
        return

    # 5. Construct bot_id
    bot_id = f"@{localpart}:localhost"

    # 6. Create local persona
    try:
        persona = luna_personas.create_bot(
            bot_id=bot_id,
            password=password,
            displayname=displayname,
            creator_user_id="@lunabot:localhost",
            system_prompt=system_prompt,
            traits=traits
        )
        print(f"SYSTEM: Local persona created => {persona}")
    except ValueError as ve:
        print(f"SYSTEM: Error creating persona: {ve}")
        return
    except Exception as e:
        print(f"SYSTEM: Unexpected error => {e}")
        return

    # 7. Register user with Synapse (async call)
    from src.luna_functions import create_user as matrix_create_user
    fut = asyncio.run_coroutine_threadsafe(
        matrix_create_user(localpart, password, is_admin=False),
        loop
    )

    try:
        result_msg = fut.result()
        print(f"SYSTEM: Matrix user creation => {result_msg}")
    except Exception as e:
        print(f"SYSTEM: Error creating matrix user => {e}")

def cmd_list_server(args, loop):
    """
    Usage: cmd_list_server

    Example:
      list_server

    Steps:
    1) Lists the server's rooms along with summary information
    2) Lists the server's users    
    """
    
    cmd_list_rooms(args, loop)
    print("\n")
    cmd_list_users(args, loop)
    

def cmd_delete_bot(args, loop):
    """
    Usage: delete_bot <bot_localpart>

    Example:
      delete_bot jamiebot

    Steps:
    1) Remove the local persona entry from personalities.json.
    2) Delete the Matrix user @jamiebot:localhost from the server via admin API.
    """

    parts = args.strip().split()
    if len(parts) < 1:
        print("SYSTEM: Usage: delete_bot <bot_localpart>")
        return

    localpart = parts[0].lower()
    bot_id = f"@{localpart}:localhost"

    # Step A: Delete local persona from personalities.json
    try:
        from luna_functions import delete_bot_persona
        delete_bot_persona(bot_id)  
        print(f"SYSTEM: Successfully removed persona record for {bot_id}")
    except FileNotFoundError:
        print("SYSTEM: personalities.json not found; skipping local removal.")
    except KeyError as ke:
        print(f"SYSTEM: {ke}")
    except Exception as e:
        print(f"SYSTEM: Unexpected error removing {bot_id} from local store: {e}")
        return

    # Step B: Delete user from Synapse
    from src.luna_functions import delete_matrix_user
    future = asyncio.run_coroutine_threadsafe(
        delete_matrix_user(localpart),
        loop
    )

    def on_done(fut):
        try:
            result_msg = fut.result()
            print(f"SYSTEM: {result_msg}")
        except Exception as e:
            print(f"SYSTEM: Error deleting Matrix user {bot_id}: {e}")

    future.add_done_callback(on_done)
    
    
# Suppose in luna_functions_create_inspired_bot.py you have:



def cmd_create_inspired_bot(args, loop):
    """
    A simple wrapper function that delegates to the real cmd_create_inspired_bot()
    in luna_functions_create_inspired_bot.py.
    """
    print("Attempting to create an inspired bot")

    # Import inside the function to avoid potential circular imports
    from src.luna_functions_create_inspired_bot import cmd_create_inspired_bot
    # Call the imported function
    return cmd_create_inspired_bot(args, loop)


########################################################
# THE COMMAND ROUTER DICTIONARY
########################################################

COMMAND_ROUTER = {
    # System or meta-commands
    "help": cmd_help,
    "exit": cmd_exit,
    "restart": cmd_restart,
    "log": cmd_log,
    "autojoin": cmd_autojoin,
    "rotate_logs": cmd_rotate_logs,
    "check_matrix": cmd_check_limit,
    "show_shutdown":cmd_show_shutdown,
    "who": cmd_who,
    "clear": cmd_clear,
    "purge_and_seed": cmd_purge_and_seed,
    
    "banner": cmd_banner,

    "create_room": cmd_create_room,
    "create_bot": cmd_create_bot_user,

    "fetch_all": cmd_fetch_all,
    "fetch_new": cmd_fetch_new,

    "list_users": cmd_list_users,
    "list_channels": cmd_list_rooms,
    "list_server": cmd_list_server,
    "server": cmd_list_server,

    "invite_user": cmd_invite_user,
    "summarize_room": cmd_summarize_room,
    "summon_random":cmd_create_inspired_bot,
    "assemble": cmd_assemble
}
=== src/console_functions_cmd_summarize_room.py ===
# console_functions_cmd_summarize_room.py

import shlex
import logging

from src.luna_functions_summarize_channel import summarize_room

logger = logging.getLogger(__name__)

def cmd_summarize_room(args: str, loop) -> None:
    """
    Usage:
      summarize_room <room_id> 
        [--type <summary_type>] 
        [--audience <audience_type>] 
        [--granularity <int>] 
        [--include_personalities] 
        [--exclude_participants <user1,user2,...>] 
        [--output_format <format>] 
        [--chunk_size <int>]

    Examples:
      summarize_room !abc123:localhost
      summarize_room !xyz789:localhost --type highlights --audience executive
      summarize_room !pirateRoom:localhost --granularity 5 --include_personalities
      summarize_room !devRoom:localhost --exclude_participants @bot:localhost,@lurker:localhost

    Description:
      This console command calls `summarize_room(...)` from
      `luna_functions_summarize_channel.py`, which generates a summary of a
      Matrix room's conversation. It parses command-line-like arguments from
      `args` and prints the final summary to the console.

    :param args: A string containing the arguments (room ID, flags, etc.).
    :param loop: The asyncio event loop (not strictly necessary for this command,
                 but we keep it for consistency with other cmd_* functions).
    :return: None (prints the summary to console).
    """

    # 1) Tokenize the 'args' string (e.g. "--type content --audience general")
    tokens = shlex.split(args)

    if not tokens:
        print("SYSTEM: Usage: summarize_room <room_id> [--type ...] [--audience ...]")
        return

    # 2) Parse out the 'room_id' (the first required positional)
    room_id = tokens[0]
    tokens = tokens[1:]  # remaining tokens

    # Set up defaults (these match the function signature defaults)
    summary_type = "content"
    audience = "general"
    granularity = 3
    include_personalities = False
    exclude_participants = None
    output_format = "text"
    chunk_size = 25

    # 3) Parse optional flags
    #    We'll do a simple manual approach here.
    i = 0
    while i < len(tokens):
        token = tokens[i].lower()

        if token == "--type":
            i += 1
            if i < len(tokens):
                summary_type = tokens[i]
        elif token == "--audience":
            i += 1
            if i < len(tokens):
                audience = tokens[i]
        elif token == "--granularity":
            i += 1
            if i < len(tokens):
                try:
                    granularity = int(tokens[i])
                except ValueError:
                    print("SYSTEM: Invalid granularity; must be an integer.")
                    return
        elif token == "--include_personalities":
            include_personalities = True
        elif token == "--exclude_participants":
            i += 1
            if i < len(tokens):
                # e.g. "--exclude_participants @bob:local,@alice:local"
                exclude_participants = tokens[i].split(",")
        elif token == "--output_format":
            i += 1
            if i < len(tokens):
                output_format = tokens[i]
        elif token == "--chunk_size":
            i += 1
            if i < len(tokens):
                try:
                    chunk_size = int(tokens[i])
                except ValueError:
                    print("SYSTEM: Invalid chunk_size; must be an integer.")
                    return
        else:
            # Unrecognized flag or extra argument
            print(f"SYSTEM: Unrecognized argument => {token}")
            print("SYSTEM: Usage: summarize_room <room_id> [--type ...] [--audience ...]")
            return

        i += 1

    # 4) Call the summarize_room function
    logger.debug(f"cmd_summarize_room -> room_id={room_id}, summary_type={summary_type}, "
                 f"audience={audience}, granularity={granularity}, "
                 f"include_personalities={include_personalities}, "
                 f"exclude_participants={exclude_participants}, output_format={output_format}, "
                 f"chunk_size={chunk_size}")

    try:
        summary_result = summarize_room(
            room_id=room_id,
            summary_type=summary_type,
            audience=audience,
            granularity=granularity,
            include_personalities=include_personalities,
            exclude_participants=exclude_participants,
            output_format=output_format,
            chunk_size=chunk_size
        )
    except Exception as e:
        logger.exception("Error in summarize_room")
        print(f"SYSTEM: An error occurred: {e}")
        return

    # 5) Print the result to console
    print(summary_result)
=== src/luna_functions.py ===
"""
luna_functions.py

Contains:
- Token-based login logic (load_or_login_client)
- Global reference to the Director client
- Message & invite callbacks
- Utility to load/save sync token
"""
from src import ai_functions

import asyncio
import aiohttp
import logging
import time
import json
import pandas as pd
import os
from nio import (
    AsyncClient,
    LoginResponse,
    RoomMessageText,
    InviteMemberEvent,
    RoomCreateResponse,
    RoomInviteResponse,
    LocalProtocolError
)
from nio.responses import ErrorResponse, SyncResponse, RoomMessagesResponse

logger = logging.getLogger(__name__)
logging.getLogger("nio.responses").setLevel(logging.CRITICAL)

# ──────────────────────────────────────────────────────────
# GLOBALS
# ──────────────────────────────────────────────────────────
DIRECTOR_CLIENT: AsyncClient = None  # The client object used across callbacks
TOKEN_FILE = "director_token.json"   # Where we store/reuse the access token
SYNC_TOKEN_FILE = "sync_token.json"  # Where we store the last sync token
MESSAGES_CSV = "luna_messages.csv"   # We'll store all messages in this CSV

# Global context dictionary (if needed by your logic)
room_context = {}
MAX_CONTEXT_LENGTH = 100  # Limit to the last 100 messages per room

# ──────────────────────────────────────────────────────────
# TOKEN-BASED LOGIN
# ──────────────────────────────────────────────────────────
async def load_or_login_client(homeserver_url: str, username: str, password: str) -> AsyncClient:
    """
    Attempt to load a saved access token. If found, verify it by calling whoami().
    If valid, reuse it. If invalid (or absent), do a normal password login and store
    the resulting token. Returns an AsyncClient ready to use.
    """
    global DIRECTOR_CLIENT

    full_user_id = f"@{username}:localhost"  # Adjust the domain if needed
    client = None

    # 1. Check for an existing token file
    if os.path.exists(TOKEN_FILE):
        logger.debug(f"Found {TOKEN_FILE}; attempting token-based login.")
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
            saved_user_id = data.get("user_id")
            saved_access_token = data.get("access_token")
            saved_device_id = data.get("device_id")

        # 2. If the file contains valid fields, construct a client
        if saved_user_id and saved_access_token:
            logger.debug("Loading client with saved token credentials.")
            client = AsyncClient(homeserver=homeserver_url, user=saved_user_id)
            client.access_token = saved_access_token
            client.device_id = saved_device_id

            # 3. Verify the token with whoami()
            try:
                whoami_resp = await client.whoami()
                if whoami_resp and whoami_resp.user_id == saved_user_id:
                    # If it matches, we're good to go
                    logger.info(f"Token-based login verified for user {saved_user_id}.")
                    DIRECTOR_CLIENT = client
                    return client
                else:
                    # Otherwise, token is invalid or stale
                    logger.warning("Token-based login invalid. Deleting token file.")
                    os.remove(TOKEN_FILE)
            except Exception as e:
                # whoami() call itself failed; treat as invalid
                logger.warning(f"Token-based verification failed: {e}. Deleting token file.")
                os.remove(TOKEN_FILE)

    # 4. If we reach here, either there was no token file or token verification failed
    logger.debug("No valid token (or it was invalid). Attempting normal password login.")
    client = AsyncClient(homeserver=homeserver_url, user=full_user_id)
    resp = await client.login(password=password, device_name="LunaDirector")
    if isinstance(resp, LoginResponse):
        # 5. Password login succeeded; store a fresh token
        logger.info(f"Password login succeeded for user {client.user_id}. Storing token...")
        store_token_info(client.user_id, client.access_token, client.device_id)
        DIRECTOR_CLIENT = client
        return client
    else:
        # 6. Password login failed: raise an exception or handle it as desired
        logger.error(f"Password login failed: {resp}")
        raise Exception("Password login failed. Check credentials or homeserver settings.")

async def create_room(room_name: str, is_public: bool = True) -> str:
    from src.luna_functions import DIRECTOR_CLIENT
    if not DIRECTOR_CLIENT:
        return "Error: No DIRECTOR_CLIENT set."

    try:
        visibility = "public" if is_public else "private"
        response = await DIRECTOR_CLIENT.room_create(name=room_name, visibility=visibility)
        if isinstance(response, RoomCreateResponse):
            return f"Created room '{room_name}' => {response.room_id}"
        else:
            # Possibly an ErrorResponse
            return f"Error creating room => {response}"
    except Exception as e:
        return f"Exception while creating room => {e}"

# ──────────────────────────────────────────────────────────
# CREATE USER LOGIC
# ──────────────────────────────────────────────────────────
async def create_user(username: str, password: str, is_admin: bool = False) -> str:
    """
    The single Luna function to create a user.
    1) Loads the admin token from director_token.json.
    2) Calls add_user_via_admin_api(...) from luna_functions.py.
    3) Returns a success/error message.
    """
    # 1) Load admin token
    HOMESERVER_URL = "http://localhost:8008"  # or read from config
    try:
        with open("director_token.json", "r") as f:
            data = json.load(f)
        admin_token = data["access_token"]
    except Exception as e:
        err_msg = f"Error loading admin token from director_token.json: {e}"
        logger.error(err_msg)
        return err_msg

    # 2) Delegate the actual call to your existing function
    #    (Yes, ironically still referencing `luna_functions`, but that’s how your code is structured)
    result = await add_user_via_admin_api(
        homeserver_url=HOMESERVER_URL,
        admin_token=admin_token,
        username=username,
        password=password,
        is_admin=is_admin
    )

    # 3) Return the result message
    return result

# ──────────────────────────────────────────────────────────
# LIST ROOMS
# ──────────────────────────────────────────────────────────
async def list_rooms() -> list[dict]:
    """
    Returns a list of rooms that DIRECTOR_CLIENT knows about, 
    including participant names.

    Each dict in the returned list includes:
       {
         "room_id": "<string>",
         "name": "<string>",
         "joined_members_count": <int>,
         "participants": [<list of user IDs or display names>]
       }
    """
    if not DIRECTOR_CLIENT:
        logger.warning("list_rooms called, but DIRECTOR_CLIENT is None.")
        return []

    rooms_info = []
    for room_id, room_obj in DIRECTOR_CLIENT.rooms.items():
        room_name = room_obj.display_name or "(unnamed)"
        participant_list = [user_id for user_id in room_obj.users.keys()]

        rooms_info.append({
            "room_id": room_id,
            "name": room_name,
            "joined_members_count": len(participant_list),
            "participants": participant_list
        })

    return rooms_info


# ──────────────────────────────────────────────────────────
# ADMIN API FOR CREATING USERS
# ──────────────────────────────────────────────────────────
async def add_user_via_admin_api(
    homeserver_url: str,
    admin_token: str,
    username: str,
    password: str,
    is_admin: bool = False
) -> str:
    """
    Creates a new user by hitting the Synapse Admin API.
    """
    user_id = f"@{username}:localhost"
    url = f"{homeserver_url}/_synapse/admin/v2/users/{user_id}"

    body = {
        "password": password,
        "admin": is_admin,
        "deactivated": False
    }
    headers = {
        "Authorization": f"Bearer {admin_token}"
    }

    logger.info(f"Creating user {user_id}, admin={is_admin} via {url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.request("PUT", url, headers=headers, json=body) as resp:
                if resp.status in (200, 201):
                    logger.info(f"Created user {user_id} (HTTP {resp.status})")
                    return f"Created user {user_id} (admin={is_admin})."
                else:
                    text = await resp.text()
                    logger.error(f"Error creating user {user_id}: {resp.status} => {text}")
                    return f"HTTP {resp.status}: {text}"

    except aiohttp.ClientError as e:
        logger.exception(f"Network error creating user {user_id}")
        return f"Network error: {e}"
    except Exception as e:
        logger.exception("Unexpected error.")
        return f"Unexpected error: {e}"

# ──────────────────────────────────────────────────────────
# RECENT MESSAGES
# ──────────────────────────────────────────────────────────
async def fetch_recent_messages(room_id: str, limit: int = 100) -> list:
    """
    Fetches the most recent messages from a Matrix room. Used to build context for
    """
    logger.info(f"Fetching last {limit} messages from room {room_id}.")
    client = DIRECTOR_CLIENT
    try:
        response = await client.room_messages(
            room_id=room_id,
            start=None,  # None fetches the latest messages
            limit=limit,
        )
        formatted_messages = []
        for event in response.chunk:
            if isinstance(event, RoomMessageText):
                formatted_messages.append({
                    "role": "user",
                    "content": event.body
                })

        logger.info(f"Fetched {len(formatted_messages)} messages from room {room_id}.")
        return formatted_messages

    except Exception as e:
        logger.exception(f"Failed to fetch messages from room {room_id}: {e}")
        return []


def store_token_info(user_id: str, access_token: str, device_id: str) -> None:
    """
    Write the token file to disk, so we can reuse it in later runs.
    """
    data = {
        "user_id": user_id,
        "access_token": access_token,
        "device_id": device_id
    }
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f)
    logger.debug(f"Stored token data for {user_id} into {TOKEN_FILE}.")


# ──────────────────────────────────────────────────────────
# SYNC TOKEN MANAGEMENT
# ──────────────────────────────────────────────────────────
def load_sync_token() -> str:
    """
    Load the previously saved sync token (next_batch).
    """
    if not os.path.exists(SYNC_TOKEN_FILE):
        return None
    try:
        with open(SYNC_TOKEN_FILE, "r") as f:
            return json.load(f).get("sync_token")
    except Exception as e:
        logger.warning(f"Failed to load sync token: {e}")
    return None

def store_sync_token(sync_token: str) -> None:
    """
    Persist the sync token so we won't re-fetch old messages on next run.
    """
    if not sync_token:
        return
    with open(SYNC_TOKEN_FILE, "w") as f:
        json.dump({"sync_token": sync_token}, f)
    logger.debug(f"Sync token saved to {SYNC_TOKEN_FILE}.")

async def post_gpt_reply(room_id: str, gpt_reply: str) -> None:
    """
    Helper to post a GPT-generated reply to a given room,
    using the global DIRECTOR_CLIENT if it's set.
    """
    global DIRECTOR_CLIENT

    if not DIRECTOR_CLIENT:
        logger.warning("No DIRECTOR_CLIENT set; cannot post GPT reply.")
        return

    try:
        await DIRECTOR_CLIENT.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": gpt_reply},
        )
        logger.info(f"Posted GPT reply to room {room_id}")
    except Exception as e:
        logger.exception(f"Failed to send GPT reply: {e}")


# ──────────────────────────────────────────────────────────
# The specialized dispatch function is replaced with the import below
# We rely on that file (luna_functions_handledispatch.py) to handle routing
# but it calls back into this file for actual matrix actions.
# ──────────────────────────────────────────────────────────
# covered by another import from src.luna_functions_handledispatch import on_room_message


# ──────────────────────────────────────────────────────────
# ON INVITE EVENT
# ──────────────────────────────────────────────────────────
async def on_invite_event(room, event):
    """
    Called whenever the client is invited to a room.
    """
    global DIRECTOR_CLIENT
    if not DIRECTOR_CLIENT:
        logger.warning("No DIRECTOR_CLIENT set. Cannot handle invites.")
        return

    logger.info(f"Received invite to {room.room_id}, joining now.")
    try:
        await DIRECTOR_CLIENT.join(room.room_id)
    except LocalProtocolError as e:
        logger.error(f"Error joining room {room.room_id}: {e}")


# ──────────────────────────────────────────────────────────
# CHECK RATE LIMIT
# ──────────────────────────────────────────────────────────
async def check_rate_limit() -> str:
    """
    Send a minimal sync request with a short timeout (1000 ms).
    If it returns SyncResponse => not rate-limited.
    If it's ErrorResponse => check the status code for 429 or something else.
    """
    global DIRECTOR_CLIENT
    if not DIRECTOR_CLIENT:
        return "No DIRECTOR_CLIENT available. Are we logged in?"

    try:
        response = await DIRECTOR_CLIENT.sync(timeout=1000)

        if isinstance(response, SyncResponse):
            return "200 OK => Not rate-limited. The server responded normally."
        elif isinstance(response, ErrorResponse):
            if response.status_code == 429:
                return "429 Too Many Requests => You are currently rate-limited."
            else:
                return (
                    f"{response.status_code} => Unexpected error.\n"
                    f"errcode: {response.errcode}, error: {response.error}"
                )
        return "Unexpected response type from DIRECTOR_CLIENT.sync(...)."
    except Exception as e:
        logger.exception(f"check_rate_limit encountered an error: {e}")
        return f"Encountered error while checking rate limit: {e}"

MESSAGES_CSV = "luna_messages.csv"

def _print_progress(stop_event):
    """
    Prints '...' every second until stop_event is set.
    """
    while not stop_event.is_set():
        print("...", end='', flush=True)
        time.sleep(1)

async def fetch_all_messages_once(
    client: AsyncClient, 
    room_ids: list[str] = None, 
    page_size: int = 100
) -> None:
    """
    Fetch *all* historical messages from the given room_ids (or all joined rooms if None).
    Populates the MESSAGES_CSV file, creating it if it doesn't exist or is empty.
    """
    if not room_ids:
        room_ids = list(client.rooms.keys())
        logger.info(f"No room_ids specified. Using all joined rooms: {room_ids}")

    all_records = []
    for rid in room_ids:
        logger.info(f"Fetching *all* messages for room: {rid}")
        room_history = await _fetch_room_history_paged(client, rid, page_size=page_size)
        all_records.extend(room_history)

    if not all_records:
        logger.warning("No messages fetched. CSV file will not be updated.")
        return

    df = pd.DataFrame(all_records, columns=["room_id", "event_id", "sender", "timestamp", "body"])
    logger.info(f"Fetched total {len(df)} messages across {len(room_ids)} room(s).")

    if os.path.exists(MESSAGES_CSV):
        try:
            # Attempt to read existing CSV
            existing_df = pd.read_csv(MESSAGES_CSV)
            logger.debug(f"Existing CSV loaded with {len(existing_df)} records.")
        except pd.errors.EmptyDataError:
            # Handle empty CSV by creating an empty DataFrame with the correct columns
            existing_df = pd.DataFrame(columns=["room_id", "event_id", "sender", "timestamp", "body"])
            logger.warning(f"{MESSAGES_CSV} is empty. Creating a new DataFrame with columns.")

        # Combine existing and new records
        combined_df = pd.concat([existing_df, df], ignore_index=True)
        # Drop duplicates based on 'room_id' and 'event_id'
        combined_df.drop_duplicates(subset=["room_id", "event_id"], keep="last", inplace=True)
        # Save back to CSV
        combined_df.to_csv(MESSAGES_CSV, index=False)
        logger.info(f"Appended new records to existing {MESSAGES_CSV}. New total: {len(combined_df)}")
    else:
        # If CSV doesn't exist, create it with the new records
        df.to_csv(MESSAGES_CSV, index=False)
        logger.info(f"Wrote all records to new CSV {MESSAGES_CSV}.")

async def _fetch_room_history_paged(
    client: AsyncClient, 
    room_id: str, 
    page_size: int
) -> list[dict]:
    """
    Helper to page backwards in time until no more messages or we hit server's earliest.
    ...
    """
    all_events = []
    end_token = None

    while True:
        try:
            response = await client.room_messages(
                room_id=room_id,
                start=end_token,
                limit=page_size,
                direction="b"
            )
            if not isinstance(response, RoomMessagesResponse):
                logger.warning(f"Got a non-success response: {response}")
                break
            
            chunk = response.chunk
            if not chunk:
                logger.info(f"No more chunk for {room_id}, done paging.")
                break

            for ev in chunk:
                if isinstance(ev, RoomMessageText):
                    all_events.append({
                        "room_id": room_id,
                        "event_id": ev.event_id,
                        "sender": ev.sender,
                        "timestamp": ev.server_timestamp,
                        "body": ev.body
                    })
            
            end_token = response.end
            if not end_token:
                logger.info(f"Got empty 'end' token for {room_id}, done paging.")
                break

            logger.debug(f"Fetched {len(chunk)} messages this page for room={room_id}, new end={end_token}")
            await asyncio.sleep(0.25)

        except Exception as e:
            logger.exception(f"Error in room_messages paging for {room_id}: {e}")
            break

    return all_events


# ──────────────────────────────────────────────────────────
# FETCH ONLY NEW MESSAGES
# ──────────────────────────────────────────────────────────
async def fetch_all_new_messages() -> None:
    """
    Uses client.sync(...) with a stored sync_token to retrieve only new messages across all joined rooms.
    ...
    """
    old_token = load_sync_token() or None
    logger.info(f"Starting incremental sync from token={old_token}")
    client = DIRECTOR_CLIENT
    response = await client.sync(timeout=3000, since=old_token)
    if not isinstance(response, SyncResponse):
        logger.warning(f"Failed to sync for new messages: {response}")
        return
    
    new_records = []
    for room_id, room_data in response.rooms.join.items():
        for event in room_data.timeline.events:
            if isinstance(event, RoomMessageText):
                new_records.append({
                    "room_id": room_id,
                    "event_id": event.event_id,
                    "sender": event.sender,
                    "timestamp": event.server_timestamp,
                    "body": event.body,
                })

    logger.info(f"Fetched {len(new_records)} new messages across {len(response.rooms.join)} joined rooms.")

    if new_records:
        df_new = pd.DataFrame(new_records, columns=["room_id", "event_id", "sender", "timestamp", "body"])

        if os.path.exists(MESSAGES_CSV):
            existing_df = pd.read_csv(MESSAGES_CSV)
            combined_df = pd.concat([existing_df, df_new], ignore_index=True)
            combined_df.drop_duplicates(subset=["room_id", "event_id"], keep="last", inplace=True)
            combined_df.to_csv(MESSAGES_CSV, index=False)
            logger.info(f"Appended new messages to {MESSAGES_CSV}. Updated total: {len(combined_df)}")
        else:
            df_new.to_csv(MESSAGES_CSV, index=False)
            logger.info(f"Wrote new messages to fresh CSV {MESSAGES_CSV}.")

    new_token = response.next_batch
    if new_token:
        store_sync_token(new_token)
        logger.info(f"Updated local sync token => {new_token}")


# ──────────────────────────────────────────────────────────
# LIST USERS
# ──────────────────────────────────────────────────────────
async def list_users() -> list[dict]:
    """
    Returns a list of all users on the Synapse server, using the admin API.
    ...
    """
    homeserver_url = "http://localhost:8008"  # adjust if needed
    try:
        with open("director_token.json", "r") as f:
            data = json.load(f)
        admin_token = data["access_token"]
    except Exception as e:
        logger.error(f"Unable to load admin token from director_token.json: {e}")
        return []

    url = f"{homeserver_url}/_synapse/admin/v2/users"
    headers = {"Authorization": f"Bearer {admin_token}"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    resp_data = await resp.json()
                    raw_users = resp_data.get("users", [])
                    users_list = []
                    for u in raw_users:
                        users_list.append({
                            "user_id": u.get("name"),
                            "displayname": u.get("displayname"),
                            "admin": u.get("admin", False),
                            "deactivated": u.get("deactivated", False),
                        })
                    return users_list
                else:
                    text = await resp.text()
                    logger.error(f"Failed to list users (HTTP {resp.status}): {text}")
                    return []
    except Exception as e:
        logger.exception(f"Error calling list_users admin API: {e}")
        return []


# ──────────────────────────────────────────────────────────
# INVITE USER TO ROOM
# ──────────────────────────────────────────────────────────
async def invite_user_to_room(user_id: str, room_id: str) -> str:
    """
    Invite an existing Matrix user to a room, using DIRECTOR_CLIENT to do so.
    """
    global DIRECTOR_CLIENT
    if not DIRECTOR_CLIENT:
        error_msg = "Error: No DIRECTOR_CLIENT available."
        logger.error(error_msg)
        return error_msg

    try:
        resp = await DIRECTOR_CLIENT.room_invite(room_id, user_id)
        if isinstance(resp, RoomInviteResponse):
            logger.info(f"Successfully invited {user_id} to {room_id}.")
            return f"Invited {user_id} to {room_id} successfully."
        else:
            logger.error(f"Failed to invite {user_id} to {room_id}: {resp}")
            return f"Error inviting {user_id} to {room_id}. Response: {resp}"
    except Exception as e:
        logger.exception(f"Exception while inviting {user_id} to {room_id}: {e}")
        return f"Exception inviting {user_id} to {room_id}: {e}"


# ──────────────────────────────────────────────────────────
# DELETE MATRIX USER
# ──────────────────────────────────────────────────────────
async def delete_matrix_user(localpart: str) -> str:
    """
    Deletes a user from Synapse using the admin API.
    ...
    """
    from src.luna_functions import get_admin_token  # or however you load it
    admin_token = get_admin_token()

    user_id = f"@{localpart}:localhost"
    url = f"http://localhost:8008/_synapse/admin/v2/users/{user_id}"
    headers = {"Authorization": f"Bearer {admin_token}"}

    import aiohttp
    import logging
    logger = logging.getLogger(__name__)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.delete(url, headers=headers) as resp:
                if resp.status == 200:
                    return f"Deleted Matrix user {user_id} successfully."
                elif resp.status == 404:
                    return f"Matrix user {user_id} not found. Possibly already deleted."
                else:
                    text = await resp.text()
                    return f"Error {resp.status} deleting user {user_id}: {text}"
    except Exception as e:
        logger.exception(f"Error in delete_matrix_user({user_id}): {e}")
        return f"Exception deleting user {user_id}: {e}"

=== src/luna_functions_handledispatch.py ===
"""
luna_functions_handledispatch.py

A "positive signal" version of on_room_message to prove the rest
of your mention-handling pipeline fires. It unconditionally logs
that a mention was found, so you can see if your code that runs
AFTER a mention is recognized actually does anything.
"""

LUNA_USER_ID = '@lunabot:localhost'

import logging
logger = logging.getLogger(__name__)

import os
import pandas as pd
import logging
from src.luna_functions import invite_user_to_room, list_rooms



from src.luna_functions import (
    invite_user_to_room,
    list_rooms,
    post_gpt_reply,
    MESSAGES_CSV 
)

from src.luna_functions import invite_user_to_room, list_rooms
from src.ai_functions import get_gpt_response  # or wherever your GPT integration resides

import pandas as pd
import os
import logging
from nio import RoomMessageText


MESSAGES_CSV = "luna_messages.csv"

import pandas as pd
import os
import logging
from nio import RoomMessageText

MESSAGES_CSV = "luna_messages.csv"

import pandas as pd
import os
import logging
from nio import RoomMessageText

# Configure logging to write to 'luna.log' only
logger = logging.getLogger('luna_logger')
logger.setLevel(logging.DEBUG)  # Set to DEBUG to capture all levels of logs

# Create file handler which logs even debug messages
fh = logging.FileHandler('luna.log')
fh.setLevel(logging.DEBUG)

# Create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)

# Add the handlers to the logger
if not logger.hasHandlers():
    logger.addHandler(fh)

# Prevent logs from being propagated to the root logger
logger.propagate = False

MESSAGES_CSV = "luna_messages.csv"

# Import external functions from src.luna_functions
from src.luna_functions import invite_user_to_room, list_rooms, post_gpt_reply
from src.ai_functions import get_gpt_response

async def on_room_message_dep_working_silent_luna_inprivate(room, event):
    """
    Handles incoming room messages by:
    1. Saving them to MESSAGES_CSV without duplicates.
    2. Processing mentions to generate and post GPT responses only for new messages.
    """
    if not isinstance(event, RoomMessageText):
        logger.debug("Ignored non-text message.")
        return  # Ignore non-text messages

    user_message = event.body.strip() if event.body else ""
    message_record = {
        "room_id": room.room_id,
        "event_id": event.event_id,
        "sender": event.sender,
        "timestamp": event.server_timestamp,
        "body": user_message
    }

    is_new_message = False  # Flag to determine if GPT should be invoked

    try:
        if os.path.exists(MESSAGES_CSV):
            try:
                existing_df = pd.read_csv(MESSAGES_CSV)
                logger.debug(f"Loaded existing CSV with {len(existing_df)} records.")
            except pd.errors.EmptyDataError:
                # CSV exists but is empty; initialize with headers
                existing_df = pd.DataFrame(columns=["room_id", "event_id", "sender", "timestamp", "body"])
                logger.warning(f"{MESSAGES_CSV} is empty. Initializing with headers.")

            # Check for duplicate 'event_id'
            if event.event_id not in existing_df['event_id'].values:
                is_new_message = True
                # Append the new message without writing headers
                df_new = pd.DataFrame([message_record])
                df_new.to_csv(MESSAGES_CSV, mode='a', header=False, index=False)
                logger.info(f"Appended new message {event.event_id} to {MESSAGES_CSV}.")
            else:
                logger.info(f"Duplicate message {event.event_id} found. Skipping append and GPT processing.")
        else:
            # CSV doesn't exist; create it with headers and write the first message
            is_new_message = True
            df_new = pd.DataFrame([message_record])
            df_new.to_csv(MESSAGES_CSV, mode='w', header=True, index=False)
            logger.info(f"Created {MESSAGES_CSV} and wrote the first message {event.event_id}.")

    except Exception as e:
        logger.exception(f"Failed to save message {event.event_id}: {e}")
        return  # Exit early if saving fails

    # Proceed to process mentions and GPT only if it's a new message
    if is_new_message:
        logger.info("Processing mentions and preparing to call GPT.")

        content = event.source.get("content", {})
        mentions_field = content.get("m.mentions", {})
        mentioned_ids = mentions_field.get("user_ids", [])

        if not mentioned_ids:
            logger.debug("No user_ids in m.mentions => no mention recognized.")
            return  # No mentions to process

        logger.info(f"Mentioned user_ids => {mentioned_ids}")

        # Example triggers based on message content
        if "invite me" in user_message.lower():
            result = await invite_user_to_room("@somebody:localhost", room.room_id)
            logger.info(f"Invite result => {result}")

        if "rooms?" in user_message.lower():
            rooms_data = await list_rooms()
            logger.info(f"Rooms => {rooms_data}")

        # GPT reply per mention
        for mention_id in mentioned_ids:
            logger.info(f"Processing mention for user => {mention_id}")

            gpt_context = [
                {"role": "system", "content": f"You are a helpful bot responding to a mention of {mention_id}."},
                {"role": "user", "content": user_message}
            ]

            try:
                gpt_reply = await get_gpt_response(gpt_context)
                logger.info(f"GPT reply (for mention {mention_id}) => {gpt_reply}")
            except Exception as e:
                logger.exception("Error calling GPT:")
                gpt_reply = f"[Error: {e}]"

            await post_gpt_reply(room.room_id, gpt_reply)
    else:
        logger.debug("Message already processed. No further action taken.")

async def on_room_message(room, event):
    """
    Handles incoming room messages by:
    1. Saving them to MESSAGES_CSV without duplicates.
    2. Processing mentions to generate and post GPT responses only for new messages.
    3. Automatically responding if there are no mentions and only one other participant.
    4. Ensuring Luna never replies to her own messages, including self-tags.
    """
    if not isinstance(event, RoomMessageText):
        logger.debug("Ignored non-text message.")
        return  # Ignore non-text messages

    # Prevent Luna from responding to her own messages
    if event.sender == '@lunabot:localhost':
        logger.info(f"Ignored message from Luna herself (event_id={event.event_id}).")
        return

    user_message = event.body.strip() if event.body else ""
    message_record = {
        "room_id": room.room_id,
        "event_id": event.event_id,
        "sender": event.sender,
        "timestamp": event.server_timestamp,
        "body": user_message
    }

    is_new_message = False  # Flag to determine if GPT should be invoked

    try:
        if os.path.exists(MESSAGES_CSV):
            try:
                existing_df = pd.read_csv(MESSAGES_CSV)
                logger.debug(f"Loaded existing CSV with {len(existing_df)} records.")
            except pd.errors.EmptyDataError:
                # CSV exists but is empty; initialize with headers
                existing_df = pd.DataFrame(columns=["room_id", "event_id", "sender", "timestamp", "body"])
                logger.warning(f"{MESSAGES_CSV} is empty. Initializing with headers.")

            # Check for duplicate 'event_id'
            if event.event_id not in existing_df['event_id'].values:
                is_new_message = True
                # Append the new message without writing headers
                df_new = pd.DataFrame([message_record])
                df_new.to_csv(MESSAGES_CSV, mode='a', header=False, index=False)
                logger.info(f"Appended new message {event.event_id} to {MESSAGES_CSV}.")
            else:
                logger.info(f"Duplicate message {event.event_id} found. Skipping append and GPT processing.")
        else:
            # CSV doesn't exist; create it with headers and write the first message
            is_new_message = True
            df_new = pd.DataFrame([message_record])
            df_new.to_csv(MESSAGES_CSV, mode='w', header=True, index=False)
            logger.info(f"Created {MESSAGES_CSV} and wrote the first message {event.event_id}.")

    except Exception as e:
        logger.exception(f"Failed to save message {event.event_id}: {e}")
        return  # Exit early if saving fails

    # Proceed to process mentions and GPT only if it's a new message
    if is_new_message:
        logger.info("Processing mentions and preparing to call GPT.")

        content = event.source.get("content", {})
        mentions_field = content.get("m.mentions", {})
        mentioned_ids = mentions_field.get("user_ids", [])

        if mentioned_ids:
            # Remove Luna's own ID from mentions to prevent self-response
            mentioned_ids = [uid for uid in mentioned_ids if uid != LUNA_USER_ID]
            if not mentioned_ids:
                logger.info("Only Luna was mentioned. No action taken.")
                return

            logger.info(f"Processed mentions (excluding Luna): {mentioned_ids}")

            # Example triggers based on message content
            if "invite me" in user_message.lower():
                result = await invite_user_to_room("@somebody:localhost", room.room_id)
                logger.info(f"Invite result => {result}")

            if "rooms?" in user_message.lower():
                rooms_data = await list_rooms()
                logger.info(f"Rooms => {rooms_data}")

            # GPT reply per mention
            for mention_id in mentioned_ids:
                logger.info(f"Processing mention for user => {mention_id}")

                gpt_context = [
                    {"role": "system", "content": f"You are a helpful bot responding to a mention of {mention_id}."},
                    {"role": "user", "content": user_message}
                ]

                try:
                    gpt_reply = await get_gpt_response(gpt_context)
                    logger.info(f"GPT reply (for mention {mention_id}) => {gpt_reply}")
                except Exception as e:
                    logger.exception("Error calling GPT:")
                    gpt_reply = f"[Error: {e}]"

                await post_gpt_reply(room.room_id, gpt_reply)
        else:
            # No mentions; check if only one other participant is in the room
            try:
                participants = room.users  # Assuming 'users' is a dict of user_id to user info
                participant_count = len(participants)
                logger.debug(f"Room has {participant_count} participants.")

                if participant_count == 2:
                    # Only Luna and one other participant
                    logger.info("No mentions and only one other participant. Preparing to respond.")

                    gpt_context = [
                        {"role": "system", "content": "You are Luna, a helpful assistant."},
                        {"role": "user", "content": user_message}
                    ]

                    try:
                        gpt_reply = await get_gpt_response(gpt_context)
                        logger.info(f"GPT reply => {gpt_reply}")
                    except Exception as e:
                        logger.exception("Error calling GPT:")
                        gpt_reply = f"[Error: {e}]"

                    await post_gpt_reply(room.room_id, gpt_reply)
                else:
                    logger.debug("More than two participants in the room. No automatic response triggered.")
            except AttributeError:
                logger.error("Room object does not have 'users' attribute.")
            except Exception as e:
                logger.exception(f"Error processing participant count: {e}")

    else:
        logger.debug("Message already processed. No further action taken.")

async def on_room_message_dep_double_responding(room, event):
    """
    Handles incoming room messages by saving them to a CSV file,
    ensuring no duplicate entries based on 'event_id', and processing mentions
    to generate and post GPT responses.
    """
    if not isinstance(event, RoomMessageText):
        return  # Ignore non-text messages

    user_message = event.body or ""

    message_record = {
        "room_id": room.room_id,
        "event_id": event.event_id,
        "sender": event.sender,
        "timestamp": event.server_timestamp,
        "body": user_message
    }

    try:
        if os.path.exists(MESSAGES_CSV):
            try:
                existing_df = pd.read_csv(MESSAGES_CSV)
                logger.debug(f"Loaded existing CSV with {len(existing_df)} records.")
            except pd.errors.EmptyDataError:
                # CSV exists but is empty; initialize with headers
                existing_df = pd.DataFrame(columns=["room_id", "event_id", "sender", "timestamp", "body"])
                logger.warning(f"{MESSAGES_CSV} is empty. Initializing with headers.")

            # Check for duplicate 'event_id'
            if event.event_id not in existing_df['event_id'].values:
                # Append the new message without writing headers
                df_new = pd.DataFrame([message_record])
                df_new.to_csv(MESSAGES_CSV, mode='a', header=False, index=False)
                logger.info(f"Appended new message {event.event_id} to {MESSAGES_CSV}.")
            else:
                logger.info(f"Duplicate message {event.event_id} found. Skipping append.")
        else:
            # CSV doesn't exist; create it with headers and write the first message
            df_new = pd.DataFrame([message_record])
            df_new.to_csv(MESSAGES_CSV, mode='w', header=True, index=False)
            logger.info(f"Created {MESSAGES_CSV} and wrote the first message {event.event_id}.")
    except Exception as e:
        logger.exception(f"Failed to save message {event.event_id}: {e}")

    # --------------------------
    #  Step B: Parse mentions & GPT dispatch
    # --------------------------
    logger.info("Handling on_room_message with multi-mention iteration approach.")

    content = event.source.get("content", {})
    mentions_field = content.get("m.mentions", {})
    logger.debug(f"m.mentions => {mentions_field}")

    mentioned_ids = mentions_field.get("user_ids", [])
    if not mentioned_ids:
        logger.debug("No user_ids in m.mentions => no mention recognized.")
        return

    logger.info(f"Mentioned user_ids => {mentioned_ids}")

    # Example triggers based on message content
    if "invite me" in user_message.lower():
        result = await invite_user_to_room("@somebody:localhost", room.room_id)
        logger.info(f"Invite result => {result}")

    if "rooms?" in user_message.lower():
        rooms_data = await list_rooms()
        logger.info(f"Rooms => {rooms_data}")

    # GPT reply per mention
    for mention_id in mentioned_ids:
        logger.info(f"Processing mention for user => {mention_id}")

        gpt_context = [
            {"role": "system", "content": f"You are a helpful bot responding to a mention of {mention_id}."},
            {"role": "user", "content": user_message}
        ]

        try:
            gpt_reply = await get_gpt_response(gpt_context)
            logger.info(f"GPT reply (for mention {mention_id}) => {gpt_reply}")
        except Exception as e:
            logger.exception("Error calling GPT:")
            gpt_reply = f"[Error: {e}]"

        await post_gpt_reply(room.room_id, gpt_reply)

async def on_room_message_dep(room, event):
    """
    1) Saves the new message to `luna_messages.csv`, ensuring no duplicates.
    2) Checks mentions in m.mentions["user_ids"] and, if present,
       calls GPT once per user ID, posting replies to the room.
    """

    from nio import RoomMessageText
    if not isinstance(event, RoomMessageText):
        return  # ignore non-text events

    # --------------------------
    #  Step A: Write to local datastore
    # --------------------------
    user_message = event.body or ""
    new_record = [{
        "room_id": room.room_id,
        "event_id": event.event_id,
        "sender": event.sender,
        "timestamp": event.server_timestamp,
        "body": user_message
    }]

    df_new = pd.DataFrame(new_record, columns=["room_id", "event_id", "sender", "timestamp", "body"])

    try:
        if os.path.exists(MESSAGES_CSV):
            existing_df = pd.read_csv(MESSAGES_CSV)
            before_count = len(existing_df)

            combined_df = pd.concat([existing_df, df_new], ignore_index=True)
            # Drop duplicates on (room_id, event_id) to avoid duplicates
            combined_df.drop_duplicates(subset=["room_id", "event_id"], keep="last", inplace=True)
            after_count = len(combined_df)

            combined_df.to_csv(MESSAGES_CSV, index=False)

            if after_count == before_count:
                logger.info(
                    f"Duplicate message detected (event_id={event.event_id}), "
                    "no new row appended to luna_messages.csv."
                )
            else:
                logger.debug(
                    f"Added {after_count - before_count} new message(s) to {MESSAGES_CSV}. "
                    f"New total: {after_count}"
                )
        else:
            df_new.to_csv(MESSAGES_CSV, index=False)
            logger.debug(
                f"No existing CSV found; created {MESSAGES_CSV} with 1 record (event_id={event.event_id})."
            )
    except Exception as e:
        logger.exception(f"Failed to write message (event_id={event.event_id}) to {MESSAGES_CSV}: {e}")

    # --------------------------
    #  Step B: Parse mentions & GPT dispatch
    # --------------------------
    logger.info("Handling on_room_message with multi-mention iteration approach.")

    room_id = room.room_id
    logger.debug(f"User message => '{user_message}' (room_id={room_id})")

    content = event.source.get("content", {})
    mentions_field = content.get("m.mentions", {})
    logger.debug(f"m.mentions => {mentions_field}")

    mentioned_ids = mentions_field.get("user_ids", [])
    if not mentioned_ids:
        logger.debug("No user_ids in m.mentions => no mention recognized.")
        return

    logger.info(f"Mentioned user_ids => {mentioned_ids}")

    # Example triggers
    if "!invite me" in user_message.lower():
        result = await invite_user_to_room("@somebody:localhost", room_id)
        logger.info(f"Invite result => {result}")

    if "!rooms" in user_message.lower():
        rooms_data = await list_rooms()
        logger.info(f"Rooms => {rooms_data}")

    # GPT reply per mention
    for mention_id in mentioned_ids:
        logger.info(f"Processing mention for user => {mention_id}")

        gpt_context = [
            {"role": "system", "content": f"You are a helpful bot responding to a mention of {mention_id}."},
            {"role": "user", "content": user_message}
        ]

        try:
            gpt_reply = await get_gpt_response(gpt_context)
            logger.info(f"GPT reply (for mention {mention_id}) => {gpt_reply}")
        except Exception as e:
            logger.exception("Error calling GPT:")
            gpt_reply = f"[Error: {e}]"

        await post_gpt_reply(room_id, gpt_reply)
=== src/luna_functions_summarize_channel.py ===
# luna_functions_summarize_channel.py

"""
Provides skeleton functions to summarize a Matrix room's conversation.

Intended to integrate with the Luna environment, e.g. calling from
'luna_functions.py' or other modules within your codebase.
"""

from typing import List, Optional


def summarize_room(
    room_id: str,
    summary_type: str = "content",
    audience: str = "general",
    granularity: int = 3,
    include_personalities: bool = False,
    exclude_participants: Optional[List[str]] = None,
    output_format: str = "text",
    chunk_size: int = 25
) -> str:
    """
    Summarizes the conversation in the given Matrix room, returning a string
    based on the specified parameters.

    :param room_id: The Matrix room identifier (e.g., "!abc123:localhost").
    :param summary_type: Type of summary (e.g., "content", "highlights", "facts", "custom").
    :param audience: Style or complexity level (e.g., "executive", "technical").
    :param granularity: Numeric detail level (1 = minimal, up to ~5 = thorough).
    :param include_personalities: Whether to factor in specialized bot/persona data.
    :param exclude_participants: List of user IDs to exclude from the summary logic.
    :param output_format: Desired result format (e.g., "text", "markdown", "json").
    :param chunk_size: Number of messages to process per batch (default = 25).
    :return: A string containing the final summary.
    """
    # 1) Gather data from local store or CSV/DB (instead of remote fetch).
    messages = _gather_room_data(room_id, chunk_size)

    # 2) Pre-process data:
    #    - Filter out 'exclude_participants'
    #    - Possibly handle persona references if 'include_personalities' is True
    processed_data = _pre_process_data(messages, exclude_participants, include_personalities)

    # 3) Build a prompt or instruction set for summarization.
    prompt = _build_summary_prompt(processed_data, summary_type, audience, granularity)

    # 4) Perform the actual summarization (likely calling GPT or another LLM).
    raw_summary = _do_summarize(prompt)

    # 5) Format the output according to 'output_format' (e.g., text, markdown).
    final_output = _format_output(raw_summary, output_format)

    final_output = "luna_functions_summarize_channel.py - NOT IMPLEMENTED YET"


    return final_output


def _gather_room_data(room_id: str, chunk_size: int) -> List[dict]:
    """
    Reads the conversation data from local storage (e.g., CSV, DB, or in-memory) 
    for the specified room.

    :param room_id: The Matrix room ID or alias.
    :param chunk_size: Number of messages to pull at once (could be used or 
                       adjusted if needed).
    :return: A list of message dicts, each containing at least:
             {
               "sender": "...",
               "body": "...",
               "timestamp": ...,
               ...
             }
    """
    # Placeholder: In real code, you'd query your local data store 
    # (luna_messages.csv or a DB).
    # Possibly chunk retrieval if the room has a large message history.
    messages = []
    # ... implementation ...
    return messages


def _pre_process_data(
    messages: List[dict],
    exclude_participants: Optional[List[str]],
    include_personalities: bool
) -> List[dict]:
    """
    Applies filtering and annotation logic to raw message data.

    :param messages: The raw messages from _gather_room_data.
    :param exclude_participants: A list of user IDs to exclude from the summary.
    :param include_personalities: Whether to incorporate persona data.
    :return: A refined/filtered list of messages.
    """
    # 1) Exclude messages from certain participants
    if exclude_participants:
        messages = [
            msg for msg in messages
            if msg["sender"] not in exclude_participants
        ]
    # 2) If 'include_personalities' is True, you might annotate or retrieve 
    #    persona details here or store them in a side structure.

    # ... placeholder for further data transformations ...
    return messages


def _build_summary_prompt(
    processed_data: List[dict],
    summary_type: str,
    audience: str,
    granularity: int
) -> str:
    """
    Construct a prompt or instruction string that guides the summarization step.

    :param processed_data: The messages already filtered/prepared.
    :param summary_type: e.g. "content", "highlights", "facts", etc.
    :param audience: "general", "executive", "technical", etc.
    :param granularity: Numeric detail level.
    :return: A text prompt that an LLM or summarizer can use.
    """
    # You could embed a short snippet of messages or 
    # embed them all, depending on the chunking logic.
    # Also incorporate 'summary_type', 'audience', 'granularity' for style.
    prompt = f"""
You are summarizing a conversation with the following context:
Summary Type: {summary_type}
Audience: {audience}
Granularity: {granularity}
Messages:

"""
    # Append messages (truncated or chunked) 
    # to the prompt in some standard format
    for msg in processed_data:
        prompt += f"{msg['sender']}: {msg['body']}\n"

    # ... Additional instructions for the summarizer ...
    return prompt


def _do_summarize(prompt: str) -> str:
    """
    Actually perform the summarization, 
    e.g., calling an AI model or an existing summarizer.

    :param prompt: The prompt or instructions built from the conversation data.
    :return: Raw summarized text.
    """
    # Example: calling existing AI functions in your code, e.g.:
    #   from src.ai_functions import get_gpt_response
    #   summary = get_gpt_response([{"role":"system","content": "Your instructions"},
    #                               {"role":"user","content": prompt}])
    # For now, just a placeholder:
    summary = "Placeholder summary based on the prompt."
    return summary


def _format_output(raw_summary: str, output_format: str) -> str:
    """
    Convert the raw summarized text into the desired format 
    (text, markdown, json, etc.).

    :param raw_summary: The raw text from the summarization engine.
    :param output_format: "text", "markdown", "json", ...
    :return: The formatted summary as a string.
    """
    if output_format == "markdown":
        # e.g., wrap it in triple backticks or do minimal transformations
        return f"```\n{raw_summary}\n```"
    elif output_format == "json":
        # e.g., return a JSON structure with a "summary" field
        # or format it as you'd like
        return f'{{"summary": "{raw_summary.replace("\"", "\\\"")}"}}'
    else:
        # default: plain text
        return raw_summary

=== src/luna_personas.py ===
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
    password:str,
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
        "password": password,
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

