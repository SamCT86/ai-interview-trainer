import os, uuid, logging, asyncio
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import openai

# ---------- Env ----------
openai.api_key = os.getenv("OPENAI_API_KEY", "")

app = FastAPI(title="AI Interview Trainer API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- DB (lazy) ----------
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
DATABASE_URL = os.getenv("DATABASE_URL", "")
engine = None
if DATABASE_URL:
    try:
        engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=180)
    except Exception as e:
        logging.exception("DB init failed – using in-memory fallback")

# ---------- In-memory store ----------
mem_sessions: Dict[str, Dict] = {}

# ---------- Models ----------
class StartPayload(BaseModel):
    role_profile: str

class AnswerPayload(BaseModel):
    session_id: str
    answer_text: str

# ---------- LLM helpers ----------
SYSTEM_PROMPTS = {
    "Junior Developer": "You are a friendly senior dev interviewer. Ask ONE concise, open question about React, testing, or teamwork. Avoid repeats.",
    "Project Manager": "You are a senior PM. Ask ONE concise question about backlog, risk, or stakeholder communication. Avoid repeats.",
}

def build_messages(role: str, history: List[str]) -> List[dict]:
    msgs = [{"role": "system", "content": SYSTEM_PROMPTS.get(role, SYSTEM_PROMPTS["Junior Developer"])}]
    for h in history:
        msgs.append({"role": "user", "content": h})
    return msgs

def ask_llm(role: str, history: List[str]) -> str:
    if not openai.api_key:
        # Fallback – unik varje gång
        return f"Tell me about a {role.lower()} challenge you solved recently – be specific."

    msgs = build_messages(role, history)
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=msgs,
            max_tokens=80,
            temperature=0.9,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logging.exception("LLM failed – fallback")
        return f"Describe a recent {role.lower()} situation – what did you do?"

# ---------- Routes ----------
@app.get("/")
async def health():
    return {"message": "AI Interview Trainer API is running", "llm": bool(openai.api_key)}

@app.post("/session/start")
async def start_session(p: StartPayload):
    role = p.role_profile or "Junior Developer"
    sid = str(uuid.uuid4())
    asyncio.create_task(ensure_schema())  # non-blocking
    first = ask_llm(role, [])
    mem_sessions[sid] = {"role": role, "history": [], "idx": 0}
    return {"session_id": sid, "first_question": first}

@app.post("/session/answer")
async def send_answer(p: AnswerPayload):
    s = mem_sessions.get(p.session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    s["history"].append(p.answer_text)
    next_q = ask_llm(s["role"], s["history"])
    s["history"].append(next_q)
    feedback = [
        "Utveckla gärna med konkreta exempel." if len(p.answer_text) 