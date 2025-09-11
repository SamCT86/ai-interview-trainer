import os
import uuid
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql import text
from typing import List, Optional, Dict
from litellm import acompletion
from fastapi.middleware.cors import CORSMiddleware

# --- Konfiguration & Initiering ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in the .env file")

engine = create_async_engine(DATABASE_URL)
app = FastAPI(title="AI Interview Trainer API", version="1.0.0")

# --- CORS Middleware ---
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
class Scores(BaseModel):
    content: int
    structure: int
    communication: int
class Feedback(BaseModel):
    bullets: List[str]
    scores: Scores
class AnswerResponse(BaseModel):
    feedback: Feedback
    next_question: Optional[str]
class ReportMetrics(BaseModel):
    avg_content: float
    avg_structure: float
    avg_communication: float
    overall_avg: float
class FinalReportResponse(BaseModel):
    session_id: uuid.UUID
    role_profile: str
    metrics: ReportMetrics
    final_summary: str

# --- Prompt-konstruktion (med språkstyrning) ---
def build_smarter_prompt(user_answer: str, role_profile: str, history: List[Dict]) -> List[Dict]:
    history_context = "\n".join([f"Q: {h.get('q_text', '')}\nA: {h.get('a_text', '')}" for h in history])

    system_prompt = f"""
    You are a senior hiring manager for a '{role_profile}' position.
    Your task is to analyze the candidate's LATEST answer and respond with a single JSON object.
    You MUST always respond in Swedish.
    Review the conversation history to avoid repeating questions or feedback.

    Your JSON response MUST contain three keys:
    1. "feedback_bullets": A list of 1-2 new, non-repetitive feedback strings in Swedish.
    2. "scores": An object with integer scores from 0 to 100 for "content", "structure", and "communication".
    3. "next_question": A new, relevant, open-ended follow-up question in Swedish. If the interview has had 4-5 turns, return null.

    CONVERSATION HISTORY:
    {history_context}
    """
    user_prompt = f"CANDIDATE'S LATEST ANSWER:\n'{user_answer}'"
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

# --- API Endpoints ---
@app.get("/", tags=["Health Check"])
def read_root():
    return {"message": "AI Interview Trainer API is running"}

@app.post("/session/start", response_model=StartSessionResponse, tags=["Interview"])
async def start_interview_session(request: StartSessionRequest):
    session_id = uuid.uuid4()
    first_question = f"Välkommen. För rollen som {request.role_profile}, kan du berätta om ett specifikt projekt eller en prestation som du är särskilt stolt över?"
    async with engine.begin() as connection:
        await connection.execute(text("INSERT INTO sessions (id, role_profile) VALUES (:id, :role_profile)"), {"id": session_id, "role_profile": request.role_profile})
        await connection.execute(text("INSERT INTO turns (id, session_id, q_text) VALUES (:id, :session_id, :q_text)"), {"id": uuid.uuid4(), "session_id": session_id, "q_text": first_question})
    return StartSessionResponse(session_id=session_id, first_question=first_question)

@app.post("/session/answer", response_model=AnswerResponse, tags=["Interview"])
async def process_answer(request: AnswerRequest):
    try:
        async with engine.begin() as connection:
            session_result = await connection.execute(text("SELECT role_profile FROM sessions WHERE id = :session_id"), {"session_id": request.session_id})
            session = session_result.fetchone()
            if not session: raise HTTPException(status_code=404, detail="Session not found")
            role_profile = session[0]

            history_result = await connection.execute(text("SELECT q_text, a_text FROM turns WHERE session_id = :session_id ORDER BY created_at ASC"), {"session_id": request.session_id})
            history = history_result.mappings().all()

            last_turn_id_result = await connection.execute(text("SELECT id FROM turns WHERE session_id = :session_id AND a_text IS NULL ORDER BY created_at DESC LIMIT 1"), {"session_id": request.session_id})
            last_turn_id = last_turn_id_result.scalar_one_or_none()
            if not last_turn_id: raise HTTPException(status_code=400, detail="No open question found to answer.")

            await connection.execute(text("UPDATE turns SET a_text = :a_text WHERE id = :id"), {"a_text": request.answer_text, "id": last_turn_id})

        messages = build_smarter_prompt(request.answer_text, role_profile, history)
        response = await acompletion(model="gemini/gemini-1.5-flash-latest", messages=messages, response_format={"type": "json_object"})
        ai_response_json = json.loads(response.choices[0].message.content)

        scores_data = ai_response_json.get("scores", {"content": 0, "structure": 0, "communication": 0})
        feedback_bullets = ai_response_json.get("feedback_bullets", ["Kunde inte generera feedback."])
        next_question = ai_response_json.get("next_question")

        async with engine.begin() as connection:
            await connection.execute(text("INSERT INTO scores (turn_id, content, structure, comms) VALUES (:turn_id, :content, :structure, :comms)"), {"turn_id": last_turn_id, "content": scores_data.get("content"), "structure": scores_data.get("structure"), "comms": scores_data.get("communication")})
            if next_question:
                await connection.execute(text("INSERT INTO turns (id, session_id, q_text) VALUES (:id, :session_id, :q_text)"), {"id": uuid.uuid4(), "session_id": request.session_id, "q_text": next_question})

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

    return AnswerResponse(feedback=Feedback(bullets=feedback_bullets, scores=Scores(**scores_data)), next_question=next_question)

@app.get("/session/{session_id}/report", response_model=FinalReportResponse, tags=["Reporting"])
async def get_final_report(session_id: uuid.UUID):
    try:
        async with engine.connect() as connection:
            session_result = await connection.execute(text("SELECT role_profile FROM sessions WHERE id = :session_id"), {"session_id": session_id})
            session = session_result.fetchone()
            if not session: raise HTTPException(status_code=404, detail="Session not found")
            role_profile = session[0]

            # Robustare query som bara hämtar scores från besvarade turns
            scores_query = text("""
                SELECT s.content, s.structure, s.comms
                FROM scores s
                JOIN turns t ON s.turn_id = t.id
                WHERE t.session_id = :session_id AND t.a_text IS NOT NULL
            """)
            scores_result = await connection.execute(scores_query, {"session_id": session_id})
            scores = scores_result.fetchall()
            if not scores: raise HTTPException(status_code=404, detail="No scores found for this session.")

            avg_content = sum(s[0] for s in scores) / len(scores)
            avg_structure = sum(s[1] for s in scores) / len(scores)
            avg_communication = sum(s[2] for s in scores) / len(scores)
            overall_avg = (avg_content + avg_structure + avg_communication) / 3

            metrics = ReportMetrics(avg_content=round(avg_content, 1), avg_structure=round(avg_structure, 1), avg_communication=round(avg_communication, 1), overall_avg=round(overall_avg, 1))

            final_summary = f"Slutrapport för din intervju som {role_profile}. Totalt medelresultat: {metrics.overall_avg:.1f}/100. Ditt starkaste område var {'Innehåll' if avg_content >= max(avg_structure, avg_communication) else 'Struktur' if avg_structure >= avg_communication else 'Kommunikation'}, med potential för utveckling inom {'Kommunikation' if avg_communication <= min(avg_content, avg_structure) else 'Struktur' if avg_structure <= avg_content else 'Innehåll'}."

        return FinalReportResponse(session_id=session_id, role_profile=role_profile, metrics=metrics, final_summary=final_summary)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")