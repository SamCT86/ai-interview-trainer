import os, uuid, logging, asyncio
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime

app = FastAPI(title="AI Interview Trainer API", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- DB (lazy init) ----------
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

# ---------- Questions ----------
FIRST_QUESTIONS = {
    "Junior Developer": "Berätta kort om ett projekt där du använde React.",
    "Project Manager": "Hur prioriterar du backloggen inför en release?",
}
FOLLOWUP = {
    "Junior Developer": [
        "Hur testade du din React-kod?",
        "Hur hanterade du state management?",
    ],
    "Project Manager": [
        "Hur hanterade du risker i projektet?",
        "Hur följde du upp teamets velocity?",
    ],
}

# ---------- Models ----------
class StartPayload(BaseModel):
    role_profile: str

class AnswerPayload(BaseModel):
    session_id: str
    answer_text: str

# ---------- Helpers ----------
async def ensure_schema():
    if not engine:
        return
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                role TEXT,
                created_at TIMESTAMP
            );
        """))

def make_feedback(answer: str) -> List[str]:
    bullets = []
    if len(answer.strip()) < 20:
        bullets.append("Utveckla svaret med mer konkreta detaljer.")
    if "test" not in answer.lower():
        bullets.append("Nämn hur du verifierade kvalitet (tester/QA).")
    if "team" not in answer.lower():
        bullets.append("Reflektera över samarbete eller kommunikation.")
    return bullets

# ---------- Routes ----------
@app.get("/")
async def health():
    return {"message": "AI Interview Trainer API is running"}

@app.post("/session/start")
async def start_session(p: StartPayload):
    role = p.role_profile or "Junior Developer"
    sid = str(uuid.uuid4())

    # Starta DB i bakgrunden – vi väntar INTE
    asyncio.create_task(ensure_schema())

    mem_sessions[sid] = {"role": role, "idx": 0, "answers": []}
    return {"session_id": sid, "first_question": FIRST_QUESTIONS[role]}

@app.post("/session/answer")
async def send_answer(p: AnswerPayload):
    s = mem_sessions.get(p.session_id)
    if not s:
        raise HTTPException(404, "Session not found")

    role = s["role"]
    idx = s["idx"]
    s["answers"].append(p.answer_text)
    fb = make_feedback(p.answer_text)

    follow = FOLLOWUP.get(role, [])
    next_q = follow[idx] if idx < len(follow) else None
    if next_q:
        s["idx"] += 1

    return {"feedback": {"bullets": fb}, "next_question": next_q}

@app.get("/session/{sid}/report")
async def report(sid: str):
    s = mem_sessions.get(sid)
    if not s:
        raise HTTPException(404, "Session not found")
    penalty = sum(len(make_feedback(a)) for a in s["answers"])
    overall = max(40, 100 - penalty * 8)
    return {
        "metrics": {
            "avg_content": overall,
            "avg_structure": overall,
            "avg_communication": overall,
            "overall_avg": overall,
        },
        "final_summary": "Demo-rapport: förbättra detaljer, tester och team-samarbete.",
    }