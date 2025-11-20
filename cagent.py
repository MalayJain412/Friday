from dotenv import load_dotenv
import os
import datetime
import time
import config
import json
import requests
import logging

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, RoomOutputOptions
from livekit.plugins import (
    google,
    cartesia,
    deepgram,
    noise_cancellation,
    silero,
)
from tools import get_weather, search_web
from logging_config import configure_logging
from transcript_logger import set_session_id, set_dialed_number, set_session_manager
from session_manager import SessionManager

# persona loader
from persona_loader import fetch_agent_instruction

load_dotenv()

# Setup logging early
try:
    configure_logging()
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)

# Generate conversation log file path and set in config.py
def setup_conversation_log():
    log_dir = os.path.join(os.path.dirname(__file__), "KMS", "logs")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"conversation_{timestamp}.txt")
    config.set_conversation_log_path(log_path)

setup_conversation_log()

# Hardcoded session instruction (per your answer)
SESSION_INSTRUCTION = "Hello — welcome to Friday. How can I help you today?"

# Minimal wait instruction to create the agent before persona arrives
WAIT_INSTRUCTION = "Please wait while I load your personalized assistant."


# Example Assistant subclass (similar to yours). Keep it compatible with your code.
class Assistant(Agent):
    def __init__(self, custom_instructions: str, **kwargs):
        if not custom_instructions:
            raise ValueError("Agent requires custom_instructions - no default fallbacks allowed")
        # Use your existing LLM / tools configuration here
        super().__init__(
            instructions=custom_instructions,
            # Replace with your LLM and tools, e.g.:
            llm=google.LLM(model="gemini-2.5-flash", temperature=0.8),
            tools=[get_weather, search_web],
            **kwargs
        )


async def entrypoint(ctx: agents.JobContext):
    """
    Main entrypoint for each new call/session.
    Flow:
    - Create agent with WAIT_INSTRUCTION
    - Build session (STT/LLM/TTS/VAD as before)
    - Start session
    - Fetch AGENT_INSTRUCTION from API (persona)
    - Apply it to the running agent (agent.update_instructions)
    - Then generate the initial reply using SESSION_INSTRUCTION (hardcoded)
    """

    # session id / transcript and logging setup (use your helpers)
    session_id = f"session_{int(time.time())}"
    try:
        # If you have helpers to set session ID / logs, call them
        set_session_id(session_id)
        logging.info(f"Starting session {session_id}")
    except Exception:
        logging.exception("Failed to configure session logging")

    # Prepare the minimal agent (so session can start immediately)
    agent = Assistant(custom_instructions=WAIT_INSTRUCTION)

    # Build AgentSession with your configured STT/LLM/TTS/VAD instances.
    # Replace below with your instances retrieval method.
    # Example placeholders (you must replace with real constructors):
    # from livekit.plugins import deepgram, cartesia, silero
    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        tts=cartesia.TTS(
            model="sonic-2", 
            language='hi',
            # Female voice ID for Hindi
            voice="f91ab3e6-5071-4e15-b016-cde6f2bcd222"
        ),
        vad=silero.VAD.load(),
    )

    # Initialize session manager
    session_manager = SessionManager(session)
    set_session_manager(session_manager)
    
    # Setup transcription logging
    await session_manager.setup_session_logging()
    await session_manager.setup_shutdown_callback()

    # Start the session (session starts with WAIT_INSTRUCTION agent)
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
        room_output_options=RoomOutputOptions(audio_enabled=True),
    )

    # Now fetch the persona (AGENT_INSTRUCTION) asynchronously
    try:
        instr = await fetch_agent_instruction()
        if instr:
            # Preferred: call agent.update_instructions() if available
            try:
                if hasattr(agent, "update_instructions"):
                    # call update_instructions with the new prompt
                    await agent.update_instructions(instr)
                    logging.info("Applied new AGENT_INSTRUCTION via agent.update_instructions()")
                else:
                    # fallback: set attribute directly (some Agent SDKs read .instructions)
                    setattr(agent, "instructions", instr)
                    logging.info("Applied new AGENT_INSTRUCTION by setting agent.instructions")
            except Exception:
                logging.exception("Failed to apply new agent instructions; continuing with previous instructions")
        else:
            logging.warning("No AGENT_INSTRUCTION received — continuing with WAIT_INSTRUCTION")
    except Exception:
        logging.exception("Error while fetching persona — continuing with WAIT_INSTRUCTION")

    # Now send the session greeting using your hardcoded SESSION_INSTRUCTION
    try:
        await session.generate_reply(instructions=SESSION_INSTRUCTION)
    except Exception:
        logging.exception("Failed to generate initial session reply")

    # The rest of your call handling goes here: conversation loop, session manager, hangup handling, etc.
    # Example placeholder to wait until session ends
    try:
        # Start history watcher AFTER session starts
        await session_manager.start_history_watcher()
        # Wait for session termination or implement your conversation loop
        pass
    except Exception:
        logging.exception("Error in session main loop")


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
