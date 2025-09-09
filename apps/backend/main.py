# main.py — Step 16: Scoring (Rubric) + persist to 'scores'
from __future__ import annotations

import os, json, uuid
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql import text

try:
    from litellm import acompletion
    LITELLM_OK = True
except Exception:
    LITELLM_OK = False

# ── Config
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in .env")
engine = create_async_engine(DATABASE_URL, future=True, pool_pre_ping=True)
GEMINI_MODEL = os.getenv("CHAT_MODEL", "gemini/gemini-1.5-flash-latest")

# ── FastAPI + CORS
app = FastAPI(title="AI Interview Trainer API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Models
class StartSessionRequest(BaseModel):
    role_profile: str

class StartSessionResponse(BaseModel):
    session_id: uuid.UUID
    first_question: str

class AnswerRequest(BaseModel):
    session_id: uuid.UUID
    answer_text: str

class Scores(BaseModel):
    content: int = Field(..., ge=0, le=100)
    structure: int = Field(..., ge=0, le=100)
    communication: int = Field(..., ge=0, le=100)  # maps to 'comms'

class Feedback(BaseModel):
    bullets: List[str]
    scores: Scores
    citations: List[dict] = []

class AnswerResponse(BaseModel):
    feedback: Feedback
    next_question: Optional[str] = None

# ── DB helpers
async def db_one(q: str, p: dict) -> Optional[dict]:
    async with engine.begin() as c:
        r = await c.execute(text(q), p)
        m = r.mappings().first()
        return dict(m) if m else None

async def db_all(q: str, p: dict) -> List[dict]:
    async with engine.begin() as c:
        r = await c.execute(text(q), p)
        return [dict(x) for x in r.mappings().all()]

async def db_exec(q: str, p: dict) -> None:
    async with engine.begin() as c:
        await c.execute(text(q), p)

# ── Prompt (strict JSON)
def build_scoring_prompt(latest_answer: str, role_profile: str, history: List[dict]) -> List[dict]:
    hist = "\n".join([f"Q: {h.get('q_text','')}\nA: {h.get('a_text','')}" for h in history])
    system = f"""
You are a strict but fair interview coach hiring for a '{role_profile}' role.
Analyze ONLY the candidate's LATEST answer, but use the entire conversation history to AVOID repetition.
Respond with ONLY valid JSON:
{{
  "feedback_bullets": ["...", "..."],        // 1–2 NEW, non-repetitive bullets
  "scores": {{
    "content": <int 0-100>,
    "structure": <int 0-100>,
    "communication": <int 0-100>
  }}
}}
Do not include any other text.
CONVERSATION HISTORY:
{hist}
""".strip()
    user = f"CANDIDATE'S LATEST ANSWER:\n'{latest_answer}'"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]

def smart_json_parse(raw: str) -> Dict[str, Any]:
    try:
        return json.loads(raw)
    except Exception:
        s, e = raw.find("{"), raw.rfind("}")
        if s != -1 and e != -1 and e > s:
            return json.loads(raw[s:e+1])
        raise

def fallback_json() -> Dict[str, Any]:
    return {
        "feedback_bullets": [
            "Använd STAR och konkretisera dina handlingar.",
            "Kvantifiera resultat (t.ex. +X%, −Y fel, Z användare).",
        ],
        "scores": {"content": 55, "structure": 50, "communication": 60},
    }

def next_question(role_profile: str, history: List[dict]) -> str:
    return "Ge ett konkret exempel på mätbart resultat (R i STAR): vad blev effekten och hur verifierade du den?"

# ── Endpoints
@app.get("/", tags=["Health"])
async def health():
    return {"message": "AI Interview Trainer API is running"}

@app.post("/session/start", response_model=StartSessionResponse, tags=["Interview"])
async def start_session(req: StartSessionRequest):
    sid = uuid.uuid4()
    first_q = f"Välkommen. För rollen '{req.role_profile}', berätta om ett projekt du är stolt över."
    await db_exec(
        "INSERT INTO sessions (id, user_id, role_profile) VALUES (:id, :uid, :role)",
        {"id": str(sid), "uid": None, "role": req.role_profile},
    )
    await db_exec(
        "INSERT INTO turns (id, session_id, q_text) VALUES (:id, :sid, :q)",
        {"id": str(uuid.uuid4()), "sid": str(sid), "q": first_q},
    )
    return StartSessionResponse(session_id=sid, first_question=first_q)

@app.post("/session/answer", response_model=AnswerResponse, tags=["Interview"])
async def process_answer(req: AnswerRequest):
    # 1) Session + historik
    sess = await db_one("SELECT role_profile FROM sessions WHERE id = :sid", {"sid": str(req.session_id)})
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    role_profile = sess["role_profile"]

    hist = await db_all(
        "SELECT id, q_text, a_text FROM turns WHERE session_id = :sid ORDER BY created_at ASC",
        {"sid": str(req.session_id)},
    )
    last_q = (hist[-1]["q_text"] if hist else "Initial question")

    # 2) Skapa turn för kandidatens svar (denna turn_id får score)
    turn_id = str(uuid.uuid4())
    await db_exec(
        "INSERT INTO turns (id, session_id, q_text, a_text) VALUES (:id, :sid, :q, :a)",
        {"id": turn_id, "sid": str(req.session_id), "q": last_q, "a": req.answer_text},
    )

    # 3) Scoring via LLM (robust)
    try:
        msgs = build_scoring_prompt(req.answer_text, role_profile, hist)
        if LITELLM_OK:
            resp = await acompletion(model=GEMINI_MODEL, messages=msgs)
            raw = resp.choices[0].message.content
            parsed = smart_json_parse(raw)
        else:
            parsed = fallback_json()
    except Exception:
        parsed = fallback_json()

    s = parsed.get("scores", {}) or {}
    content = int(s.get("content", 0))
    structure = int(s.get("structure", 0))
    communication = int(s.get("communication", 0))

    # 4) Persist poäng
    await db_exec(
        "INSERT INTO scores (turn_id, content, structure, comms) VALUES (:tid, :c, :s, :m)",
        {"tid": turn_id, "c": content, "s": structure, "m": communication},
    )

    # 5) Nästa fråga
    nq = next_question(role_profile, hist)
    await db_exec(
        "INSERT INTO turns (id, session_id, q_text) VALUES (:id, :sid, :q)",
        {"id": str(uuid.uuid4()), "sid": str(req.session_id), "q": nq},
    )

    # 6) Return
    feedback = Feedback(
        bullets=parsed.get("feedback_bullets", ["(no feedback)"]),
        scores=Scores(content=content, structure=structure, communication=communication),
        citations=[],
    )
    return AnswerResponse(feedback=feedback, next_question=nq)