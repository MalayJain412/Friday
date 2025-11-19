from dotenv import load_dotenv
import os
import datetime
import time
import config

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, RoomOutputOptions
from livekit.plugins import (
    google,
    cartesia,
    deepgram,
    noise_cancellation,
    silero,
)
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import get_weather, search_web
from logging_config import configure_logging
from transcript_logger import set_session_id, set_dialed_number, set_session_manager
from session_manager import SessionManager

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


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=google.LLM(model="gemini-2.5-flash", temperature=0.8),
            tools=[
                get_weather,
                search_web
            ],
        )


async def entrypoint(ctx: agents.JobContext):
    # Initialize session ID and metadata
    session_id = f"session_{int(time.time())}"
    set_session_id(session_id)
    
    # Create a session with Cartesia TTS for Hindi voice output
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

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
        room_output_options=RoomOutputOptions(
            audio_enabled=True,  # Enable audio output for agent replies
        ),
    )

    # Start history watcher AFTER session starts
    await session_manager.start_history_watcher()

    await session.generate_reply(
        instructions=SESSION_INSTRUCTION
    )


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
