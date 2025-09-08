# main.py — Step 15-B: Conversational memory completed
from __future__ import annotations

import os
import uuid
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# LiteLLM (Gemini via LiteLLM)
# pip install litellm
from litellm import acompletion

# ────────────────────────────────────────────────────────────────────────────────
# Config
# ────────────────────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")  # postgresql+psycopg://...
if not DATABASE_URL:
    raise RuntimeError("Missing DATABASE_URL in environment")

# Viktigt: psycopg asyncio kräver +asyncpg eller psycopg[pool]? Vi kör psycopg v3 URL.
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, future=True)

GEMINI_MODEL = "gemini/gemini-1.5-flash-latest"  # LiteLLM alias
DEFAULT_ROLE = "Junior Developer"

# ────────────────────────────────────────────────────────────────────────────────
# FastAPI
# ────────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Interview Trainer API",
    version="1.0.0"
)

# CORS – fronten kör på http://localhost:3000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ────────────────────────────────────────────────────────────────────────────────
# Models (Pydantic)
# ────────────────────────────────────────────────────────────────────────────────
class StartRequest(BaseModel):
    role_profile: str = Field(default=DEFAULT_ROLE)

class StartResponse(BaseModel):
    session_id: uuid.UUID
    first_question: str

class AnswerRequest(BaseModel):
    session_id: uuid.UUID
    answer_text: str

class Feedback(BaseModel):
    bullets: List[str]
    citations: List[str] = []

class AnswerResponse(BaseModel):
    feedback: Feedback
    next_question: str

# ────────────────────────────────────────────────────────────────────────────────
# DB helpers (Supabase Postgres)
# ────────────────────────────────────────────────────────────────────────────────
async def db_fetchone(query: str, params: dict) -> Optional[dict]:
    async with engine.begin() as cn:
        res = await cn.execute(text(query), params)
        row = res.mappings().first()
        return dict(row) if row else None

async def db_fetchall(query: str, params: dict) -> List[dict]:
    async with engine.begin() as cn:
        res = await cn.execute(text(query), params)
        rows = res.mappings().all()
        return [dict(r) for r in rows]

async def db_execute(query: str, params: dict) -> None:
    async with engine.begin() as cn:
        await cn.execute(text(query), params)

# ────────────────────────────────────────────────────────────────────────────────
# RAG helpers (neutral fallback, stabilt)
# ────────────────────────────────────────────────────────────────────────────────
async def find_relevant_sources(user_text: str) -> List[str]:
    """
    Minimal RAG: hämtar topp 5 texter utan embeddings om embeddings ej finns.
    Om du redan har embeddings + pgvector kan du byta till:
      SELECT chunk_text FROM sources ORDER BY embedding <=> :embed LIMIT 5
    """
    try:
        rows = await db_fetchall(
            "SELECT chunk_text FROM sources ORDER BY created_at DESC LIMIT 5",
            {}
        )
        return [r["chunk_text"] for r in rows]
    except Exception:
        return []

# ────────────────────────────────────────────────────────────────────────────────
# Prompt builder – med HISTORIK
# ────────────────────────────────────────────────────────────────────────────────
def build_messages_with_history(
    latest_answer: str,
    sources: List[str],
    role_profile: str,
    history: List[dict]
) -> List[dict]:
    """
    history: [{q_text:str, a_text:str}, ...] i kronologisk ordning
    """
    history_str = ""
    for h in history:
        q = (h.get("q_text") or "").strip()
        a = (h.get("a_text") or "").strip()
        if q:
            history_str += f"Q: {q}\n"
        if a:
            history_str += f"A: {a}\n"
    sources_str = "\n".join([f"- {s}" for s in sources]) if sources else "- (no sources)"

    system = (
        "You are a strict but helpful interview coach. "
        "Use the ENTIRE conversation history to avoid repeating feedback. "
        "Always provide NEW, non-redundant guidance. "
        "Return your feedback as 3–6 concise bullet points. No long paragraphs."
    )
    user = (
        f"ROLE PROFILE: {role_profile}\n\n"
        f"CONVERSATION HISTORY (oldest→newest):\n{history_str}\n\n"
        f"LATEST ANSWER:\n{latest_answer}\n\n"
        f"SOURCES (optional):\n{sources_str}\n\n"
        "TASK:\n"
        "1) Give 3–6 non-repetitive bullet points of feedback tailored to the latest answer.\n"
        "2) Each bullet should push the candidate forward (STAR, quantify results, personal ownership, tie to role).\n"
        "3) Do NOT repeat the same phrasing as before.\n"
        "4) Only bullets, no intro/outro."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user}
    ]

def parse_bullets(text: str) -> List[str]:
    lines = [ln.strip(" •-") for ln in text.splitlines() if ln.strip()]
    # Ta bara 3–6 första "rimliga" rader
    bullets = [ln for ln in lines if len(ln) > 0]
    if not bullets:
        bullets = ["Knyt svaret till jobbet.", "Kvantifiera resultat.", "Visa ditt personliga ansvar (STAR)."]
    return bullets[:6]

def next_question_from(role_profile: str, history: List[dict]) -> str:
    """
    En enkel heuristik: fråga efter nästa STAR-del beroende på tidigare svar.
    Kan bytas mot LLM senare.
    """
    # Om senaste svaret var allmänt → styra mot 'Result'
    return "Ge ett konkret exempel med siffror på resultatet (R i STAR). Vad blev effekten och hur mätte du den?"

# ────────────────────────────────────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def root():
    return {"message": "AI Interview Trainer API is running"}

@app.post("/session/start", response_model=StartResponse, tags=["Interview"])
async def start_session(req: StartRequest):
    """
    Skapar sessions-rad och första turn (fråga) i DB.
    """
    s_id = uuid.uuid4()
    first_q = "Välkommen. För rollen '{role}', berätta om ett projekt du är stolt över.".format(role=req.role_profile)

    # sessions: (id uuid pk, role_profile text)
    await db_execute(
        "INSERT INTO sessions (id, role_profile) VALUES (:id, :role)",
        {"id": str(s_id), "role": req.role_profile}
    )
    # turns: (id uuid pk, session_id uuid fk, q_text text, a_text text null, created_at timestamptz default now())
    await db_execute(
        "INSERT INTO turns (id, session_id, q_text) VALUES (:id, :sid, :q)",
        {"id": str(uuid.uuid4()), "sid": str(s_id), "q": first_q}
    )
    return StartResponse(session_id=s_id, first_question=first_q)

@app.post("/session/answer", response_model=AnswerResponse, tags=["Interview"])
async def process_answer(req: AnswerRequest):
    """
    1) Hämtar roll + hel historik från DB
    2) Uppdaterar senaste turn med kandidatens svar
    3) Kör RAG + LLM med historik för icke-repetitiv feedback
    4) Skapar och lagrar nästa fråga
    """
    # ── 1) session & historik
    sess = await db_fetchone(
        "SELECT role_profile FROM sessions WHERE id = :id",
        {"id": str(req.session_id)}
    )
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    role_profile = sess["role_profile"]

    history = await db_fetchall(
        "SELECT q_text, a_text FROM turns WHERE session_id = :sid ORDER BY created_at ASC",
        {"sid": str(req.session_id)}
    )

    # ── 2) uppdatera senaste frågan med svaret
    await db_execute(
        """
        UPDATE turns
        SET a_text = :a
        WHERE id = (
          SELECT id FROM turns WHERE session_id = :sid ORDER BY created_at DESC LIMIT 1
        )
        """,
        {"a": req.answer_text, "sid": str(req.session_id)}
    )

    # ── 3) RAG + LLM
    try:
        sources = await find_relevant_sources(req.answer_text)
        messages = build_messages_with_history(
            latest_answer=req.answer_text,
            sources=sources,
            role_profile=role_profile,
            history=history
        )
        llm = await acompletion(model=GEMINI_MODEL, messages=messages, temperature=0.7)
        ai_text = llm.choices[0].message["content"] if isinstance(llm.choices[0].message, dict) else llm.choices[0].message.content
        bullets = parse_bullets(ai_text)
    except Exception:
        # Robust fallback – aldrig 500
        bullets = [
            "Förfina med STAR: fokus på Situation/Task → dina Actions → kvantifierade Results.",
            "Var tydlig med *din* roll och *dina* beslut.",
            "Knyt svaret till kraven för rollen: tekniker, processer, ansvar."
        ]

    # ── 4) nästa fråga + lagra
    next_q = next_question_from(role_profile, history)
    await db_execute(
        "INSERT INTO turns (id, session_id, q_text) VALUES (:id, :sid, :q)",
        {"id": str(uuid.uuid4()), "sid": str(req.session_id), "q": next_q}
    )

    return AnswerResponse(
        feedback=Feedback(bullets=bullets, citations=[]),
        next_question=next_q
    )