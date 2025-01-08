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

