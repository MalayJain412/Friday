import json
import os
import requests

LOCAL_APP = os.getenv("LOCAL_APP", "true").lower() == "true"

if LOCAL_APP:
    # Load from local file
    with open("prompts.json", "r", encoding="utf-8") as f:
        data = json.load(f)
else:
    # Load from API
    api_url = os.getenv("PROMPT_API_URL", "http://localhost:8000/api/prompts")
    response = requests.get(api_url)
    response.raise_for_status()
    data = response.json()

AGENT_INSTRUCTION = data["AGENT_INSTRUCTION"]
SESSION_INSTRUCTION = data["SESSION_INSTRUCTION"]