import os
import uuid
from typing import List, Optional

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql import text
from litellm import acompletion, aembedding

# --- Konfiguration & init ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in the .env file")

engine = create_async_engine(DATABASE_URL)
app = FastAPI(title="AI Interview Trainer API", version="1.2.0")  # Steg 12

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Datamodeller ---
class StartSessionRequest(BaseModel):
    role_profile: str

class StartSessionResponse(BaseModel):
    session_id: uuid.UUID
    first_question: str

class AnswerRequest(BaseModel):
    session_id: uuid.UUID
    answer_text: str

class Feedback(BaseModel):
    bullets: List[str]
    citations: List[dict]  # källhänvisningar

class AnswerResponse(BaseModel):
    feedback: Feedback
    next_question: Optional[str] = None

# --- Hjälpare: hämta role_profile för en session ---
async def get_role_profile(session_id: uuid.UUID) -> str:
    q = text("SELECT role_profile FROM sessions WHERE id = :sid")
    async with engine.connect() as conn:
        row = (await conn.execute(q, {"sid": session_id})).first()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Session not found or role_profile missing")
    return row[0]

# --- RAG: hitta relevanta källor (pgvector; använd cast till vector) ---
async def find_relevant_sources(query_text: str, k: int = 2) -> List[dict]:
    emb = await aembedding(
        model="gemini/text-embedding-004",
        input=[query_text],
        api_key=GEMINI_API_KEY,
    )
    query_embedding = emb.data[0].embedding  # List[float]

    # OBS: byt 'embedding' till 'embedding_vector' om din kolumn heter så
    search_query = text("""
        SELECT title, chunk_text, url
        FROM sources
        ORDER BY embedding <=> (:query_embedding)::vector
        LIMIT :k
    """)

    async with engine.connect() as conn:
        result = await conn.execute(search_query, {"query_embedding": query_embedding, "k": k})
        rows = result.mappings().all()
    return [dict(r) for r in rows]

# --- Prompt-konstruktion (roll-medveten) ---
def build_rag_prompt(role_profile: str, user_answer: str, sources: List[dict]) -> List[dict]:
    source_context = "\n\n---\n\n".join(
        [f"[{i+1}] {s.get('title') or '(untitled)'}\n{s.get('chunk_text','')}" for i, s in enumerate(sources)]
    )

    system_prompt = f"""
Du är en senior intervjucoach som coachar en kandidat för rollen: {role_profile}.
Ge 2–4 korta, konkreta bullets. Basera feedback STRIKT på källorna nedan.
Fokusera på STAR (Situation, Task, Action, Result), kvantifiering och personligt ansvar.
KÄLLOR:
{source_context if source_context else '(inga källor)'}
""".strip()

    user_prompt = f"KANDIDATSVAR:\n{user_answer}"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

def craft_next_question(role_profile: str) -> str:
    rp = role_profile.lower()
    if "backend" in rp:
        return "Beskriv ett prestandaproblem du löste end-to-end i backend och hur du mätte förbättringen."
    if "frontend" in rp:
        return "Hur säkerställde du prestanda och tillgänglighet (a11y) i ett komplext UI? Ge mätetal."
    if "project manager" in rp or "pm" in rp:
        return "Hur prioriterade du scope under press och vilka risker mitigera du? Ge konkreta KPI:er."
    if "data" in rp:
        return "Ge ett exempel där du valde modell/arkitektur för data/ML och hur du validerade resultat."
    return "Ge ett konkret exempel där ditt beslut påverkade resultatet och hur du verifierade effekten."

# --- API ---
@app.get("/", tags=["Health"])
def root():
    return {"message": "AI Interview Trainer API is running (Step 12)"}

@app.post("/session/start", response_model=StartSessionResponse, tags=["Interview"])
async def start_session(request: StartSessionRequest):
    session_id = uuid.uuid4()
    insert_query = text(
        "INSERT INTO sessions (id, user_id, role_profile) VALUES (:id, :user_id, :role_profile)"
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(insert_query, {"id": session_id, "user_id": None, "role_profile": request.role_profile})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create session in database: {str(e)}")

    first_question = f"Välkommen. För rollen '{request.role_profile}', berätta om ett projekt du är stolt över."
    return StartSessionResponse(session_id=session_id, first_question=first_question)

@app.post("/session/answer", response_model=AnswerResponse, tags=["Interview"])
async def process_answer(request: AnswerRequest):
    # 0) Läs rollprofilen för den här sessionen
    role_profile = await get_role_profile(request.session_id)

    # 1) Spara kandidatens svar som en turn
    turn_id = uuid.uuid4()
    insert_turn = text("INSERT INTO turns (id, session_id, a_text) VALUES (:id, :sid, :a)")
    try:
        async with engine.begin() as conn:
            await conn.execute(insert_turn, {"id": turn_id, "sid": request.session_id, "a": request.answer_text})
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Session not found or failed to save turn: {str(e)}")

    # 2) RAG: hämta källor och bygg roll-medveten prompt
    try:
        relevant_sources = await find_relevant_sources(request.answer_text, k=2)
        messages = build_rag_prompt(role_profile, request.answer_text, relevant_sources)

        # 3) LLM-svar (Gemini 1.5 Flash via LiteLLM)
        resp = await acompletion(
            model="gemini/gemini-1.5-flash-latest",
            messages=messages,
            api_key=GEMINI_API_KEY,
        )
        ai_text = resp.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in RAG or LLM processing: {str(e)}")

    # 4) Parsning till bullets (robust)
    lines = [ln.strip() for ln in ai_text.split("\n") if ln.strip()]
    bullets: List[str] = []
    for ln in lines:
        if ln.startswith("- "):
            bullets.append(ln[2:].strip())
    if not bullets:
        bullets = [b.strip() for b in ai_text.split("- ") if b.strip()]
    if not bullets:
        bullets = [ai_text.strip()]
    bullets = bullets[:4]

    # 5) Skräddarsydd nästa fråga efter roll
    next_q = craft_next_question(role_profile)

    feedback = Feedback(
        bullets=bullets,
        citations=[{"title": s.get("title"), "url": s.get("url")} for s in relevant_sources],
    )
    return AnswerResponse(feedback=feedback, next_question=next_q)