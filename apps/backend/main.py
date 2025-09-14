# apps/backend/main.py
import os
import uuid
import json
import asyncio
from typing import List, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

from pydantic import BaseModel
from dotenv import load_dotenv

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql import text

from litellm import acompletion

# --- Konfiguration & Initiering ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_async_engine(DATABASE_URL)
app = FastAPI(title="AI Interview Trainer API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_origin_regex=r"https://.*\.vercel\.app",
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

# --- Prompt-konstruktion ---
def build_streaming_prompt(user_answer: str, role_profile: str, history: List[Dict]) -> List[Dict]:
    history_context = "\n".join(
        [f"Q: {h.get('q_text', '')}\nA: {h.get('a_text', '')}" for h in history]
    )
    system_prompt = f"""
Du är en senior rekryterande chef för rollen '{role_profile}'. Svara ALLTID på svenska.
För varje svar ska du:
1) Först ge 1–2 nya, icke-repetitiva bulletpoints med feedback på KANDIDATENS SENASTE svar.
2) På en ny rad skriv exakt token: |||
3) På en ny rad skriv ett JSON-objekt med heltalsbetyg 0–100 för "content", "structure", "communication".
4) På en ny rad skriv exakt token: |||
5) På en ny rad, ställ en ny, relevant, öppen följdfråga. Om intervjun är slut (efter 4–5 vändor), skriv 'INTERVIEW_COMPLETE'.

SAMTALSHISTORIK:
{history_context}
    """.strip()
    user_prompt = f"KANDIDATENS SENASTE SVAR:\n'{user_answer}'"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

# --- API Endpoints ---
@app.get("/", tags=["Health Check"])
def read_root():
    return {"message": "AI Interview Trainer API is running"}

@app.post("/session/start", response_model=StartSessionResponse, tags=["Interview"])
async def start_interview_session(request: StartSessionRequest):
    session_id = uuid.uuid4()
    first_question = (
        f"Välkommen. För rollen som {request.role_profile}, kan du berätta om ett specifikt "
        f"projekt eller en prestation som du är särskilt stolt över?"
    )
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO sessions (id, role_profile) VALUES (:id, :role_profile)"),
            {"id": session_id, "role_profile": request.role_profile},
        )
        await connection.execute(
            text("INSERT INTO turns (id, session_id, q_text) VALUES (:id, :session_id, :q_text)"),
            {"id": uuid.uuid4(), "session_id": session_id, "q_text": first_question},
        )
    return StartSessionResponse(session_id=session_id, first_question=first_question)

@app.post("/session/answer", tags=["Interview"])
async def process_answer_streaming(request: AnswerRequest):
    async def stream_generator():
        try:
            # 1) Hämta historik och roll
            async with engine.begin() as connection:
                session_result = await connection.execute(
                    text("SELECT role_profile FROM sessions WHERE id = :session_id"),
                    {"session_id": request.session_id},
                )
                session_row = session_result.fetchone()
                if not session_row:
                    raise HTTPException(status_code=404, detail="Session not found")
                role_profile = session_row[0]

                history_result = await connection.execute(
                    text(
                        "SELECT q_text, a_text FROM turns "
                        "WHERE session_id = :session_id ORDER BY created_at ASC"
                    ),
                    {"session_id": request.session_id},
                )
                history = history_result.mappings().all()

                last_turn_id_result = await connection.execute(
                    text(
                        "SELECT id FROM turns WHERE session_id = :session_id "
                        "AND a_text IS NULL ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"session_id": request.session_id},
                )
                last_turn_id = last_turn_id_result.scalar_one_or_none()
                if not last_turn_id:
                    raise HTTPException(status_code=400, detail="No open question found.")

                await connection.execute(
                    text("UPDATE turns SET a_text = :a_text WHERE id = :id"),
                    {"a_text": request.answer_text, "id": last_turn_id},
                )

            # 2) LLM stream
            messages = build_streaming_prompt(request.answer_text, role_profile, history)
            response_stream = await acompletion(
                model="gemini/gemini-1.5-flash-latest",
                messages=messages,
                stream=True,
            )

            # 3) Strömma till klient
            full_response = ""
            async for chunk in response_stream:
                # Litellm-stream: försök läsa delta.content (fallback till content)
                content = None
                try:
                    content = chunk.choices[0].delta.content  # OpenAI-liknande
                except Exception:
                    try:
                        content = chunk.choices[0].message.content
                    except Exception:
                        content = None
                if content:
                    full_response += content
                    yield content

            # 4) Parsa och spara i DB
            parts = full_response.split("|||")
            if len(parts) >= 3:
                feedback_text = parts[0].strip()
                scores_json_text = parts[1].strip()
                next_question_text = parts[2].strip()

                try:
                    scores_data = json.loads(scores_json_text)
                except json.JSONDecodeError:
                    scores_data = {"content": 0, "structure": 0, "communication": 0}

                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "INSERT INTO scores (turn_id, content, structure, comms) "
                            "VALUES (:turn_id, :content, :structure, :comms)"
                        ),
                        {
                            "turn_id": last_turn_id,
                            "content": scores_data.get("content"),
                            "structure": scores_data.get("structure"),
                            "comms": scores_data.get("communication"),
                        },
                    )
                    if next_question_text != "INTERVIEW_COMPLETE":
                        await connection.execute(
                            text(
                                "INSERT INTO turns (id, session_id, q_text) "
                                "VALUES (:id, :session_id, :q_text)"
                            ),
                            {
                                "id": uuid.uuid4(),
                                "session_id": request.session_id,
                                "q_text": next_question_text,
                            },
                        )

        except Exception as e:
            yield f"STREAM_ERROR: {str(e)}"

    return StreamingResponse(stream_generator(), media_type="text/plain")
