# persona_loader.py
import os
import requests
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

PROMPT_API_URL = os.getenv("PROMPT_API_URL", "http://localhost:8000/api/prompts")
HTTP_TIMEOUT = int(os.getenv("PROMPT_API_TIMEOUT", "5"))


async def fetch_agent_instruction() -> Optional[str]:
    """
    Asynchronously fetch AGENT_INSTRUCTION from the persona API.
    Uses asyncio.to_thread to avoid blocking the event loop (requests is blocking).
    Returns the instruction string on success, or None on failure.
    """
    def _sync_get():
        resp = requests.get(PROMPT_API_URL, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    try:
        data = await asyncio.to_thread(_sync_get)
        # the API returns a JSON which contains AGENT_INSTRUCTION
        # Adjust the key here if your API uses a different key
        instr = data.get("AGENT_INSTRUCTION") or data.get("agent_instructions") or data.get("instructions")
        if not instr:
            logger.warning("Persona API returned no AGENT_INSTRUCTION key")
            return None
        return instr
    except Exception as e:
        logger.exception(f"Failed to fetch AGENT_INSTRUCTION from {PROMPT_API_URL}: {e}")
        return None