"use client";
import { useMemo, useState, useEffect } from "react";

export default function Page() {
  const backendBase = useMemo(() => process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000", []);
  const [role, setRole] = useState("Junior Developer");
  const [sessionId, setSessionId] = useState(null);
  const [question, setQuestion] = useState(null);
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState(null);
  const [loading, setLoading] = useState(false);
  const [initLoading, setInitLoading] = useState(false);
  const [error, setError] = useState("");
  const [answers, setAnswers] = useState([]);
  const [finalized, setFinalized] = useState(false);
  const [report, setReport] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState("");
  const [inputError, setInputError] = useState(false);

  // Focus input när fråga kommer
  useEffect(() => {
    if (question) {
      const ta = document.querySelector("textarea");
      ta?.focus();
    }
  }, [question]);

  // Klick-utanför → blinka röd ram + focus
  useEffect(() => {
    if (!question) return;
    const handleClickOutside = (e) => {
      const ta = document.querySelector("textarea");
      if (ta && !ta.contains(e.target)) {
        setInputError(true);
        ta.focus();
        setTimeout(() => setInputError(false), 600);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [question]);

  // Starta session
  const startSession = async () => {
    setInitLoading(true);
    setError("");
    const callStart = async (attempt = 1) => {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 25000);
      try {
        const res = await fetch(`${backendBase}/session/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ role_profile: role }),
          signal: ctrl.signal,
        });
        clearTimeout(t);
        if (!res.ok) throw new Error("Start failed");
        const data = await res.json();
        setSessionId(data.session_id);
        setQuestion(data.first_question);
      } catch (e) {
        clearTimeout(t);
        if (attempt === 1) {
          await new Promise((r) => setTimeout(r, 1500));
          return callStart(2);
        }
        setError(e?.message || "Kunde inte starta session.");
      } finally {
        setInitLoading(false);
      }
    };
    await callStart(1);
  };

  const sendAnswer = async () => {
    if (!sessionId || !answer.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(`${backendBase}/session/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, answer_text: answer.trim() }),
      });
      if (!res.ok) throw new Error("Answer failed");
      const data = await res.json();
      setAnswers((prev) => [...prev, { q: question || "", a: answer.trim(), fbBullets: data?.feedback?.bullets || [] }]);
      setFeedback(data.feedback || null);
      setQuestion(data.next_question || null);
      setAnswer("");
    } catch (e) {
      setError(e.message || "Kunde inte skicka svaret.");
    } finally {
      setLoading(false);
    }
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!loading) sendAnswer();
    }
  };

  useEffect(() => {
    if (sessionId && !question && !initLoading && !loading && answers.length > 0) {
      setFinalized(true);
    }
  }, [sessionId, question, initLoading, loading, answers.length]);

  useEffect(() => {
    if (finalized && sessionId) {
      (async () => {
        setReportLoading(true);
        try {
          const res = await fetch(`${backendBase}/session/${sessionId}/report`);
          if (!res.ok) throw new Error("Report failed");
          setReport(await res.json());
        } catch (e) {
          setReportError(e.message || "Kunde inte hämta rapport.");
        } finally {
          setReportLoading(false);
        }
      })();
    }
  }, [finalized, sessionId, backendBase]);

  return (
   <main className="min-h-screen bg-neutral-950 text-neutral-100 p-6">
  <header className="max-w-3xl mx-auto mb-6">
    <h1 className="text-2xl font-semibold">AI Interview Trainer</h1>
    <p className="text-neutral-400">MVP – Next.js + FastAPI</p>
  </header>

  <section className="max-w-3xl mx-auto space-y-4">
    {/* Rollval + Start */}
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
      <p className="text-sm text-neutral-400 mt-3">
        Välj roll och klicka på <span className="font-medium text-neutral-200">Starta intervju</span>.
      </p>
      <div className="mt-4 flex items-center gap-3">
        <button
          onClick={startSession}
          disabled={initLoading}
          style={{
            backgroundColor: initLoading ? "#6b7280" : "#10b981",
            color: "#ffffff",
            padding: "0.5rem 1rem",
            borderRadius: "0.75rem",
            border: "none",
            cursor: initLoading ? "not-allowed" : "pointer",
            opacity: initLoading ? 0.6 : 1,
          }}
        >
          {initLoading ? "Startar…" : "Starta intervju"}
        </button>
        {sessionId && <span className="text-xs text-neutral-400">Session: {sessionId}</span>}
      </div>
      {initLoading && (
        <div className="mt-4">
          <div className="w-full bg-neutral-800 rounded-full h-2.5">
            <div className="bg-emerald-500 h-2.5 rounded-full animate-pulse" style={{ width: "100%" }}></div>
          </div>
          <p className="text-xs text-neutral-400 mt-2">Väcker backend – tar max 15 s första gången…</p>
        </div>
      )}
    </div>

    {/* Fråga */}
    <div className="rounded-2xl border border-neutral-800 p-4">
      <h2 className="text-lg font-medium mb-2" style={{ color: question ? "#10b981" : "#a3a3a3" }}>
        Fråga
      </h2>
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

    {/* Svar + utanför-klick-indikator */}
    <div
      className="rounded-2xl border border-neutral-800 p-4 relative"
      style={{ borderColor: inputError ? "#ef4444" : "#404040" }}
    >
      <h2 className="text-lg font-medium mb-2" style={{ color: question ? "#10b981" : "#a3a3a3" }}>
        Ditt svar
      </h2>
      <textarea
        placeholder={question || "Skriv ditt svar här… (Shift+Enter för ny rad)"}
        className="w-full h-32 bg-neutral-900 border rounded-xl p-3 focus:outline-none placeholder:text-neutral-500"
        style={{
          borderColor: inputError ? "#ef4444" : "#525252",
          boxShadow: inputError ? "0 0 10px #ef4444" : "none",
        }}
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (!loading) sendAnswer();
          }
        }}
        disabled={!sessionId || loading}
      />
      <div className="mt-3 flex justify-end">
        <button
          onClick={sendAnswer}
          disabled={!sessionId || loading || !answer.trim()}
          style={{
            backgroundColor: "#ffffff1a",
            color: "#fff",
            padding: "0.5rem 1rem",
            borderRadius: "0.75rem",
            border: "1px solid #ffffff1a",
            cursor: !sessionId || loading || !answer.trim() ? "not-allowed" : "pointer",
            opacity: !sessionId || loading || !answer.trim() ? 0.5 : 1,
          }}
          onMouseEnter={(e) => !loading && (e.currentTarget.style.backgroundColor = "#ffffff2a")}
          onMouseLeave={(e) => !loading && (e.currentTarget.style.backgroundColor = "#ffffff1a")}
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
        <ul className="list-disc pl-6 space-y-1">
          {feedback.bullets?.map((b, i) => (
            <li key={i} className="text-neutral-300">
              {b}
            </li>
          ))}
        </ul>
      )}
    </div>

    {error && <p className="mt-2 text-red-500 text-center">Error: {error}</p>}

    {sessionId && !question && !initLoading && !loading && answers.length > 0 && (
      <div className="rounded-2xl border border-neutral-800 p-4 space-y-3">
        <h3 className="text-lg font-semibold">🎯 Slutrapport</h3>
        {reportLoading && <p className="text-neutral-400">Genererar rapport…</p>}
        {reportError && <p className="text-red-400">Rapportfel: {reportError}</p>}
        {report?.metrics && (
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
            <div className="rounded-xl border border-neutral-800 p-3 bg-neutral-900">
              <p className="text-xs text-neutral-400">Content</p>
              <p className="text-xl font-semibold">{report.metrics.avg_content}</p>
            </div>
            <div className="rounded-xl border border-neutral-800 p-3 bg-neutral-900">
              <p className="text-xs text-neutral-400">Structure</p>
              <p className="text-xl font-semibold">{report.metrics.avg_structure}</p>
            </div>
            <div className="rounded-xl border border-neutral-800 p-3 bg-neutral-900">
              <p className="text-xs text-neutral-400">Communication</p>
              <p className="text-xl font-semibold">{report.metrics.avg_communication}</p>
            </div>
            <div className="rounded-xl border border-neutral-800 p-3 bg-neutral-900">
              <p className="text-xs text-neutral-400">Overall</p>
              <p className="text-xl font-semibold">{report.metrics.overall_avg}</p>
            </div>
          </div>
        )}
        <div className="rounded-xl border border-neutral-800 p-3 bg-neutral-900 max-h-64 overflow-auto">
          <ol className="list-decimal pl-5 space-y-2">
            {answers.map((it, idx) => (
              <li key={idx}>
                <p className="text-neutral-200">
                  <span className="font-medium">Fråga:</span> {it.q}
                </p>
                <p className="text-neutral-300">
                  <span className="font-medium">Ditt svar:</span> {it.a}
                </p>
                {it.fbBullets?.length > 0 && (
                  <ul className="list-disc pl-5 mt-1">
                    {it.fbBullets.map((b, i) => (
                      <li key={i} className="text-neutral-400">
                        {b}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ol>
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => {
              const blob = new Blob([exportText(answers, report)], { type: "text/plain;charset=utf-8" });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = "ai-interview-trainer-slutrapport.txt";
              a.click();
              URL.revokeObjectURL(url);
            }}
            className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20"
          >
            Ladda ner .txt
          </button>
        </div>
      </div>
    )}

    <footer className="max-w-3xl mx-auto mt-10 text-xs text-neutral-500">Backend: {backendBase}</footer>
  </main>
);