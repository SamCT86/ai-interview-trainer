"use client";

import { useMemo, useState, useEffect } from "react";

export default function Page() {
  const backendBase = useMemo(() => {
    return process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";
  }, []);

  const [role, setRole] = useState("Junior Developer");
  const [sessionId, setSessionId] = useState(null);
  const [question, setQuestion] = useState(null);
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState(null);
  const [loading, setLoading] = useState(false);
  const [initLoading, setInitLoading] = useState(false);
  const [error, setError] = useState("");

  // Lokal historik + UI-resultat
  const [answers, setAnswers] = useState([]);   // [{q, a, fbBullets: []}]
  const [finalized, setFinalized] = useState(false);

  // Backendrapport
  const [report, setReport] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState("");

  const computeLocalScore = (items) => {
    const bullets = items.reduce(
      (acc, it) => acc + (Array.isArray(it.fbBullets) ? it.fbBullets.length : 0),
      0
    );
    return Math.max(40, 100 - bullets * 8);
  };

  const exportText = (items, rep) => {
    const lines = [];
    lines.push("AI Interview Trainer — Slutrapport\n");
    items.forEach((it, i) => {
      lines.push(Fråga : );
      lines.push(Svar: );
      if (it.fbBullets?.length) {
        lines.push("Feedback:");
        it.fbBullets.forEach((b) => lines.push(- ));
      }
      lines.push("");
    });
    if (rep?.metrics) {
      lines.push("== Sammanlagda betyg (backend) ==");
      lines.push(Content: /100);
      lines.push(Structure: /100);
      lines.push(Communication: /100);
      lines.push(Overall: /100);
    } else {
      lines.push(== Heuristisk poäng (lokal) ==);
      lines.push(Overall: /100);
    }
    if (rep?.final_summary) {
      lines.push("");
      lines.push("Sammanfattning:");
      lines.push(rep.final_summary);
    }
    return lines.join("\n");
  };

  const hardReset = () => {
    setSessionId(null);
    setQuestion(null);
    setAnswer("");
    setFeedback(null);
    setError("");
    setAnswers([]);
    setFinalized(false);
    setReport(null);
    setReportError("");
    setReportLoading(false);
  };

  const startSession = async () => {
    hardReset();
    setInitLoading(true);
    try {
      const res = await fetch(${backendBase}/session/start, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role_profile: role }),
      });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(Start failed:  );
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
      const res = await fetch(${backendBase}/session/answer, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          answer_text: answer.trim(),
        }),
      });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(Answer failed:  );
      }
      const data = await res.json();

      setAnswers((prev) => [
        ...prev,
        {
          q: question || "",
          a: answer.trim(),
          fbBullets: data?.feedback?.bullets || [],
        },
      ]);

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

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!loading) sendAnswer();
    }
  };

  // När intervjun är slut: visa resultat + hämta slutrapport
  useEffect(() => {
    const ended = sessionId && !question && !initLoading && !loading && answers.length > 0;
    if (!ended) return;

    setFinalized(true);

    const fetchReport = async () => {
      try {
        setReportLoading(true);
        setReportError("");
        const res = await fetch(${backendBase}/session//report);
        if (!res.ok) {
          const txt = await res.text();
          throw new Error(Report failed:  );
        }
        const data = await res.json();
        setReport(data);
      } catch (err) {
        setReportError(err.message || "Kunde inte hämta slutrapporten.");
        setReport(null);
      } finally {
        setReportLoading(false);
      }
    };
    fetchReport();
  }, [sessionId, question, initLoading, loading, answers.length, backendBase]);

  return (
    <main className="min-h-screen bg-neutral-950 text-neutral-100 p-6">
      <header className="max-w-3xl mx-auto mb-6">
        <h1 className="text-2xl font-semibold">AI Interview Trainer</h1>
        <p className="text-neutral-400">MVP – Next.js + FastAPI</p>
      </header>

      <section className="max-w-3xl mx-auto space-y-4">
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
            Välj roll och klicka på <span className="font-medium text-neutral-200">Starta intervju</span> för att börja.
          </p>

          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={startSession}
              disabled={initLoading}
              className="px-4 py-2 rounded-xl bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-50"
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

        <div className="rounded-2xl border border-neutral-800 p-4">
          <h2 className="text-lg font-medium mb-2">Fråga</h2>
          <div className="min-h-12 text-neutral-200">
            {question ? <p>{question}</p> : initLoading ? <p>Initialiserar session…</p> : <p className="text-neutral-500">Ingen aktiv fråga ännu.</p>}
          </div>
        </div>

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

        <div className="rounded-2xl border border-neutral-800 p-4">
          <h2 className="text-lg font-medium mb-2">Feedback</h2>
          {!feedback ? (
            <p className="text-neutral-500">Ingen feedback ännu.</p>
          ) : (
            <div className="space-y-2">
              <p className="text-neutral-200">{feedback.summary}</p>
              {Array.isArray(feedback.bullets) && feedback.bullets.length > 0 && (
                <ul className="list-disc pl-6 space-y-1">
                  {feedback.bullets.map((b, i) => <li key={i}>{b}</li>)}
                </ul>
              )}
            </div>
          )}
        </div>

        {error && <p className="mt-2 text-red-500 text-center">Error: {error}</p>}

        {sessionId && !question && !initLoading && !loading && (
          <div className="rounded-2xl border border-neutral-800 p-4 space-y-3">
            {!finalized ? (
              <>
                <p className="text-neutral-200 font-medium">Slut på frågor ✅</p>
                <p className="text-neutral-400">Klicka nedan för att generera en sammanfattning och poäng.</p>
                <div className="flex gap-3">
                  <button onClick={() => setFinalized(true)} className="px-4 py-2 rounded-xl bg-emerald-600 text-white hover:bg-emerald-500">Visa resultat</button>
                  <button onClick={startSession} className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20">Starta om intervju</button>
                </div>
              </>
            ) : (
              <>
                <h3 className="text-lg font-semibold">🎯 Slutrapport</h3>

                {reportLoading && <p className="text-neutral-400">Genererar rapport…</p>}
                {reportError && <p className="text-red-400">Rapportfel: {reportError}</p>}

                {report?.metrics ? (
                  <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                    <div className="rounded-xl border border-neutral-800 p-3 bg-neutral-900"><p className="text-xs text-neutral-400">Content</p><p className="text-xl font-semibold">{report.metrics.avg_content}</p></div>
                    <div className="rounded-xl border border-neutral-800 p-3 bg-neutral-900"><p className="text-xs text-neutral-400">Structure</p><p className="text-xl font-semibold">{report.metrics.avg_structure}</p></div>
                    <div className="rounded-xl border border-neutral-800 p-3 bg-neutral-900"><p className="text-xs text-neutral-400">Communication</p><p className="text-xl font-semibold">{report.metrics.avg_communication}</p></div>
                    <div className="rounded-xl border border-neutral-800 p-3 bg-neutral-900"><p className="text-xs text-neutral-400">Overall</p><p className="text-xl font-semibold">{report.metrics.overall_avg}</p></div>
                  </div>
                ) : (
                  <p className="text-neutral-400">(Visar heuristisk poäng lokalt: <span className="font-semibold">{computeLocalScore(answers)}</span>/100)</p>
                )}

                {report?.final_summary && (
                  <div className="rounded-xl border border-neutral-800 p-3 bg-neutral-900">
                    <p className="text-neutral-200 whitespace-pre-wrap">{report.final_summary}</p>
                  </div>
                )}

                <div className="rounded-xl border border-neutral-800 p-3 bg-neutral-900 max-h-64 overflow-auto">
                  <ol className="list-decimal pl-5 space-y-2">
                    {answers.map((it, idx) => (
                      <li key={idx}>
                        <p className="text-neutral-200"><span className="font-medium">Fråga:</span> {it.q}</p>
                        <p className="text-neutral-300"><span className="font-medium">Ditt svar:</span> {it.a}</p>
                        {it.fbBullets?.length > 0 && (
                          <ul className="list-disc pl-5 mt-1">
                            {it.fbBullets.map((b, i) => (<li key={i} className="text-neutral-400">{b}</li>))}
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
                      a.href = url; a.download = "ai-interview-trainer-slutrapport.txt"; a.click();
                      URL.revokeObjectURL(url);
                    }}
                    className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20"
                  >
                    Ladda ner .txt
                  </button>
                  <button
                    onClick={async () => {
                      try { await navigator.clipboard.writeText(exportText(answers, report)); alert("Slutrapport kopierad till urklipp."); }
                      catch { alert("Kunde inte kopiera – ladda ner .txt istället."); }
                    }}
                    className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20"
                  >
                    Kopiera sammanfattning
                  </button>
                  <button onClick={hardReset} className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20">Starta ny intervju</button>
                </div>
              </>
            )}
          </div>
        )}
      </section>

      <footer className="max-w-3xl mx-auto mt-10 text-xs text-neutral-500">
        Backend: {backendBase}
      </footer>
    </main>
  );
}
