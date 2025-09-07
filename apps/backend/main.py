import os
import uuid
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql import text
from litellm import acompletion, aembedding

# --- Konfiguration & init ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # tas från din .env

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in the .env file")

engine = create_async_engine(DATABASE_URL)
app = FastAPI(title="AI Interview Trainer API", version="1.0.0")

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

# --- RAG: hitta relevanta källor (pgvector <=> cosine) ---
async def find_relevant_sources(query_text: str, k: int = 2) -> List[dict]:
    # Async embeddings via Gemini (LitellM) – nyckel från .env
    emb = await aembedding(
        model="gemini/text-embedding-004",
        input=[query_text],
        api_key=GEMINI_API_KEY,
    )
    query_embedding = emb.data[0].embedding  # List[float]

    # OBS: byt 'embedding' till 'embedding_vector' om din kolumn heter så.

    search_query = text("""
    SELECT title, chunk_text
    FROM sources
    ORDER BY embedding <=> (:query_embedding)::vector
    LIMIT :k
""")


    async with engine.connect() as connection:
        result = await connection.execute(
            search_query,
            {"query_embedding": query_embedding, "k": k}
        )
        sources = result.mappings().all()  # List[RowMapping]
    return [dict(r) for r in sources]

# --- Prompt-konstruktion ---
def build_rag_prompt(user_answer: str, sources: List[dict]) -> List[dict]:
    source_context = "\n\n---\n\n".join(
        [f"Source: {s.get('title','(untitled)')}\nContent: {s.get('chunk_text','')}" for s in sources]
    )

    system_prompt = f"""
You are a world-class interview coach. Your task is to provide feedback on a candidate's answer.
Base your feedback STRICTLY on the provided sources below.
Provide 1–2 concise bullet points of feedback that help the candidate align with the principles in the sources.

SOURCES:
{source_context}
""".strip()

    user_prompt = f"CANDIDATE'S ANSWER:\n'{user_answer}'"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

# --- API ---
@app.get("/", tags=["Health"])
def root():
    return {"message": "AI Interview Trainer API is running"}

@app.post("/session/start", response_model=StartSessionResponse, tags=["Interview"])
async def start_session(request: StartSessionRequest):
    session_id = uuid.uuid4()
    insert_query = text(
        "INSERT INTO sessions (id, user_id, role_profile) VALUES (:id, :user_id, :role_profile)"
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(
                insert_query,
                {"id": session_id, "user_id": None, "role_profile": request.role_profile},
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create session in database: {str(e)}")

    first_question = f"Välkommen. Berätta om ett projekt du är stolt över inom området '{request.role_profile}'."
    return StartSessionResponse(session_id=session_id, first_question=first_question)

@app.post("/session/answer", response_model=AnswerResponse, tags=["Interview"])
async def process_answer(request: AnswerRequest):
    # 1) Spara användarens svar
    turn_id = uuid.uuid4()
    insert_query = text("INSERT INTO turns (id, session_id, a_text) VALUES (:id, :session_id, :a_text)")
    try:
        async with engine.begin() as connection:
            await connection.execute(
                insert_query,
                {"id": turn_id, "session_id": request.session_id, "a_text": request.answer_text},
            )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Session not found or failed to save turn: {str(e)}")

    # 2) RAG: hämta källor + bygg prompt
    try:
        relevant_sources = await find_relevant_sources(request.answer_text, k=2)
        messages = build_rag_prompt(request.answer_text, relevant_sources)

        # 3) LLM-svar (Gemini 1.5 Flash via LitellM)
        response = await acompletion(
            model="gemini/gemini-1.5-flash-latest",
            messages=messages,
            api_key=GEMINI_API_KEY,
        )
        ai_feedback_text = response.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in RAG or LLM processing: {str(e)}")

    # 4) Paketera svaret (försiktig parsning av bullets)
    # Modellen brukar svara i punktlista ("- "). Splitta försiktigt:
    raw_lines = [ln.strip() for ln in ai_feedback_text.split("\n") if ln.strip()]
    bullets = []
    for ln in raw_lines:
        if ln.startswith("- "):
            bullets.append(ln[2:].strip())
    if not bullets:
        # fallback: dela på "- " i hela texten
        bullets = [b.strip() for b in ai_feedback_text.split("- ") if b.strip()]
    if not bullets:
        bullets = [ai_feedback_text.strip()]

    feedback = Feedback(
        bullets=bullets[:4],
        citations=[{"title": s.get("title"), "url": s.get("url")} for s in relevant_sources],
    )
    next_q = "Tack. Baserat på din erfarenhet, hur skulle du hantera en situation med en kollega som inte levererar?"

    return AnswerResponse(feedback=feedback, next_question=next_q)