# image_helpers.py

import os
import logging
import urllib.parse

import aiohttp
from nio import AsyncClient

logger = logging.getLogger(__name__)

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

    logger.debug("[direct_upload_image] POST to %s, size=%d", upload_url, file_size)

    async with aiohttp.ClientSession() as session:
        with open(file_path, "rb") as f:
            async with session.post(upload_url, headers=headers, data=f) as resp:
                if resp.status == 200:
                    body = await resp.json()
                    content_uri = body.get("content_uri")
                    if not content_uri:
                        raise RuntimeError("No 'content_uri' in response JSON.")
                    logger.debug("[direct_upload_image] Uploaded. content_uri=%s", content_uri)
                    return content_uri
                else:
                    err_text = await resp.text()
                    raise RuntimeError(
                        f"Upload failed (HTTP {resp.status}): {err_text}"
                    )
