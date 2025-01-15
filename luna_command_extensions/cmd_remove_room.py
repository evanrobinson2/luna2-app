import logging
import asyncio
import aiohttp
from luna import luna_functions

logger = logging.getLogger(__name__)

def cmd_remove_room(args, loop):
    """
    Usage: remove_room <room_id>

    Example:
      remove_room !abc123:localhost

    This console command removes the room from the homeserver
    entirely using the Synapse Admin API:
      DELETE /_synapse/admin/v2/rooms/<roomID>

    Must be an admin user. This does not remove messages in a graceful
    manner—those events become orphaned. But the room
    is fully deleted from Synapse’s perspective, and future attempts
    to join or invite this room ID will fail.

    If you want to only forget the room from your perspective,
    do a normal "forget" in a Matrix client. This command is destructive.
    """

    parts = args.strip().split()
    if len(parts) < 1:
        print("SYSTEM: Usage: remove_room <room_id>")
        return

    room_id = parts[0]

    # The asynchronous subroutine:
    async def _do_remove_room(rid: str) -> str:
        """
        Actually calls the DELETE /_synapse/admin/v2/rooms/{roomId} endpoint.
        Must have admin privileges. 
        Sends an empty JSON body with Content-Type: application/json to avoid
        "Content not JSON" errors.
        """
        client = luna_functions.getClient()
        if not client:
            return "[Error] No DIRECTOR_CLIENT set or not logged in."

        admin_token = client.access_token
        if not admin_token:
            return "[Error] No admin token in DIRECTOR_CLIENT (need to be a Synapse admin)."

        homeserver_url = client.homeserver
        endpoint = f"{homeserver_url}/_synapse/admin/v2/rooms/{rid}"

        headers = {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json"
        }

        logger.debug(f"[_do_remove_room] Attempting to DELETE room => {endpoint}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(endpoint, headers=headers, json={}) as resp:
                    if resp.status in (200, 202):
                        return f"Successfully removed room => {rid}"
                    else:
                        text = await resp.text()
                        return f"Error removing room {rid}: {resp.status} => {text}"
        except Exception as e:
            logger.exception("[_do_remove_room] Exception calling admin API:")
            return f"Exception removing room => {e}"

    # The blocking wrapper:
    def do_remove_room_sync(rid: str) -> str:
        """
        Schedules _do_remove_room(...) on the event loop, then blocks until
        it finishes by calling future.result().
        """
        future = asyncio.run_coroutine_threadsafe(_do_remove_room(rid), loop)
        return future.result()

    print(f"SYSTEM: Removing room '{room_id}' from server (blocking)... Please wait.")
    # Actually run the removal, blocking until it's done
    result_msg = do_remove_room_sync(room_id)
    print(f"SYSTEM: {result_msg}")
