# main.py – hardened MVP backend (FastAPI)
from __future__ import annotations

import os
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---- LiteLLM (LLM + embeddings) --------------------------------------------
# If LiteLLM missing or API key unset, we will fallback gracefully.
try:
    from litellm import acompletion, aembedding
    LITELLM_OK = True
except Exception:
    LITELLM_OK = False

# ----------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ai-interview-trainer")

app = FastAPI(title="AI Interview Trainer API", version="1.0.0")

# CORS for Next.js on localhost:3000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store (MVP)
# session_id -> {"role_profile": str, "history": List[Dict[str, str]]}
SESSIONS: Dict[str, Dict[str, Any]] = {}

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # should be set in the terminal running uvicorn
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-004")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gemini/gemini-1.5-flash-latest")


# ==== Pydantic models ========================================================

class StartSessionRequest(BaseModel):
    role_profile: str = Field(..., description="Ex: 'Junior Backend Developer'")


class StartSessionResponse(BaseModel):
    session_id: uuid.UUID
    first_question: str


class AnswerRequest(BaseModel):
    session_id: uuid.UUID
    answer_text: str


class Feedback(BaseModel):
    bullets: List[str] = []
    sources: List[str] = []


class AnswerResponse(BaseModel):
    feedback: Feedback
    next_question: str


# ==== Utility: embeddings + RAG placeholders (hardened) =====================

async def embed_text(text: str) -> List[float]:
    """
    Try to embed. If anything fails (no key, LiteLLM missing, provider error),
    return an empty list so caller can degrade gracefully.
    """
    if not (LITELLM_OK and GEMINI_API_KEY):
        return []
    try:
        resp = await aembedding(model=EMBED_MODEL, input=text)
        # liteLLM normalizes to 'data[0].embedding' style
        vec = resp["data"][0]["embedding"]
        return vec
    except Exception as e:
        log.warning("embed_text failed: %s", e)
        return []


async def find_relevant_sources(query_text: str, k: int = 2) -> List[Dict[str, Any]]:
    """
    MVP: no DB dependency. Try embedding to simulate RAG decision, but if
    anything fails just return an empty list.
    """
    _ = await embed_text(query_text)  # we ignore result in MVP fallback
    # In real impl: query pgvector with <=> ordering.
    # Here we always return empty to avoid crashing the flow.
    return []


def build_rag_prompt_with_history(answer_text: str,
                                  sources: List[Dict[str, Any]],
                                  role_profile: str,
                                  history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Compose a compact chat prompt for the model. Plain messages for LiteLLM.
    """
    system = (
        "Du är en strikt intervjuerare. Ge punktlistad feedback (3–6 bullets) på kandidatens svar, "
        "fokusera på STAR-metoden, kvantifiering, relevans mot rollen och tydliga förbättringar. "
        "Returnera bara saklig feedback utan överdrifter."
    )

    context = ""
    if sources:
        context = "Källor:\n" + "\n".join(f"- {s.get('title','(okänd)')}" for s in sources)

    messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
    if role_profile:
        messages.append({"role": "user", "content": f"Rollprofil: {role_profile}"})
    if context:
        messages.append({"role": "user", "content": context})

    # include short history (last 3 exchanges)
    for turn in history[-3:]:
        if "question" in turn:
            messages.append({"role": "user", "content": f"Fråga: {turn['question']}"})
        if "answer" in turn:
            messages.append({"role": "user", "content": f"Svar: {turn['answer']}"})

    messages.append({"role": "user", "content": f"Utvärdera detta svar och ge punktlista:\n{answer_text}"})
    return messages


def first_question_for(role_profile: str) -> str:
    return f"Välkommen. För rollen '{role_profile}', berätta om ett projekt du är stolt över."


def next_question_for(role_profile: str) -> str:
    return "Ge ett konkret exempel där ditt beslut påverkade resultatet och hur du verifierade effekten."


# ==== Endpoints ==============================================================

@app.get("/")
async def read_root():
    return {"message": "AI Interview Trainer API is running"}

@app.post("/session/start", response_model=StartSessionResponse)
async def start_session(req: StartSessionRequest):
    sid = uuid.uuid4()
    SESSIONS[str(sid)] = {
        "role_profile": req.role_profile,
        "history": []
    }
    return StartSessionResponse(session_id=sid, first_question=first_question_for(req.role_profile))

@app.post("/session/answer", response_model=AnswerResponse)
async def process_answer(req: AnswerRequest):
    sid = str(req.session_id)
    sess = SESSIONS.get(sid)
    if not sess:
        # create a minimal session so flow doesn't break
        SESSIONS[sid] = {"role_profile": "Unknown", "history": []}
        sess = SESSIONS[sid]

    role_profile: str = sess.get("role_profile", "Unknown")
    history: List[Dict[str, str]] = sess.get("history", [])

    # ---- RAG + LLM (hardened) ---------------------------------------------
    try:
        sources = await find_relevant_sources(req.answer_text, k=2)
    except Exception as e:
        log.warning("find_relevant_sources failed: %s", e)
        sources = []

    messages = build_rag_prompt_with_history(req.answer_text, sources, role_profile, history)

    ai_text = None
    if LITELLM_OK and GEMINI_API_KEY:
        try:
            resp = await acompletion(model=CHAT_MODEL, messages=messages)
            ai_text = resp.choices[0].message.content.strip()
        except Exception as e:
            log.warning("LLM completion failed: %s", e)

    # Fallback feedback text
    if not ai_text:
        ai_text = (
            "- Förtydliga din roll och dina konkreta handlingar.\n"
            "- Använd STAR (Situation–Task–Action–Result) för struktur.\n"
            "- Kvantifiera resultat (t.ex. +X%, −Y fel, Z användare).\n"
            "- Knyt svaret till krav för rollen och teknikstacken.\n"
            "- Nämn en lärdom och hur du tillämpade den."
        )

    # Update history
    history.append({"question": history[-1]["question"] if history else first_question_for(role_profile),
                    "answer": req.answer_text})
    sess["history"] = history  # write-back (explicit)

    # Build response
    feedback = Feedback(
        bullets=[b.strip("- ").strip() for b in ai_text.split("\n") if b.strip()],
        sources=[s.get("title", "") for s in (sources or [])]
    )
    return AnswerResponse(feedback=feedback, next_question=next_question_for(role_profile))