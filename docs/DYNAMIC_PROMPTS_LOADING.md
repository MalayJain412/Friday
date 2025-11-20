# Dynamic Prompts Loading for Friday Voice Assistant

## Overview

This document describes the implementation of dynamic prompt loading for the Friday LiveKit voice assistant. The current setup requires restarting the bot whenever prompts are updated via the web interface. This guide provides solutions to enable automatic prompt updates without manual restarts.

## Problem Statement

- **Current Issue**: After updating prompts in the FastAPI web UI (`prompt_manager/app.py`), the LiveKit bot must be manually restarted to load new instructions
- **Impact**: Disrupts ongoing conversations and requires manual intervention
- **Goal**: Enable seamless prompt updates that take effect automatically

## Current Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web UI        │    │   LiveKit Bot    │    │   Prompts API   │
│   (FastAPI)     │◄──►│   (cagent.py)    │◄──►│  (/api/prompts) │
│                 │    │                  │    │                 │
│ - Edit prompts  │    │ - Loads prompts  │    │ - Serves JSON   │
│ - Save changes  │    │   at startup     │    │ - Static data   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

**Key Components:**
- `prompt_manager/app.py`: FastAPI web interface for prompt editing
- `cagent.py`: LiveKit voice agent with static prompt loading
- `prompts.py`: Conditional prompt loading (local file vs API)
- Environment variables: `LOCAL_APP`, `PROMPT_API_URL`

## Implementation Approaches

### Approach 1: Periodic Polling (Recommended)

**Description**: Background task periodically checks for prompt updates and reloads them automatically.

**Pros**:
- Simple implementation
- No additional infrastructure needed
- Reliable fallback behavior

**Cons**:
- Updates not instantaneous (30-second delay)
- Unnecessary API calls when prompts haven't changed

### Approach 2: Webhook Notifications

**Description**: FastAPI app sends HTTP notification to bot when prompts are updated.

**Pros**:
- Instant updates
- Efficient (no polling overhead)

**Cons**:
- Requires additional HTTP server in bot
- More complex setup
- Potential for missed notifications

## Recommended Implementation: Periodic Polling

### 1. Enhanced prompts.py

```python
import json
import os
import requests
import logging
import time
from typing import Dict, Any

# Global prompt storage with caching
_prompts_data: Dict[str, Any] = {}
_last_loaded = 0
CACHE_DURATION = 30  # seconds

def load_prompts(force_refresh: bool = False) -> Dict[str, Any]:
    """Load prompts with caching support"""
    global _prompts_data, _last_loaded

    current_time = time.time()

    # Check if cache is still valid
    if not force_refresh and (current_time - _last_loaded) < CACHE_DURATION and _prompts_data:
        return _prompts_data

    LOCAL_APP = os.getenv("LOCAL_APP", "true").lower() == "true"

    try:
        if LOCAL_APP:
            # Load from local file
            with open("prompts.json", "r", encoding="utf-8") as f:
                _prompts_data = json.load(f)
        else:
            # Load from API
            api_url = os.getenv("PROMPT_API_URL", "http://localhost:8000/api/prompts")
            response = requests.get(api_url, timeout=5)
            response.raise_for_status()
            _prompts_data = response.json()

        _last_loaded = current_time
        logging.info("Prompts loaded/updated")

    except Exception as e:
        logging.error(f"Failed to load prompts: {e}")
        # Keep existing prompts if available, otherwise use defaults
        if not _prompts_data:
            _prompts_data = {
                "AGENT_INSTRUCTION": "You are Friday, a helpful assistant.",
                "SESSION_INSTRUCTION": "Please assist the user."
            }

    return _prompts_data

# Initial load
_prompts_data = load_prompts()

# Expose as module-level variables (these can be updated)
AGENT_INSTRUCTION = _prompts_data.get("AGENT_INSTRUCTION", "")
SESSION_INSTRUCTION = _prompts_data.get("SESSION_INSTRUCTION", "")

def update_global_prompts():
    """Update the global prompt variables"""
    global AGENT_INSTRUCTION, SESSION_INSTRUCTION, _prompts_data
    _prompts_data = load_prompts(force_refresh=True)
    AGENT_INSTRUCTION = _prompts_data.get("AGENT_INSTRUCTION", "")
    SESSION_INSTRUCTION = _prompts_data.get("SESSION_INSTRUCTION", "")
```

### 2. Background Monitoring in cagent.py

```python
import asyncio
import hashlib
import requests
import logging
import os

# Global variables to track prompt state
current_prompt_hash: Optional[str] = None

async def check_for_prompt_updates():
    """Background task to check for prompt updates every 30 seconds"""
    global current_prompt_hash

    while True:
        try:
            # Only check if using API mode
            if os.getenv("LOCAL_APP", "true").lower() != "true":
                api_url = os.getenv("PROMPT_API_URL", "http://localhost:8000/api/prompts")
                response = requests.get(api_url, timeout=5)
                response.raise_for_status()
                new_prompts = response.json()

                # Calculate hash of current prompts
                prompt_content = f"{new_prompts.get('AGENT_INSTRUCTION', '')}{new_prompts.get('SESSION_INSTRUCTION', '')}"
                new_hash = hashlib.md5(prompt_content.encode()).hexdigest()

                # Check if prompts changed
                if current_prompt_hash is None:
                    # First load
                    current_prompt_hash = new_hash
                    logging.info("Initial prompts loaded via polling")
                elif new_hash != current_prompt_hash:
                    # Prompts updated - reload them
                    current_prompt_hash = new_hash
                    prompts.update_global_prompts()
                    logging.info("Prompts updated dynamically via polling")

        except Exception as e:
            logging.warning(f"Failed to check for prompt updates: {e}")

        await asyncio.sleep(30)  # Check every 30 seconds

async def entrypoint(ctx: agents.JobContext):
    # ... existing initialization code ...

    # Start prompt update checker (only in API mode)
    if os.getenv("LOCAL_APP", "true").lower() != "true":
        asyncio.create_task(check_for_prompt_updates())

    # ... rest of entrypoint ...
```

### 3. Environment Configuration

Add to `.env`:

```bash
# Dynamic Prompts Configuration
LOCAL_APP=false  # Set to false to enable API mode
PROMPT_API_URL=http://localhost:8000/api/prompts
PROMPT_CHECK_INTERVAL=30  # seconds between checks
```

## Alternative Implementation: Webhook Approach

### Webhook Server in Bot

```python
# Add to cagent.py
from aiohttp import web
import threading

async def prompt_update_webhook(request):
    """Webhook endpoint for prompt updates"""
    try:
        # Trigger prompt reload
        prompts.update_global_prompts()
        logging.info("Prompts updated via webhook")
        return web.Response(text="Prompts updated")
    except Exception as e:
        logging.error(f"Webhook update failed: {e}")
        return web.Response(status=500, text="Update failed")

def start_webhook_server():
    """Start simple webhook server on separate thread"""
    app = web.Application()
    app.router.add_post('/webhook/prompts', prompt_update_webhook)

    def run_server():
        web.run_app(app, host='localhost', port=8081)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

# Start webhook server in entrypoint
async def entrypoint(ctx: agents.JobContext):
    # ... existing code ...

    # Start webhook server for prompt updates
    start_webhook_server()

    # ... rest of entrypoint ...
```

### Webhook Notification from FastAPI

```python
# Add to prompt_manager/app.py
import requests

def notify_bot_of_prompt_update():
    """Notify the bot that prompts have been updated"""
    try:
        webhook_url = "http://localhost:8081/webhook/prompts"
        requests.post(webhook_url, timeout=2)
    except Exception as e:
        print(f"Failed to notify bot: {e}")

@app.post("/update")
async def update(request: Request, prompt: str = Form(...)):
    update_prompt(prompt)
    notify_bot_of_prompt_update()  # Notify bot immediately
    return RedirectResponse(url="/", status_code=303)
```

## LiveKit Agent Considerations

### Current Limitation
The LiveKit `Agent` class sets instructions during initialization:
```python
class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,  # Set once at creation
            # ...
        )
```

### Potential Solutions

1. **Check for Dynamic Updates**: Verify if LiveKit Agent supports instruction updates
2. **Session-Level Updates**: Update instructions at the session level if supported
3. **Agent Recreation**: Recreate agent instances when prompts change (complex)
4. **Global Variable Updates**: Rely on the global variables being updated and hope the agent uses current values

### Recommended Approach
For immediate implementation, use the global variable updates. If the LiveKit Agent doesn't dynamically reload instructions, consider:

- Updating between sessions only
- Adding a manual "Apply Changes" button that recreates the agent
- Checking LiveKit documentation for dynamic instruction support

## Testing and Validation

### Test Scenarios

1. **Prompt Update Detection**:
   ```bash
   # Update prompts via web UI
   # Check bot logs for "Prompts updated dynamically" message
   ```

2. **API Failure Handling**:
   ```bash
   # Stop the prompt manager API
   # Verify bot continues with cached prompts
   # Restart API and check automatic recovery
   ```

3. **Cache Behavior**:
   ```bash
   # Update prompts
   # Verify immediate update (webhook) or within 30 seconds (polling)
   ```

### Monitoring

Add logging to track:
- Prompt update events
- API call success/failure
- Cache hit/miss ratios
- Fallback activations

### Health Checks

```python
# Add to prompt_manager/app.py
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "bot_webhook": check_bot_webhook(),
        "last_prompt_update": get_last_update_time()
    }
```

## Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `LOCAL_APP` | `true` | Use local file (true) or API (false) |
| `PROMPT_API_URL` | `http://localhost:8000/api/prompts` | API endpoint URL |
| `PROMPT_CHECK_INTERVAL` | `30` | Polling interval in seconds |
| `WEBHOOK_PORT` | `8081` | Port for bot webhook server |

## Deployment Considerations

### Development
- Use polling approach for simplicity
- Keep `LOCAL_APP=true` for local development
- Test with both approaches

### Production
- Use webhook approach for instant updates
- Implement proper error handling and monitoring
- Consider authentication for webhook endpoints
- Add rate limiting to prevent abuse

### Scaling
- For multiple bot instances, use shared cache (Redis)
- Implement centralized prompt management
- Consider database-backed prompt storage

## Troubleshooting

### Common Issues

1. **Prompts not updating**:
   - Check `LOCAL_APP` setting
   - Verify API connectivity
   - Check bot logs for errors

2. **Webhook failures**:
   - Ensure bot is running and webhook server started
   - Check firewall settings
   - Verify webhook URL configuration

3. **Performance issues**:
   - Adjust polling interval
   - Implement caching optimizations
   - Monitor API response times

### Debug Commands

```bash
# Check current prompts
curl http://localhost:8000/api/prompts

# Test webhook (if implemented)
curl -X POST http://localhost:8081/webhook/prompts

# Check bot logs
tail -f logs/bot.log | grep -i prompt
```

## Future Enhancements

1. **Advanced Caching**: Redis-based distributed caching
2. **A/B Testing**: Support for prompt variants
3. **Audit Logging**: Track prompt changes and usage
4. **Rollback Support**: Ability to revert to previous prompts
5. **Real-time Metrics**: Monitor prompt performance

## Conclusion

The periodic polling approach provides the best balance of simplicity and reliability for the current Friday architecture. It enables automatic prompt updates without requiring complex infrastructure changes, while maintaining backward compatibility with the existing setup.

For production deployments, consider implementing the webhook approach for instant updates and better resource utilization.</content>
<parameter name="filePath">c:\Users\int10281\Desktop\Github\Friday\docs\DYNAMIC_PROMPTS_LOADING.md