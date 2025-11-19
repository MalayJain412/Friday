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

# MongoDB integration disabled
USE_MONGODB = False
_current_session_id = None
_current_dialed_number = None
_current_session_manager = None

MONGODB_AVAILABLE = False
logging.info("MongoDB integration disabled - using file storage")

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

            # Log to file
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