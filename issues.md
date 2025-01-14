#### ISSUES


1. Lunabot is the admin, it's hardcoded in multiple files
2. Multiple files declare globals and constants, those should move to a config file of some kind
3. Keys like the director key should be stored in environment variables, not on disk
4. In Luna Functions, sometimes we use the API to make changes, sometimes we call functions from matrix-nio, it's inconsistent
5. deleting a user doesn't destroy their entry in personalities


6. shut-down not graceful:?
2025-01-12 15:33:28,560 [ERROR] __main__: An unexpected exception occurred in main_logic: Event loop stopped before Future completed.
Traceback (most recent call last):
  File "/Users/evanrobinson/Documents/Luna2/luna/luna.py", line 152, in luna
    loop.run_until_complete(main_logic())
    ~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^
  File "/opt/homebrew/Cellar/python@3.13/3.13.1/Frameworks/Python.framework/Versions/3.13/lib/python3.13/asyncio/base_events.py", line 718, in run_until_complete
    raise RuntimeError('Event loop stopped before Future completed.')
RuntimeError: Event loop stopped before Future completed.
2025-01-12 15:33:28,561 [DEBUG] __main__: Preparing to close the event loop.
2025-01-12 15:33:28,561 [INFO] __main__: Event loop closed. Exiting main function.
2025-01-12 15:33:28,595 [ERROR] asyncio: Unclosed connector
connections: ['deque([(<aiohttp.client_proto.ResponseHandler object at 0x11de93f50>, 42509.1350415)])']
connector: <aiohttp.connector.TCPConnector object at 0x11de76350>

ISSUE - spawn_squad needs to be tested
ISSUE - Orphaned users can accumulate on the server.