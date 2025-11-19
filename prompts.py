import json

with open("prompts.json", "r", encoding="utf-8") as f:
    data = json.load(f)

AGENT_INSTRUCTION = data["AGENT_INSTRUCTION"]
SESSION_INSTRUCTION = data["SESSION_INSTRUCTION"]