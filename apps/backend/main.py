import os
import uuid
import json
from typing import List, Optional, Dict

from fastapi import FastAPI, HTTPException, Response
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
app = FastAPI(title="AI Interview Trainer API", version="1.1.1")

# --- CORS (tillåter localhost + vercel.app) ---
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # MVP-läge – öppet
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Preflight fallback (fixar 405 på OPTIONS) ---
@app.options("/{path:path}")
def preflight_ok(path: str):
    return Response(status_code=204)

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

# --- Schema bootstrap ---
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
    history_context = "\n".join([f"Q: {h.get('q_text','')}\nA: {h.get('a_text','')}" for h in history])
    system_prompt = f"""
You are a world-class interview coach hiring for a '{role_profile}' position.
Analyze ONLY the candidate's latest answer in the history below.
Return STRICT JSON with:
- "feedback_bullets" (1-2 items),
- "scores" (content, structure, communication; 0-100 ints),
- "next_question" (string) OR null to end interview.
History:
{history_context}
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"CANDIDATE_LATEST_ANSWER:\n{user_answer}"},
    ]

# --- Endpoints ---
@app.get("/", tags=["Health"])
def health():
    return {"ok": True}

@app.post("/session/start", response_model=StartSessionResponse, tags=["Interview"])
async def start_session(req: StartSessionRequest):
    await ensure_schema()
    sid = uuid.uuid4()
    first_q = f"Välkommen! För rollen '{req.role_profile}', berätta om ett projekt du är stolt över och din påverkan."
    async with engine.begin() as conn:
        await conn.execute(text("INSERT INTO sessions (id, user_id, role_profile) VALUES (:i,:u,:r)"),
                           {"i": sid, "u": None, "r": req.role_profile})
        await conn.execute(text("INSERT INTO turns (id, session_id, q_text) VALUES (:i,:s,:q)"),
                           {"i": uuid.uuid4(), "s": sid, "q": first_q})
    return StartSessionResponse(session_id=sid, first_question=first_q)

@app.post("/session/answer", response_model=AnswerResponse, tags=["Interview"])
async def answer(req: AnswerRequest):
    await ensure_schema()
    try:
        async with engine.begin() as conn:
            r = await conn.execute(text("SELECT role_profile FROM sessions WHERE id=:s"), {"s": req.session_id})
            row = r.fetchone()
            if not row: raise HTTPException(status_code=404, detail="Session not found")
            role_profile = row[0]

            hist = (await conn.execute(
                text("SELECT q_text,a_text FROM turns WHERE session_id=:s ORDER BY created_at ASC"),
                {"s": req.session_id}
            )).mappings().all()

            last_id = (await conn.execute(
                text("SELECT id FROM turns WHERE session_id=:s ORDER BY created_at DESC LIMIT 1"),
                {"s": req.session_id}
            )).scalar_one_or_none()
            if last_id:
                await conn.execute(text("UPDATE turns SET a_text=:a WHERE id=:i"),
                                   {"a": req.answer_text, "i": last_id})

        msgs = build_full_prompt(req.answer_text, role_profile, hist)
        resp = await acompletion(model="gemini/gemini-1.5-flash-latest",
                                 messages=msgs,
                                 response_format={"type": "json_object"})
        try:
            content = resp.choices[0].message.content
        except Exception:
            content = getattr(resp, "content", None) or "{}"
        try:
            data = json.loads(content)
        except Exception:
            data = {"feedback_bullets":["Utveckla med konkreta data."],
                    "scores":{"content":60,"structure":60,"communication":60},
                    "next_question": None}

        scores = data.get("scores", {"content":60,"structure":60,"communication":60})
        bullets = data.get("feedback_bullets", ["Bra början."])
        next_q = data.get("next_question", None)

        async with engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO scores (turn_id, content, structure, comms) VALUES (:t,:c,:s,:m) "
                     "ON CONFLICT (turn_id) DO NOTHING"),
                {"t": last_id, "c": int(scores.get("content",60)),
                 "s": int(scores.get("structure",60)), "m": int(scores.get("communication",60))}
            )
            if next_q:
                await conn.execute(text("INSERT INTO turns (id, session_id, q_text) VALUES (:i,:s,:q)"),
                                   {"i": uuid.uuid4(), "s": req.session_id, "q": next_q})

        return AnswerResponse(feedback=Feedback(bullets=bullets,
                                               scores=Scores(content=int(scores.get("content",60)),
                                                             structure=int(scores.get("structure",60)),
                                                             communication=int(scores.get("communication",60)))),
                              next_question=next_q)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {e}")

@app.get("/session/{session_id}/report", response_model=FinalReportResponse, tags=["Reporting"])
async def report(session_id: uuid.UUID):
    await ensure_schema()
    async with engine.connect() as conn:
        r = await conn.execute(text("SELECT role_profile FROM sessions WHERE id=:s"), {"s": session_id})
        row = r.fetchone()
        if not row: raise HTTPException(status_code=404, detail="Session not found")
        role_profile = row[0]

        rows = (await conn.execute(text("""
            SELECT s.content, s.structure, s.comms
            FROM scores s JOIN turns t ON s.turn_id=t.id
            WHERE t.session_id=:s AND t.a_text IS NOT NULL
        """), {"s": session_id})).fetchall()
        if not rows: raise HTTPException(status_code=404, detail="No scores for this session")

        n = len(rows)
        avg_c = sum(x[0] for x in rows)/n
        avg_s = sum(x[1] for x in rows)/n
        avg_m = sum(x[2] for x in rows)/n
        overall = (avg_c+avg_s+avg_m)/3

    strongest = max([("Content",avg_c),("Structure",avg_s),("Communication",avg_m)], key=lambda t:t[1])[0]
    weakest  = min([("Content",avg_c),("Structure",avg_s),("Communication",avg_m)], key=lambda t:t[1])[0]
    summary = (f"Slutrapport för rollen '{role_profile}'. Totalt snitt: {overall:.1f}/100. "
               f"Starkast: {strongest}. Utvecklingsområde: {weakest}.")

    return FinalReportResponse(
        session_id=session_id,
        role_profile=role_profile,
        metrics=ReportMetrics(
            avg_content=round(avg_c,1),
            avg_structure=round(avg_s,1),
            avg_communication=round(avg_m,1),
            overall_avg=round(overall,1),
        ),
        final_summary=summary,
    )
