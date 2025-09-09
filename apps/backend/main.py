import os
import uuid
import json
from typing import List, Optional, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql import text

from litellm import acompletion

# --- Config ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)

app = FastAPI(title="AI Interview Trainer API", version="1.1.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://*.vercel.app",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Models ---
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
    next_question: Optional[str]  # None vid sista frågan

# Report models
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

# --- Schema bootstrap (skapar scores om den saknas) ---
async def ensure_schema():
    create_scores_sql = """
    CREATE TABLE IF NOT EXISTS scores (
        turn_id uuid PRIMARY KEY,
        content integer NOT NULL,
        structure integer NOT NULL,
        comms integer NOT NULL,
        created_at timestamp with time zone DEFAULT now()
    );
    """
    async with engine.begin() as conn:
        await conn.execute(text(create_scores_sql))

# --- Prompt helper ---
def build_full_prompt(user_answer: str, role_profile: str, history: List[Dict]) -> List[Dict]:
    history_context = "\n".join(
        [f"Q: {h.get('q_text','')}\nA: {h.get('a_text','')}" for h in history]
    )
    system_prompt = f"""
You are a world-class interview coach hiring for a '{role_profile}' position.
Analyze ONLY the candidate's latest answer in context of the history below.
Return a STRICT JSON object with keys:
- "feedback_bullets": list of 1-2 concise improvement points (no repeats across turns)
- "scores": integers 0-100 for "content", "structure", "communication"
- "next_question": a new relevant open-ended follow-up question OR null if interview is finished

Conversation history (oldest->newest):
{history_context}
"""
    user_prompt = f"CANDIDATE_LATEST_ANSWER:\n{user_answer}"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

# --- Endpoints ---
@app.get("/", tags=["Health"])
def health():
    return {"message": "AI Interview Trainer API is running"}

@app.post("/session/start", response_model=StartSessionResponse, tags=["Interview"])
async def start_interview_session(request: StartSessionRequest):
    await ensure_schema()
    session_id = uuid.uuid4()
    first_question = (
        f"Välkommen! För rollen '{request.role_profile}', berätta om ett projekt du är stolt över "
        f"och vad just DU bidrog med (mål, teknik, resultat)."
    )
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO sessions (id, user_id, role_profile) VALUES (:id, :user_id, :role_profile)"),
            {"id": session_id, "user_id": None, "role_profile": request.role_profile},
        )
        await conn.execute(
            text("INSERT INTO turns (id, session_id, q_text) VALUES (:id, :session_id, :q_text)"),
            {"id": uuid.uuid4(), "session_id": session_id, "q_text": first_question},
        )
    return StartSessionResponse(session_id=session_id, first_question=first_question)

@app.post("/session/answer", response_model=AnswerResponse, tags=["Interview"])
async def process_answer(request: AnswerRequest):
    await ensure_schema()
    try:
        # Fetch session + history
        async with engine.begin() as conn:
            sess = await conn.execute(
                text("SELECT role_profile FROM sessions WHERE id = :sid"),
                {"sid": request.session_id},
            )
            row = sess.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Session not found")
            role_profile = row[0]

            history_res = await conn.execute(
                text("SELECT q_text, a_text FROM turns WHERE session_id = :sid ORDER BY created_at ASC"),
                {"sid": request.session_id},
            )
            history = history_res.mappings().all()

            # set latest answer on last turn
            last_id = (
                await conn.execute(
                    text("SELECT id FROM turns WHERE session_id = :sid ORDER BY created_at DESC LIMIT 1"),
                    {"sid": request.session_id},
                )
            ).scalar_one_or_none()
            if last_id:
                await conn.execute(
                    text("UPDATE turns SET a_text = :a WHERE id = :id"),
                    {"a": request.answer_text, "id": last_id},
                )

        # LLM call
        msgs = build_full_prompt(request.answer_text, role_profile, history)
        resp = await acompletion(
            model="gemini/gemini-1.5-flash-latest",
            messages=msgs,
            response_format={"type": "json_object"},
        )

        # Parse robustly
        try:
            content = resp.choices[0].message.content
        except Exception:
            content = getattr(resp, "content", None) or json.dumps(resp)

        try:
            data = json.loads(content)
        except Exception:
            data = {
                "feedback_bullets": ["Kunde inte tolka svar."],
                "scores": {"content": 60, "structure": 60, "communication": 60},
                "next_question": None,
            }

        scores_data = data.get("scores", {"content": 60, "structure": 60, "communication": 60})
        feedback_bullets = data.get("feedback_bullets", ["Bra början. Utveckla med konkreta data."])
        next_question = data.get("next_question", None)

        # Save scores + maybe next question
        async with engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO scores (turn_id, content, structure, comms) VALUES (:tid, :c, :s, :m) "
                     "ON CONFLICT (turn_id) DO NOTHING"),
                {
                    "tid": last_id,
                    "c": int(scores_data.get("content", 60)),
                    "s": int(scores_data.get("structure", 60)),
                    "m": int(scores_data.get("communication", 60)),
                },
            )
            if next_question:
                await conn.execute(
                    text("INSERT INTO turns (id, session_id, q_text) VALUES (:id, :sid, :q)"),
                    {"id": uuid.uuid4(), "sid": request.session_id, "q": next_question},
                )

        fb = Feedback(bullets=feedback_bullets, scores=Scores(**{
            "content": int(scores_data.get("content", 60)),
            "structure": int(scores_data.get("structure", 60)),
            "communication": int(scores_data.get("communication", 60)),
        }))
        return AnswerResponse(feedback=fb, next_question=next_question)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing answer: {str(e)}")

@app.get("/session/{session_id}/report", response_model=FinalReportResponse, tags=["Reporting"])
async def get_final_report(session_id: uuid.UUID):
    await ensure_schema()
    try:
        async with engine.connect() as conn:
            sess = await conn.execute(
                text("SELECT role_profile FROM sessions WHERE id = :sid"),
                {"sid": session_id},
            )
            row = sess.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Session not found")
            role_profile = row[0]

            res = await conn.execute(
                text("""
                    SELECT s.content, s.structure, s.comms
                    FROM scores s
                    JOIN turns t ON s.turn_id = t.id
                    WHERE t.session_id = :sid AND t.a_text IS NOT NULL
                """),
                {"sid": session_id},
            )
            rows = res.fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail="No scores for this session")

            n = len(rows)
            avg_c = sum(r[0] for r in rows) / n
            avg_s = sum(r[1] for r in rows) / n
            avg_m = sum(r[2] for r in rows) / n
            overall = (avg_c + avg_s + avg_m) / 3

        strongest = max([("Content", avg_c), ("Structure", avg_s), ("Communication", avg_m)], key=lambda x: x[1])[0]
        weakest  = min([("Content", avg_c), ("Structure", avg_s), ("Communication", avg_m)], key=lambda x: x[1])[0]

        final_summary = (
            f"Slutrapport för rollen '{role_profile}'. Totalt snitt: {overall:.1f}/100. "
            f"Starkast: {strongest}. Utvecklingsområde: {weakest}."
        )

        return FinalReportResponse(
            session_id=session_id,
            role_profile=role_profile,
            metrics=ReportMetrics(
                avg_content=round(avg_c, 1),
                avg_structure=round(avg_s, 1),
                avg_communication=round(avg_m, 1),
                overall_avg=round(overall, 1),
            ),
            final_summary=final_summary,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")
