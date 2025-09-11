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
    from starlette.responses import StreamingResponse
    import asyncio

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
        history_context = "\n".join([f"Q: {h.get('q_text', '')}\nA: {h.get('a_text', '')}" for h in history])
        system_prompt = f"""
        You are a senior hiring manager for a '{role_profile}' position. You MUST always respond in Swedish.
        First, provide 1-2 new, non-repetitive feedback bullet points on the candidate's LATEST answer.
        Then, on a new line, write the token '|||'.
        Then, on a new line, provide integer scores from 0 to 100 for "content", "structure", and "communication" in a JSON object.
        Then, on a new line, write the token '|||'.
        Finally, on a new line, ask a new, relevant, open-ended follow-up question. If the interview is over (4-5 turns), write 'INTERVIEW_COMPLETE'.

        CONVERSATION HISTORY:
        {history_context}
        """
        user_prompt = f"CANDIDATE'S LATEST ANSWER:\n'{user_answer}'"
        return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

    # --- API Endpoints ---
    @app.get("/", tags=["Health Check"])
    def read_root(): return {"message": "AI Interview Trainer API is running"}

    @app.post("/session/start", response_model=StartSessionResponse, tags=["Interview"])
    async def start_interview_session(request: StartSessionRequest):
        session_id = uuid.uuid4()
        first_question = f"Välkommen. För rollen som {request.role_profile}, kan du berätta om ett specifikt projekt eller en prestation som du är särskilt stolt över?"
        async with engine.begin() as connection:
            await connection.execute(text("INSERT INTO sessions (id, role_profile) VALUES (:id, :role_profile)"), {"id": session_id, "role_profile": request.role_profile})
            await connection.execute(text("INSERT INTO turns (id, session_id, q_text) VALUES (:id, :session_id, :q_text)"), {"id": uuid.uuid4(), "session_id": session_id, "q_text": first_question})
        return StartSessionResponse(session_id=session_id, first_question=first_question)

    @app.post("/session/answer", tags=["Interview"])
    async def process_answer_streaming(request: AnswerRequest):
        async def stream_generator():
            try:
                # Steg 1: Hämta historik och roll (som tidigare)
                async with engine.begin() as connection:
                    session_result = await connection.execute(text("SELECT role_profile FROM sessions WHERE id = :session_id"), {"session_id": request.session_id})
                    session = session_result.fetchone()
                    if not session: raise HTTPException(status_code=404, detail="Session not found")
                    role_profile = session[0]

                    history_result = await connection.execute(text("SELECT q_text, a_text FROM turns WHERE session_id = :session_id ORDER BY created_at ASC"), {"session_id": request.session_id})
                    history = history_result.mappings().all()

                    last_turn_id_result = await connection.execute(text("SELECT id FROM turns WHERE session_id = :session_id AND a_text IS NULL ORDER BY created_at DESC LIMIT 1"), {"session_id": request.session_id})
                    last_turn_id = last_turn_id_result.scalar_one_or_none()
                    if not last_turn_id: raise HTTPException(status_code=400, detail="No open question found.")
                    
                    await connection.execute(text("UPDATE turns SET a_text = :a_text WHERE id = :id"), {"a_text": request.answer_text, "id": last_turn_id})

                # Steg 2: Anropa LLM med stream=True
                messages = build_streaming_prompt(request.answer_text, role_profile, history)
                response_stream = await acompletion(model="gemini/gemini-1.5-flash-latest", messages=messages, stream=True)

                # Steg 3: Strömma svaret till klienten
                full_response = ""
                async for chunk in response_stream:
                    content = chunk.choices[0].delta.content
                    if content:
                        full_response += content
                        yield content
                
                # Steg 4: Parsa den fullständiga responsen och spara i DB
                parts = full_response.split('|||')
                if len(parts) >= 3:
                    feedback_text = parts[0].strip()
                    scores_json_text = parts[1].strip()
                    next_question_text = parts[2].strip()
                    
                    try:
                        scores_data = json.loads(scores_json_text)
                    except json.JSONDecodeError:
                        scores_data = {"content": 0, "structure": 0, "communication": 0}

                    async with engine.begin() as connection:
                        await connection.execute(text("INSERT INTO scores (turn_id, content, structure, comms) VALUES (:turn_id, :content, :structure, :comms)"), {"turn_id": last_turn_id, "content": scores_data.get("content"), "structure": scores_data.get("structure"), "comms": scores_data.get("communication")})
                        if next_question_text != 'INTERVIEW_COMPLETE':
                            await connection.execute(text("INSERT INTO turns (id, session_id, q_text) VALUES (:id, :session_id, :q_text)"), {"id": uuid.uuid4(), "session_id": request.session_id, "q_text": next_question_text})
            
            except Exception as e:
                error_message = f"STREAM_ERROR: {str(e)}"
                yield error_message

        return StreamingResponse(stream_generator(), media_type="text/plain")
    
    # ... (Din /report endpoint är oförändrad) ...
    ```

**Del B: Uppgradera Frontend (`page.js`) för Streaming**
1.  **Öppna `page.js`:** I din kod-editor, öppna filen `apps/frontend/app/page.js`.
2.  **Ersätt Allt:** Radera **all** befintlig kod och ersätt den med denna nya version som kan hantera en dataström.

    ```javascript
    'use client';
    import { useState, useRef, useEffect } from "react";

    export default function Page() {
      const backendBase = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

      const [role, setRole] = useState("Junior Developer");
      const [sessionId, setSessionId] = useState(null);
      const [conversation, setConversation] = useState([]); // [ {q, a, feedback, scores} ]
      const [currentQuestion, setCurrentQuestion] = useState("");
      const [isLoading, setIsLoading] = useState(false);
      const [error, setError] = useState("");

      const endOfConversationRef = useRef(null);
      useEffect(() => {
        endOfConversationRef.current?.scrollIntoView({ behavior: 'smooth' });
      }, [conversation]);

      const handleStartSession = async () => {
        setIsLoading(true);
        setError("");
        setConversation([]);
        
        try {
          const res = await fetch(`${backendBase}/session/start`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ role_profile: role }),
          });
          if (!res.ok) throw new Error("Could not start session.");
          const data = await res.json();
          setSessionId(data.session_id);
          setCurrentQuestion(data.first_question);
        } catch (e) {
          setError(e.message);
        } finally {
          setIsLoading(false);
        }
      };

      const handleSendAnswer = async (answerText) => {
        if (!sessionId || !answerText.trim()) return;
        
        setIsLoading(true);
        setError("");

        // Lägg till användarens fråga och svar direkt i UI
        const newConversation = [...conversation, { q: currentQuestion, a: answerText, feedback: "", scores: null }];
        setConversation(newConversation);
        setCurrentQuestion(""); // Rensa frågan, indikerar att AI:n "tänker"

        try {
          const response = await fetch(`${backendBase}/session/answer`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId, answer_text: answerText.trim() }),
          });

          if (!response.body) throw new Error("No response body");

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let fullResponse = "";

          while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            fullResponse += chunk;
            
            // Uppdatera UI i realtid
            setConversation(prev => {
                const updated = [...prev];
                const lastTurn = updated[updated.length - 1];
                const parts = fullResponse.split('|||');
                lastTurn.feedback = parts[0] || "";
                return updated;
            });
          }
          
          // När streamen är klar, parsa den fullständiga datan
          const parts = fullResponse.split('|||');
          const feedbackText = parts[0]?.trim();
          const scoresJsonText = parts[1]?.trim();
          const nextQuestionText = parts[2]?.trim();

          let scores = null;
          try {
              if(scoresJsonText) scores = JSON.parse(scoresJsonText);
          } catch (e) { console.error("Could not parse scores JSON"); }

          setConversation(prev => {
              const finalUpdate = [...prev];
              const lastTurn = finalUpdate[finalUpdate.length - 1];
              lastTurn.feedback = feedbackText;
              lastTurn.scores = scores;
              return finalUpdate;
          });

          if (nextQuestionText && nextQuestionText !== 'INTERVIEW_COMPLETE') {
            setCurrentQuestion(nextQuestionText);
          } else {
            // Här kan vi anropa /report-endpointen
          }

        } catch (e) {
          setError(e.message);
        } finally {
          setIsLoading(false);
        }
      };

      return (
        <main className="flex flex-col h-screen bg-neutral-950 text-neutral-100 p-4">
          {/* ... UI Komponenter ... */}
          {/* Denna del behöver en Svarskomponent som anropar handleSendAnswer */}
        </main>
      );
    }