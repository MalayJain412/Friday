from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import os
import json

app = FastAPI()
templates = Jinja2Templates(directory="templates")

def read_prompt():
    with open("prompts.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["AGENT_INSTRUCTION"]

def update_prompt(new_prompt):
    with open("prompts.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    data["AGENT_INSTRUCTION"] = new_prompt
    with open("prompts.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def read_prompts():
    with open("prompts.json", "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/api/prompts")
async def get_prompts():
    return read_prompts()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    prompt = read_prompt()
    return templates.TemplateResponse("index.html", {"request": request, "prompt": prompt})

@app.post("/update")
async def update(request: Request, prompt: str = Form(...)):
    update_prompt(prompt)
    return RedirectResponse(url="/", status_code=303)