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
# Tillåter vår frontend att anropa API:et
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://ai-interview-trainer-front-git-main-sarmads-projects-f3142150.vercel.app"],
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

# --- Prompt-konstruktion (Uppgraderad) ---
def build_smarter_prompt(user_answer: str, role_profile: str, history: List[Dict]) -> List[Dict]:
    history_context = "\n".join([f"Q: {h.get('q_text', '')}\nA: {h.get('a_text', '')}" for h in history])

    system_prompt = f"""
    You are a senior hiring manager conducting an interview for a '{role_profile}' position.
    Your task is to analyze the candidate's LATEST answer and respond with a single JSON object.
    Review the conversation history to avoid repeating questions or feedback.

    Your JSON response MUST contain three keys:
    1. "feedback_bullets": A list of 1-2 new, non-repetitive feedback strings.
    2. "scores": An object with integer scores from 0 to 100 for "content", "structure", and "communication".
    3. "next_question": A new, relevant, open-ended follow-up question. VARY YOUR QUESTION STYLE by choosing one of the following types based on the conversation so far:
       - BEHAVIORAL: Ask for a specific past experience (e.g., "Describe a time when...").
       - SITUATIONAL: Present a hypothetical scenario (e.g., "Imagine you discover a critical bug right before a release. What do you do?").
       - TECHNICAL_DEEP_DIVE: Ask for a detailed explanation of a technology mentioned by the candidate.
       - REFLECTIVE: Ask the candidate to reflect on a past experience (e.g., "What was your key takeaway from that project?").
       If the interview has had 4-5 turns, consider ending it by returning null for "next_question".

    CONVERSATION HISTORY:
    {history_context}
    """
    
    user_prompt = f"CANDIDATE'S LATEST ANSWER:\n'{user_answer}'"

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

# --- API Endpoints ---
@app.get("/", tags=["Health Check"])
def read_root():
    return {"message": "AI Interview Trainer API is running"}

@app.post("/session/start", response_model=StartSessionResponse, tags=["Interview"])
async def start_interview_session(request: StartSessionRequest):
    session_id = uuid.uuid4()
    # Förbättrad startfråga
    first_question = f"Tack för ditt intresse för rollen som {request.role_profile}. För att börja, kan du berätta om ett specifikt projekt eller en prestation som du är särskilt stolt över och som är relevant för denna roll?"
    
    async with engine.begin() as connection:
        await connection.execute(text("INSERT INTO sessions (id, user_id, role_profile) VALUES (:id, :user_id, :role_profile)"), {"id": session_id, "user_id": None, "role_profile": request.role_profile})
        await connection.execute(text("INSERT INTO turns (id, session_id, q_text) VALUES (:id, :session_id, :q_text)"), {"id": uuid.uuid4(), "session_id": session_id, "q_text": first_question})
        
    return StartSessionResponse(session_id=session_id, first_question=first_question)

@app.post("/session/answer", response_model=AnswerResponse, tags=["Interview"])
async def process_answer(request: AnswerRequest):
    try:
        async with engine.begin() as connection:
            # Hämta session info och historik
            session_result = await connection.execute(text("SELECT role_profile FROM sessions WHERE id = :session_id"), {"session_id": request.session_id})
            session = session_result.fetchone()
            if not session: raise HTTPException(status_code=404, detail="Session not found")
            role_profile = session[0]

            history_result = await connection.execute(text("SELECT q_text, a_text FROM turns WHERE session_id = :session_id ORDER BY created_at ASC"), {"session_id": request.session_id})
            history = history_result.mappings().all()
            
            # Hitta ID för den senaste frågan och uppdatera den med svaret
            last_turn_id_result = await connection.execute(text("SELECT id FROM turns WHERE session_id = :session_id AND a_text IS NULL ORDER BY created_at DESC LIMIT 1"), {"session_id": request.session_id})
            last_turn_id = last_turn_id_result.scalar_one_or_none()
            
            if last_turn_id:
                update_turn_query = text("UPDATE turns SET a_text = :a_text WHERE id = :id")
                await connection.execute(update_turn_query, {"a_text": request.answer_text, "id": last_turn_id})
            else:
                # Fallback om ingen obesvarad fråga hittas (bör inte hända i normalt flöde)
                raise HTTPException(status_code=400, detail="No open question found to answer.")

        # Bygg prompt och anropa LLM
        messages = build_smarter_prompt(request.answer_text, role_profile, history)
        
        response = await acompletion(
            model="gemini/gemini-1.5-flash-latest",
            messages=messages,
            response_format={"type": "json_object"}
        )
        
        ai_response_json = json.loads(response.choices[0].message.content)
        scores_data = ai_response_json.get("scores", {"content": 0, "structure": 0, "communication": 0})
        feedback_bullets = ai_response_json.get("feedback_bullets", ["No feedback provided."])
        next_question = ai_response_json.get("next_question")

        async with engine.begin() as connection:
            # Spara poängen för den turn vi just besvarade
            insert_scores_query = text("INSERT INTO scores (turn_id, content, structure, comms) VALUES (:turn_id, :content, :structure, :comms)")
            await connection.execute(insert_scores_query, {
                "turn_id": last_turn_id, 
                "content": scores_data.get("content"), 
                "structure": scores_data.get("structure"), 
                "comms": scores_data.get("communication")
            })

            # Om en ny fråga genererades, spara den
            if next_question:
                insert_question_query = text("INSERT INTO turns (id, session_id, q_text) VALUES (:id, :session_id, :q_text)")
                await connection.execute(insert_question_query, {"id": uuid.uuid4(), "session_id": request.session_id, "q_text": next_question})

    except Exception as e:
        # Fångar alla fel och returnerar ett användarvänligt meddelande
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

    ai_feedback = Feedback(bullets=feedback_bullets, scores=Scores(**scores_data))
    return AnswerResponse(feedback=ai_feedback, next_question=next_question)
