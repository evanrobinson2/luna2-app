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