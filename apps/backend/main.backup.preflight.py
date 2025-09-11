import os
import uuid
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql import text
from typing import List, Optional, Dict

# --- Konfiguration & Initiering ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

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
class Scores(BaseModel):
    content: int
    structure: int
    communication: int
class Feedback(BaseModel):
    bullets: List[str]
    scores: Scores
class AnswerResponse(BaseModel):
    feedback: Feedback
    next_question: Optional[str] # Blir null vid sista frågan

# --- NYA Datamodeller för Rapport ---
class ReportMetrics(BaseModel):
    avg_content: float
    avg_structure: float
    avg_communication: float
    overall_avg: float

class FinalReportResponse(BaseModel):
    session_id: uuid.UUID
    role_profile: str
    metrics: ReportMetrics
    final_summary: str # En AI-genererad sammanfattning

# --- Prompt-konstruktion ---
def build_full_prompt(user_answer: str, role_profile: str, history: List[Dict]) -> List[Dict]:
    # ... (samma som tidigare)
    history_context = "\n".join([f"Q: {h.get('q_text', '')}\nA: {h.get('a_text', '')}" for h in history])
    system_prompt = f"""
    You are a world-class interview coach hiring for a '{role_profile}' position.
    Your task is to analyze the candidate's LATEST answer and respond with a single JSON object.
    Review the conversation history to avoid repeating feedback or questions.

    Your JSON response MUST contain three keys:
    1. "feedback_bullets": A list of 1-2 new, non-repetitive feedback strings.
    2. "scores": An object with integer scores from 0 to 100 for "content", "structure", and "communication".
    3. "next_question": A new, relevant, open-ended follow-up question. If this was the final question, return null.
    """
    user_prompt = f"CANDIDATE'S LATEST ANSWER:\n'{user_answer}'"
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

# --- API Endpoints ---
@app.get("/", tags=["Health Check"])
def read_root():
    return {"message": "AI Interview Trainer API is running"}

@app.post("/session/start", response_model=StartSessionResponse, tags=["Interview"])
async def start_interview_session(request: StartSessionRequest):
    # ... (samma som tidigare)
    session_id = uuid.uuid4()
    first_question = f"Välkommen. För rollen '{request.role_profile}', berätta om ett projekt du är stolt över."
    async with engine.begin() as connection:
        await connection.execute(text("INSERT INTO sessions (id, user_id, role_profile) VALUES (:id, :user_id, :role_profile)"), {"id": session_id, "user_id": None, "role_profile": request.role_profile})
        await connection.execute(text("INSERT INTO turns (id, session_id, q_text) VALUES (:id, :session_id, :q_text)"), {"id": uuid.uuid4(), "session_id": session_id, "q_text": first_question})
    return StartSessionResponse(session_id=session_id, first_question=first_question)

@app.post("/session/answer", response_model=AnswerResponse, tags=["Interview"])
async def process_answer(request: AnswerRequest):
    # ... (samma logik som i Steg 17, men notera att next_question kan bli null)
    turn_id = uuid.uuid4()
    try:
        async with engine.begin() as connection:
            session_result = await connection.execute(text("SELECT role_profile FROM sessions WHERE id = :session_id"), {"session_id": request.session_id})
            session = session_result.fetchone()
            if not session: raise HTTPException(status_code=404, detail="Session not found")
            role_profile = session[0]

            history_result = await connection.execute(text("SELECT q_text, a_text FROM turns WHERE session_id = :session_id ORDER BY created_at ASC"), {"session_id": request.session_id})
            history = history_result.mappings().all()

            last_turn_id_query = text("SELECT id FROM turns WHERE session_id = :session_id ORDER BY created_at DESC LIMIT 1")
            last_turn_id = (await connection.execute(last_turn_id_query, {"session_id": request.session_id})).scalar_one_or_none()

            if last_turn_id:
                update_turn_query = text("UPDATE turns SET a_text = :a_text WHERE id = :id")
                await connection.execute(update_turn_query, {"a_text": request.answer_text, "id": last_turn_id})

        messages = build_full_prompt(request.answer_text, role_profile, history)
        response = await acompletion(model="gemini/gemini-1.5-flash-latest", messages=messages, response_format={"type": "json_object"})

        ai_response_json = json.loads(response.choices[0].message.content)
        scores_data = ai_response_json.get("scores", {"content": 0, "structure": 0, "communication": 0})
        feedback_bullets = ai_response_json.get("feedback_bullets", ["No feedback provided."])
        next_question = ai_response_json.get("next_question") # Kan vara null

        async with engine.begin() as connection:
            insert_scores_query = text("INSERT INTO scores (turn_id, content, structure, comms) VALUES (:turn_id, :content, :structure, :comms)")
            await connection.execute(insert_scores_query, {"turn_id": last_turn_id, "content": scores_data.get("content"), "structure": scores_data.get("structure"), "comms": scores_data.get("communication")})

            if next_question:
                insert_question_query = text("INSERT INTO turns (id, session_id, q_text) VALUES (:id, :session_id, :q_text)")
                await connection.execute(insert_question_query, {"id": turn_id, "session_id": request.session_id, "q_text": next_question})

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing answer: {str(e)}")

    ai_feedback = Feedback(bullets=feedback_bullets, scores=Scores(**scores_data))
    return AnswerResponse(feedback=ai_feedback, next_question=next_question)

# --- NY Endpoint för Slutrapport ---
@app.get("/session/{session_id}/report", response_model=FinalReportResponse, tags=["Reporting"])
async def get_final_report(session_id: uuid.UUID):
    """
    Generates a final summary report for a completed interview session.
    """
    try:
        async with engine.connect() as connection:
            # Hämta sessionsdata och alla poäng
            session_query = text("SELECT role_profile FROM sessions WHERE id = :session_id")
            session_result = await connection.execute(session_query, {"session_id": session_id})
            session = session_result.fetchone()
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            role_profile = session[0]

            scores_query = text("""
                SELECT s.content, s.structure, s.comms
                FROM scores s
                JOIN turns t ON s.turn_id = t.id
                WHERE t.session_id = :session_id AND t.a_text IS NOT NULL
            """)
            scores_result = await connection.execute(scores_query, {"session_id": session_id})
            scores = scores_result.fetchall()

            if not scores:
                raise HTTPException(status_code=404, detail="No scores found for this session.")

            # Beräkna medelvärden
            avg_content = sum(s[0] for s in scores) / len(scores)
            avg_structure = sum(s[1] for s in scores) / len(scores)
            avg_communication = sum(s[2] for s in scores) / len(scores)
            overall_avg = (avg_content + avg_structure + avg_communication) / 3

            metrics = ReportMetrics(
                avg_content=round(avg_content, 1),
                avg_structure=round(avg_structure, 1),
                avg_communication=round(avg_communication, 1),
                overall_avg=round(overall_avg, 1)
            )

        # (Valfritt men rekommenderat) Anropa LLM för en text-sammanfattning
        # Detta kan läggas till senare för att hålla MVP enkel
        final_summary = f"Du genomförde en intervju för rollen {role_profile} med ett totalt medelresultat på {metrics.overall_avg:.1f}/100. Ditt starkaste område var {'Content' if avg_content > avg_structure else 'Structure'}, medan det finns utvecklingspotential inom {'Communication' if avg_communication < avg_structure else 'Structure'}."

        return FinalReportResponse(
            session_id=session_id,
            role_profile=role_profile,
            metrics=metrics,
            final_summary=final_summary
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")