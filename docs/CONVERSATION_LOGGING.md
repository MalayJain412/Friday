# Unified Conversation Logging Setup

This document describes how to log both user and agent messages to a single file per session in your LiveKit assistant project.

---

## 1. `config.py`
**Purpose:** Centralized management of the conversation log file path.

```python
# d:/ML Folders/ml_env/GitHub/Friday/config.py
_conversation_log_path = None

def set_conversation_log_path(path: str):
    global _conversation_log_path
    _conversation_log_path = path

def get_conversation_log_path() -> str:
    if _conversation_log_path is None:
        raise RuntimeError("Conversation log path not set!")
    return _conversation_log_path
```

---

## 2. `cagent.py`
**Purpose:** Generate the log file path at script start and set it in `config.py`.

```python
# d:/ML Folders/ml_env/GitHub/Friday/cagent.py
import os
import datetime
import config

def setup_conversation_log():
    log_dir = os.path.join(os.path.dirname(__file__), "KMS", "logs")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"conversation_{timestamp}.txt")
    config.set_conversation_log_path(log_path)

setup_conversation_log()
```
*Insert after your imports, before any session/agent creation.*

---

## 3. `tts.py` (Cartesia TTS plugin)
**Purpose:** Use the shared log file for agent messages.

```python
# d:/ML Folders/ml_env/Lib/site-packages/livekit/plugins/cartesia/tts.py
from __future__ import annotations
import config
# ...existing code...

class ChunkedStream(tts.ChunkedStream):
    # ...existing code...
    def _log_tts_input(self, text: str) -> None:
        try:
            log_file = config.get_conversation_log_path()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"agent: {text}\n")
        except Exception:
            pass

class SynthesizeStream(tts.SynthesizeStream):
    # ...existing code...
    def _log_tts_input(self, text: str) -> None:
        try:
            log_file = config.get_conversation_log_path()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"agent: {text}\n")
        except Exception:
            pass
```
*Remove any previous file path generation logic and use only `config.get_conversation_log_path()`.*

---

## 4. `stt.py` (Deepgram STT plugin)
**Purpose:** Use the shared log file for user messages.

```python
# d:/ML Folders/ml_env/Lib/site-packages/livekit/plugins/deepgram/stt.py
from __future__ import annotations
import config
# ...existing code...

class SpeechStream(stt.SpeechStream):
    # ...existing code...
    def _log_stt_output(self, text: str) -> None:
        try:
            log_file = config.get_conversation_log_path()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"user: {text}\n")
        except Exception:
            pass
```
*Remove any previous file path generation logic and use only `config.get_conversation_log_path()`.*

---

## Summary
- The log file is generated once per session in `cagent.py` and set in `config.py`.
- Both plugins (`tts.py` and `stt.py`) use `config.get_conversation_log_path()` to append their respective messages.
- All conversation data is stored in a single file per session, with clear `user:` and `agent:` prefixes.

This structure is efficient, maintainable, and easy to extend (e.g., for JSON or other formats).
