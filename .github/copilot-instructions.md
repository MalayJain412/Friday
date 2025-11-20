# AI Coding Assistant Instructions for Friday Voice Assistant

## Project Overview
Friday is a LiveKit-based Hindi voice assistant inspired by Iron Man's JARVIS. It uses speech-to-text (Deepgram), text-to-speech (Cartesia), and conversational AI (Google Gemini) for real-time voice interactions.

## Architecture
- **Main Agent**: `cagent.py` - LiveKit agent with custom STT/TTS plugins
- **Web UI**: `prompt_manager/app.py` - FastAPI app for prompt management (hosted separately)
- **Speech Processing**: `updated_stt.py` (Deepgram), `updated_tts.py` (Cartesia)
- **Logging**: `session_manager.py`, `transcript_logger.py` - Conversation logging to JSONL/JSON files
- **Tools**: `tools.py` - Weather (wttr.in), web search (DuckDuckGo)

## Key Conventions
- **Language**: All agent responses in Hindi (Devanagari script), one sentence only
- **Persona**: Sarcastic butler style ("करूँगी, साहब", "जी बॉस", "हो जाएगा!")
- **Logging**: User/agent messages logged to `KMS/logs/conversation_*.txt` and `conversations/transcripts.jsonl`
- **Session Management**: Unique session IDs, automatic history saving on shutdown
- **Tools**: Always summarize tool outputs in responses (e.g., weather results, search summaries)

## Development Workflow
- **Run Agent**: `python -m livekit cagent.py` (requires LiveKit server)
- **Run Prompt Manager**: `cd prompt_manager && uvicorn app:app --reload` (separate host)
- **Update Prompts**: Visit http://localhost:8000 to edit prompts via web UI
- **Test Tools**: Use `mcp_pylance_mcp_s_pylanceRunCodeSnippet` for isolated testing
- **Check Logs**: Monitor `conversations/` for transcripts, `KMS/logs/` for conversations

## Code Patterns
- **Custom Plugins**: Extend LiveKit plugins in `updated_stt.py`/`updated_tts.py` for logging
- **Session Setup**: Initialize `SessionManager` after `AgentSession` creation
- **Error Handling**: Use try/except with logging, fallback to file storage
- **Async Logging**: Queue-based logging in `transcript_logger.py` for non-blocking I/O

## File Structure
- `cagent.py`: Agent definition, LiveKit integration
- `tools.py`: Function tools with `@function_tool()` decorator
- `session_manager.py`: History watching, shutdown callbacks
- `config.py`: Shared log path management
- `prompts.py`: Conditional prompt loading (local or API)
- `prompt_manager/`: Separate FastAPI app for prompt management
  - `app.py`: Web UI and API for prompts
  - `templates/`: Jinja2 templates
  - `prompts.json`: Prompt data (when hosted separately)
- `prompts.json`: Local prompt data (for LOCAL_APP=true)

## Common Tasks
- **Add Tool**: Define function in `tools.py`, import in `cagent.py`, add to Agent.tools
- **Modify Persona**: Edit `prompts.json` AGENT_INSTRUCTION
- **Debug Speech**: Check STT/TTS logs in conversation files
- **Session Tracking**: Use `generate_session_id()` for unique identifiers

## Dependencies
- LiveKit agents with Google, Deepgram, Cartesia plugins
- FastAPI for web UI, langchain for search, requests for weather
- MongoDB optional (fallback to file logging)

## Environment Variables
- `LOCAL_APP=true`: Load prompts from local `prompts.json`
- `LOCAL_APP=false`: Load prompts from `PROMPT_API_URL` API
- `PROMPT_API_URL`: URL of the prompt manager API (default: http://localhost:8000/api/prompts)

Focus on Hindi responses, comprehensive logging, and LiveKit agent patterns.