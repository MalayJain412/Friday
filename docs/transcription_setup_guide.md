# Complete Transcription Setup Guide for LiveKit Voice Bot

Based on the code analysis from `cagent.py`, `session_manager.py`, and related files, here's the complete setup guide for implementing transcription in a new LiveKit voice bot:

## **1. Dependencies Required**

Add these to your `requirements.txt`:

```txt
# Core LiveKit
livekit==1.0.12
livekit-agents==1.2.14
livekit-api==1.0.5

# Database & Storage
pymongo==4.15.3

# Utilities
python-dotenv==1.1.1
pytz==2025.2
```

## **2. Core Files to Create**

### **A. `logging_config.py`** - Centralized logging setup
```python
import logging
import logging.config
import os

class NoPymongoDebugFilter(logging.Filter):
    """Filter out very chatty pymongo debug messages."""
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith("pymongo") and record.levelno <= logging.DEBUG:
            return False
        return True

def configure_logging():
    """Centralized logging configuration."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)4s %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            }
        },
        "filters": {
            "no_pymongo_debug": {
                "()": NoPymongoDebugFilter
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": log_level,
                "filters": ["no_pymongo_debug"],
                "stream": "ext://sys.stdout",
            }
        },
        "root": {
            "handlers": ["console"],
            "level": log_level,
        },
        "loggers": {
            "pymongo": {"level": "WARNING", "handlers": ["console"], "propagate": False},
            "urllib3": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        },
    }

    logging.config.dictConfig(config)
```

### **B. `transcript_logger.py`** - Core transcription logging system
```python
import os
import json
import threading
import queue
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

DEFAULT_DIR = Path(__file__).parent / "conversations"
DEFAULT_DIR.mkdir(exist_ok=True)
DEFAULT_FILE = DEFAULT_DIR / "transcripts.jsonl"

_LOG_PATH_ENV = "TRANSCRIPT_LOG_PATH"
_log_path = Path(os.environ.get(_LOG_PATH_ENV, str(DEFAULT_FILE)))
_log_path.parent.mkdir(parents=True, exist_ok=True)

# MongoDB integration setup
USE_MONGODB = os.getenv("USE_MONGODB", "true").lower() == "true"
_current_session_id = None
_current_dialed_number = None
_current_session_manager = None

try:
    if USE_MONGODB:
        from db_config import TranscriptDB, ConversationDB
        MONGODB_AVAILABLE = True
        logging.info("MongoDB integration enabled for transcript logging")
    else:
        MONGODB_AVAILABLE = False
        logging.info("MongoDB integration disabled - using file storage")
except ImportError as e:
    MONGODB_AVAILABLE = False
    logging.warning(f"MongoDB not available for transcript logging, using file storage fallback: {e}")

_q: "queue.Queue[dict | object]" = queue.Queue()
_STOP = object()

def _worker() -> None:
    while True:
        item = _q.get()
        if item is _STOP:
            break
        try:
            # Sanitize the item for JSON encoding
            def _serialize_value(v):
                if v is None or isinstance(v, (str, int, float, bool)):
                    return v
                if isinstance(v, datetime):
                    return v.isoformat()
                if isinstance(v, dict):
                    return {str(k): _serialize_value(vk) for k, vk in v.items()}
                if isinstance(v, (list, tuple)):
                    return [_serialize_value(x) for x in v]
                if hasattr(v, "to_dict"):
                    try:
                        return _serialize_value(v.to_dict())
                    except Exception:
                        pass
                if hasattr(v, "toJSON"):
                    try:
                        raw = v.toJSON()
                        if isinstance(raw, str):
                            try:
                                return json.loads(raw)
                            except Exception:
                                return raw
                        return _serialize_value(raw)
                    except Exception:
                        pass
                try:
                    return str(v)
                except Exception:
                    return repr(v)

            def _sanitize_event(ev):
                if not isinstance(ev, dict):
                    return {"value": _serialize_value(ev)}
                return {str(k): _serialize_value(v) for k, v in ev.items()}

            sanitized = _sanitize_event(item)

            # Try MongoDB first if available
            if MONGODB_AVAILABLE and isinstance(sanitized, dict):
                try:
                    TranscriptDB.log_event(sanitized, _current_session_id)
                except Exception as e:
                    logging.warning(f"Failed to log to MongoDB: {e}")

            # Always log to file as backup
            with open(_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(sanitized, ensure_ascii=False) + "\n")
        except Exception:
            pass
        _q.task_done()

_worker_thread = threading.Thread(target=_worker, daemon=True)
_worker_thread.start()

def log_event(event: dict) -> None:
    """Log a transcription event"""
    try:
        _q.put_nowait(event)
    except Exception:
        try:
            with open(_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception:
            pass

def flush_and_stop(timeout: float = 2.0) -> None:
    """Flush and stop the logging worker"""
    try:
        _q.put(_STOP)
        _worker_thread.join(timeout=timeout)
    except Exception:
        pass

def get_log_path() -> str:
    return str(_log_path)

def set_session_id(session_id: str) -> None:
    """Set the current session ID for transcript logging"""
    global _current_session_id
    _current_session_id = session_id
    logging.info(f"Transcript logging session ID set to: {session_id}")

def set_dialed_number(dialed_number: str) -> None:
    """Set the current dialed number for metadata"""
    global _current_dialed_number
    _current_dialed_number = dialed_number

def set_session_manager(session_manager) -> None:
    """Set the current session manager reference"""
    global _current_session_manager
    _current_session_manager = session_manager

def get_current_session_id() -> Optional[str]:
    """Get the current session ID"""
    return _current_session_id

def generate_session_id() -> str:
    """Generate a new unique session ID"""
    session_id = f"session_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    set_session_id(session_id)
    return session_id

def save_conversation_session(items: list, metadata: Optional[dict] = None) -> Optional[str]:
    """Save complete conversation session"""
    if not items:
        return None

    session_id = _current_session_id or generate_session_id()
    
    # Calculate session metrics
    start_time = None
    end_time = None
    
    for item in items:
        if isinstance(item, dict) and "timestamp" in item:
            timestamp = item["timestamp"]
            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                except:
                    continue
            
            if start_time is None or timestamp < start_time:
                start_time = timestamp
            if end_time is None or timestamp > end_time:
                end_time = timestamp

    # Prepare session data
    session_data = {
        "session_id": session_id,
        "start_time": start_time or datetime.utcnow(),
        "end_time": end_time or datetime.utcnow(),
        "items": items,
        "total_items": len(items),
        "duration_seconds": ((end_time - start_time).total_seconds() if start_time and end_time else 0),
        "metadata": metadata or {}
    }
    
    # Try MongoDB first
    if MONGODB_AVAILABLE:
        try:
            ConversationDB.create_session(session_data)
        except Exception as e:
            logging.error(f"Error creating conversation session: {e}")
    
    # Save to file as backup
    try:
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S.%f")
        session_file = DEFAULT_DIR / f"transcript_session_{timestamp}.json"
        
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False, default=str)
        
        logging.info(f"Conversation session saved to file: {session_file}")
        return str(session_file)
        
    except Exception as e:
        logging.error(f"Failed to save session to file: {e}")
        return None
```

### **C. `db_config.py`** - MongoDB integration (optional but recommended)
```python
import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import pymongo
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "voice_bot")
MONGODB_TIMEOUT = int(os.getenv("MONGODB_TIMEOUT", "5000"))

_client: Optional[MongoClient] = None
_database = None

def get_database():
    """Get MongoDB database instance"""
    global _client, _database
    
    if _client is None:
        try:
            _client = MongoClient(
                MONGODB_URI,
                serverSelectionTimeoutMS=MONGODB_TIMEOUT,
                connectTimeoutMS=MONGODB_TIMEOUT,
                socketTimeoutMS=MONGODB_TIMEOUT
            )
            _client.admin.command('ping')
            _database = _client[MONGODB_DATABASE]
            
            # Create indexes
            _create_indexes()
            
            logging.info(f"Connected to MongoDB database: {MONGODB_DATABASE}")
            
        except Exception as e:
            logging.error(f"Failed to connect to MongoDB: {e}")
            raise
    
    return _database

def _create_indexes():
    """Create necessary indexes"""
    try:
        db = _database
        
        # Transcript events collection
        events_collection = db.transcript_events
        events_collection.create_index([("timestamp", pymongo.DESCENDING)])
        events_collection.create_index([("session_id", 1), ("timestamp", 1)])
        
        # Conversation sessions collection
        sessions_collection = db.conversation_sessions
        sessions_collection.create_index("session_id", unique=True)
        sessions_collection.create_index([("start_time", pymongo.DESCENDING)])
        
        logging.info("MongoDB indexes created")
        
    except Exception as e:
        logging.warning(f"Error creating MongoDB indexes: {e}")

class TranscriptDB:
    """Helper class for transcript operations"""
    
    @staticmethod
    def log_event(event_data: Dict[str, Any], session_id: str = None) -> bool:
        """Log a transcript event"""
        try:
            db = get_database()
            collection = db.transcript_events
            
            event_data.update({
                "session_id": session_id or "default",
                "created_at": datetime.utcnow()
            })
            
            collection.insert_one(event_data)
            return True
            
        except Exception as e:
            logging.error(f"Error logging transcript event: {e}")
            return False
    
    @staticmethod
    def get_session_events(session_id: str) -> list:
        """Get all events for a session"""
        try:
            db = get_database()
            collection = db.transcript_events
            return list(collection.find({"session_id": session_id}).sort("timestamp", 1))
        except Exception as e:
            logging.error(f"Error getting session events: {e}")
            return []

class ConversationDB:
    """Helper class for conversation session operations"""
    
    @staticmethod
    def create_session(session_data: Dict[str, Any]) -> Optional[str]:
        """Create a new conversation session"""
        try:
            db = get_database()
            collection = db.conversation_sessions
            
            session_data.update({
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            })
            
            result = collection.insert_one(session_data)
            return str(result.inserted_id)
            
        except Exception as e:
            logging.error(f"Error creating conversation session: {e}")
            return None
```

### **D. `session_manager.py`** - Session lifecycle management
```python
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from livekit.agents import AgentSession
from livekit.agents.job import get_job_context

from transcript_logger import (
    log_event,
    get_log_path,
    flush_and_stop,
    generate_session_id,
    save_conversation_session,
)

class SessionManager:
    def __init__(self, session: AgentSession):
        self.session = session
        self.watch_task: Optional[asyncio.Task] = None
        self.last_user_activity: Optional[datetime] = None
        self.campaign_metadata = {}
        
    async def setup_session_logging(self):
        """Setup session logging and generate session ID"""
        try:
            sid = generate_session_id()
            logging.info(f"Transcript logging session id: {sid}")
        except Exception:
            pass
    
    async def setup_shutdown_callback(self):
        """Setup shutdown callback to save final session history"""
        async def _save_history_on_shutdown():
            try:
                # Extract session history
                try:
                    payload = self.session.history.toJSON()
                except Exception:
                    try:
                        payload = self.session.history.to_json()
                    except Exception:
                        try:
                            payload = self.session.history.to_dict()
                        except Exception:
                            payload = str(self.session.history)

                # Save raw transcript as backup
                timestamp = datetime.utcnow().isoformat().replace(":", "-")
                room_name = getattr(self.session, "room", None)
                room_name = getattr(room_name, "name", "session") if room_name else "session"
                fname = Path(get_log_path()).with_name(f"transcript_{room_name}_{timestamp}.json")
                with open(fname, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                print(f"Transcript saved to {fname}")
                
            except Exception as e:
                log_event({
                    "role": "system",
                    "event": "shutdown_save_failed",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            finally:
                try:
                    flush_and_stop()
                except Exception:
                    pass

        # Register shutdown saver
        try:
            job_ctx = get_job_context()
            job_ctx.add_shutdown_callback(_save_history_on_shutdown)
        except Exception:
            pass

    async def start_history_watcher(self):
        """Start background watcher that polls session.history and logs new items"""
        logging.info("SessionManager: starting history watcher")
        
        async def _watch_history_and_log():
            seen_ids = set()
            try:
                while True:
                    try:
                        hist = getattr(self.session, "history", None)
                        items = None
                        if hist is None:
                            items = None
                        else:
                            if hasattr(hist, "items"):
                                items = getattr(hist, "items")
                            else:
                                try:
                                    d = hist.to_dict()
                                    items = d.get("items") if isinstance(d, dict) else None
                                except Exception:
                                    try:
                                        d = hist.to_json()
                                        import json as _json
                                        dd = _json.loads(d) if isinstance(d, str) else d
                                        items = dd.get("items") if isinstance(dd, dict) else None
                                    except Exception:
                                        try:
                                            d = hist.toJSON()
                                            import json as _json2
                                            dd = _json2.loads(d) if isinstance(d, str) else d
                                            items = dd.get("items") if isinstance(dd, dict) else None
                                        except Exception:
                                            items = None

                        if items:
                            for it in items:
                                try:
                                    itid = None
                                    if isinstance(it, dict):
                                        itid = it.get("id")
                                    else:
                                        itid = str(it)
                                    if itid in seen_ids:
                                        continue
                                    seen_ids.add(itid)

                                    role = it.get("role") if isinstance(it, dict) else "unknown"
                                    content = it.get("content") if isinstance(it, dict) else None
                                    if isinstance(content, list):
                                        content = " ".join([str(c) for c in content])
                                    elif content is None:
                                        content = ""

                                    evt = {
                                        "role": role,
                                        "content": content,
                                        "timestamp": datetime.utcnow().isoformat() + "Z",
                                        "source": "session_history",
                                        "item_type": it.get("type") if isinstance(it, dict) else None,
                                        "raw": it,
                                    }

                                    log_event(evt)
                                    
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                return

        self.watch_task = asyncio.create_task(_watch_history_and_log())
    
    def set_campaign_metadata(self, metadata: dict):
        """Store campaign metadata"""
        self.campaign_metadata = metadata.copy()
        logging.info(f"SessionManager: Campaign metadata set: {metadata}")
```

## **3. Integration in Main Agent (`cagent.py`)**

Add this to your main agent entrypoint:

```python
import os
from dotenv import load_dotenv
import logging
from logging_config import configure_logging
from transcript_logger import set_current_session_id, set_dialed_number, set_session_manager

from livekit.agents import AgentSession, Agent, JobContext
# ... other imports ...

# Setup logging early
try:
    configure_logging()
except Exception:
    logging.basicConfig(level=logging.INFO)

async def entrypoint(ctx: JobContext):
    # Initialize session ID and metadata
    session_id = f"session_{int(time.time())}"
    set_current_session_id(session_id)
    
    # Create agent session
    session = AgentSession(
        stt=instances["stt"],
        llm=instances["llm"],
        tts=instances["tts"],
        vad=instances["vad"],
    )

    # Initialize session manager
    session_manager = SessionManager(session)
    set_session_manager(session_manager)
    
    # Setup transcription logging
    await session_manager.setup_session_logging()
    await session_manager.setup_shutdown_callback()
    
    # Start the session
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(audio_enabled=True, close_on_disconnect=False),
        room_output_options=RoomOutputOptions(audio_enabled=True),
    )

    # Start history watcher AFTER session starts
    await session_manager.start_history_watcher()
    
    # ... rest of your agent logic ...
```

## **4. Environment Variables**

Add to your `.env` file:

```env
# Logging
LOG_LEVEL=INFO
TRANSCRIPT_LOG_PATH=./conversations/transcripts.jsonl

# MongoDB (optional)
USE_MONGODB=true
MONGODB_URI=mongodb://localhost:27017/
MONGODB_DATABASE=voice_bot
MONGODB_TIMEOUT=5000
```

## **5. Directory Structure**

Create these directories:
```
your-project/
├── conversations/          # Saved conversation files
├── logging_config.py       # Logging setup
├── transcript_logger.py    # Core logging system
├── session_manager.py      # Session management
├── db_config.py           # MongoDB integration
├── cagent.py              # Main agent
└── requirements.txt       # Dependencies
```

## **6. Key Features Implemented**

1. **Real-time Logging**: Captures every message, tool call, and system event
2. **Session Management**: Tracks conversation lifecycle with metadata
3. **Dual Storage**: MongoDB + file backup
4. **Automatic Session Saving**: Saves complete conversations on shutdown
5. **Structured Events**: All transcription data is properly formatted
6. **Background Processing**: Non-blocking logging with queue system

## **7. Usage Examples**

```python
# Log custom events
from transcript_logger import log_event

log_event({
    "type": "custom_event",
    "data": "your_data",
    "timestamp": datetime.utcnow().isoformat() + "Z"
})

# Save conversation manually
from transcript_logger import save_conversation_session
save_conversation_session(items_list, metadata={"custom": "data"})
```

This setup provides a complete, production-ready transcription system that captures all conversation data, supports both real-time and batch processing, and includes robust error handling and fallback mechanisms.