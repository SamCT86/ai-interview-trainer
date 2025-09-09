"use client";

import { useEffect, useMemo, useState } from "react";

export default function Page() {
  // --- Config ---
  const backendBase = useMemo(() => {
    // Prod från Vercel env, fallback lokalt
    return process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";
  }, []);

  // --- UI State ---
  const [role, setRole] = useState("Junior Developer");
  const [sessionId, setSessionId] = useState(null);
  const [question, setQuestion] = useState(null);
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState(null);
  const [loading, setLoading] = useState(false);
  const [initLoading, setInitLoading] = useState(false);
  const [error, setError] = useState("");

  // --- Helpers ---
  const resetUI = () => {
    setSessionId(null);
    setQuestion(null);
    setAnswer("");
    setFeedback(null);
    setError("");
  };

  // --- Actions ---
  const startSession = async () => {
    resetUI();
    setInitLoading(true);
    try {
      const res = await fetch(`${backendBase}/session/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role_profile: role }),
      });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(`Start failed: ${res.status} ${txt}`);
      }
      const data = await res.json();
      setSessionId(data.session_id);
      setQuestion(data.first_question);
      setError("");
    } catch (e) {
      setError(e.message || "Något gick fel vid start av session.");
    } finally {
      setInitLoading(false);
    }
  };

  const sendAnswer = async () => {
    if (!sessionId || !answer.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(`${backendBase}/session/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          answer_text: answer.trim(),
        }),
      });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(`Answer failed: ${res.status} ${txt}`);
      }
      const data = await res.json();
      setFeedback(data.feedback || null);
      setQuestion(data.next_question || null);
      setAnswer("");
      setError("");
    } catch (e) {
      setError(e.message || "Något gick fel när svaret skickades.");
    } finally {
      setLoading(false);
    }
  };

  // Enter skickar, Shift+Enter ny rad
  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!loading) sendAnswer();
    }
  };

  // --- UI ---
  return (
    <main className="min-h-screen bg-neutral-950 text-neutral-100 p-6">
      <header className="max-w-3xl mx-auto mb-6">
        <h1 className="text-2xl font-semibold">AI Interview Trainer</h1>
        <p className="text-neutral-400">MVP – Next.js + FastAPI</p>
      </header>

      <section className="max-w-3xl mx-auto space-y-4">
        {/* Controls */}
        <div className="rounded-2xl border border-neutral-800 p-4">
          <label className="block text-sm mb-2">Rollprofil</label>
          <select
            className="w-full bg-neutral-900 border border-neutral-800 rounded-xl p-2"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            disabled={initLoading || loading}
          >
            <option>Junior Developer</option>
            <option>Project Manager</option>
          </select>

          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={startSession}
              disabled={initLoading}
              className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20 disabled:opacity-50"
            >
              {initLoading ? "Initierar..." : "Starta intervju"}
            </button>

            {sessionId && (
              <span className="text-xs text-neutral-400">
                Session: {sessionId}
              </span>
            )}
          </div>
        </div>

        {/* Question */}
        <div className="rounded-2xl border border-neutral-800 p-4">
          <h2 className="text-lg font-medium mb-2">Fråga</h2>
          <div className="min-h-12 text-neutral-200">
            {question ? (
              <p>{question}</p>
            ) : initLoading ? (
              <p>Initialiserar session…</p>
            ) : (
              <p className="text-neutral-500">Ingen aktiv fråga ännu.</p>
            )}
          </div>
        </div>

        {/* Answer input */}
        <div className="rounded-2xl border border-neutral-800 p-4">
          <h2 className="text-lg font-medium mb-2">Ditt svar</h2>
          <textarea
            className="w-full h-32 bg-neutral-900 border border-neutral-800 rounded-xl p-3"
            placeholder="Skriv ditt svar här… (Shift+Enter för ny rad)"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={!sessionId || loading}
          />
          <div className="mt-3 flex justify-end">
            <button
              onClick={sendAnswer}
              disabled={!sessionId || loading || !answer.trim()}
              className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20 disabled:opacity-50"
            >
              {loading ? "Skickar…" : "Skicka"}
            </button>
          </div>
        </div>

        {/* Feedback */}
        <div className="rounded-2xl border border-neutral-800 p-4">
          <h2 className="text-lg font-medium mb-2">Feedback</h2>
          {!feedback ? (
            <p className="text-neutral-500">Ingen feedback ännu.</p>
          ) : (
            <div className="space-y-2">
              <p className="text-neutral-200">{feedback.summary}</p>
              {Array.isArray(feedback.bullets) && feedback.bullets.length > 0 && (
                <ul className="list-disc pl-6 space-y-1">
                  {feedback.bullets.map((b, i) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        {/* Status/Error */}
        {error && (
          <p className="mt-2 text-red-500 text-center">
            Error: {error}
          </p>
        )}

        {/* End of questions */}
        {sessionId && !question && !initLoading && !loading && (
          <div className="rounded-2xl border border-neutral-800 p-4 text-center">
            <p className="text-neutral-200 mb-2">Slut på frågor ✅</p>
            <button
              onClick={startSession}
              className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20"
            >
              Starta om intervju
            </button>
          </div>
        )}
      </section>

      <footer className="max-w-3xl mx-auto mt-10 text-xs text-neutral-500">
        Backend: {backendBase}
      </footer>
    </main>
  );
}