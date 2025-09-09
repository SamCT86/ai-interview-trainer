from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, UUID4
from typing import Dict, List, Optional
from uuid import uuid4, UUID
import os

# SQLAlchemy
from sqlalchemy.ext.asyncio import create_async_engine

# -----------------------------------------------------------------------------
# Force psycopg v3 driver (fix for Render deploy)
# -----------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql+psycopg2://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)

# Create async engine (will be used later for DB ops)
engine = create_async_engine(DATABASE_URL, future=True, pool_pre_ping=True)

# -----------------------------------------------------------------------------
# FastAPI app + CORS
# -----------------------------------------------------------------------------
app = FastAPI(title="AI Interview Trainer API", version="1.0.0")

FRONTEND_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class StartRequest(BaseModel):
    role_profile: str

class StartResponse(BaseModel):
    session_id: UUID4
    first_question: str

class AnswerRequest(BaseModel):
    session_id: UUID4
    answer_text: str

class Feedback(BaseModel):
    summary: str
    bullets: List[str] = []
    sources: List[str] = []

class AnswerResponse(BaseModel):
    next_question: Optional[str] = None
    feedback: Feedback

# -----------------------------------------------------------------------------
# Enkel “MVP-state” i minnet för unika frågor per session
# -----------------------------------------------------------------------------
QUESTION_BANK: Dict[str, List[str]] = {
    "Junior Developer": [
        "Välkommen. För rollen 'Junior Developer', berätta om ett projekt du är stolt över.",
        "Ge ett konkret exempel på mätbart resultat (R i STAR): vad blev effekten och hur verifierade du den?",
        "Beskriv en teknisk utmaning du stötte på i projektet och hur du löste den.",
        "Hur testade du din lösning (enheter, integration, prestanda)? Ge detaljer."
    ],
    "Project Manager": [
        "Välkommen. För rollen 'Project Manager', berätta om ett projekt du ledde och vad som gjorde det framgångsrikt.",
        "Hur hanterade du risker och intressenter? Ge ett konkret exempel på effekt.",
        "Berätta om ett svårt beslut du tog och hur du utvärderade utfallen."
    ],
}

SESSIONS: Dict[UUID, Dict] = {}  # {session_id: {"role": str, "index": int, "history": List[Dict]]}

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def get_first_question(role: str) -> str:
    questions = QUESTION_BANK.get(role) or QUESTION_BANK["Junior Developer"]
    return questions[0]

def get_next_question(role: str, idx: int) -> Optional[str]:
    questions = QUESTION_BANK.get(role) or QUESTION_BANK["Junior Developer"]
    nxt = idx + 1
    if nxt < len(questions):
        return questions[nxt]
    return None

def generate_feedback(role: str, question: str, answer: str) -> Feedback:
    bullets = []
    if "projekt" in question.lower():
        bullets.append("Förtydliga omfattning, din roll och mätbara resultat.")
        if "FastAPI" in answer or "API" in answer or "cach" in answer.lower():
            bullets.append("Bra att nämna teknik. Lägg till detaljer om valda lösningar och varför.")
    if "mätbart" in question.lower() or "resultat" in question.lower():
        bullets.append("Fortsätt kvantifiera förbättringar med tydliga siffror och hur du validerade dem.")
    if "utmaning" in question.lower():
        bullets.append("Beskriv problemet, alternativen du övervägde och varför din lösning valdes.")
    if "test" in question.lower():
        bullets.append("Nämn konkreta ramverk/verktyg (t.ex. pytest, locust, grafana) och vad de påvisade.")

    if not bullets:
        bullets.append("Svarade bra. Lägg gärna till konkreta exempel, siffror och ditt personliga bidrag.")

    return Feedback(
        summary="MVP-feedback – fortsätt ge konkreta data och tydliggör din personliga påverkan.",
        bullets=bullets,
        sources=[],
    )

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/")
def read_root():
    return {"message": "AI Interview Trainer API is running"}

@app.post("/session/start", response_model=StartResponse)
def session_start(req: StartRequest):
    role = (req.role_profile or "").strip() or "Junior Developer"
    session_id = uuid4()
    first_q = get_first_question(role)

    SESSIONS[session_id] = {
        "role": role,
        "index": 0,
        "history": []
    }
    return StartResponse(session_id=session_id, first_question=first_q)

@app.post("/session/answer", response_model=AnswerResponse)
def session_answer(req: AnswerRequest):
    sid = UUID(str(req.session_id))
    if sid not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    state = SESSIONS[sid]
    role = state["role"]
    idx = state["index"]
    last_question = QUESTION_BANK.get(role, QUESTION_BANK["Junior Developer"])[idx]

    state["history"].append({"q": last_question, "a": req.answer_text})
    fb = generate_feedback(role, last_question, req.answer_text)

    next_q = get_next_question(role, idx)
    if next_q is not None:
        state["index"] = idx + 1

    return AnswerResponse(next_question=next_q, feedback=fb)