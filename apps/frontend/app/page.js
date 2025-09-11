"use client";
import { useMemo, useState, useEffect, useRef } from "react";

export default function Page() {
  const backendBase = useMemo(() => process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000", []);

  const [role, setRole] = useState("Junior Developer");
  const [sessionId, setSessionId] = useState(null);
  const [question, setQuestion] = useState(null);
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [initLoading, setInitLoading] = useState(false);
  const [error, setError] = useState("");
  const [conversation, setConversation] = useState([]);

  // States för slutrapporten
  const [isFinalized, setIsFinalized] = useState(false);
  const [report, setReport] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState("");

  const endOfConversationRef = useRef(null);

  // Skrolla ner automatiskt
  useEffect(() => {
    endOfConversationRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversation, report]);

  // Funktion för att starta en session
  const startSession = async () => {
    setInitLoading(true);
    setError("");
    setConversation([]);
    setReport(null);
    setIsFinalized(false);
    setSessionId(null);
    setQuestion(null);

    try {
      const res = await fetch(`${backendBase}/session/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role_profile: role }),
      });
      if (!res.ok) throw new Error("Could not start session.");
      const data = await res.json();
      setSessionId(data.session_id);
      setQuestion(data.first_question);
    } catch (e) {
      setError(e.message);
    } finally {
      setInitLoading(false);
    }
  };

  // Funktion för att skicka svar
  const sendAnswer = async () => {
    if (!sessionId || !answer.trim()) return;
    setLoading(true);
    setError("");

    const currentTurn = { q: question, a: answer.trim(), feedback: null };
    setConversation(prev => [...prev, currentTurn]);
    setAnswer("");
    setQuestion(null); // Töm frågan direkt för snabbare UI-respons

    try {
      const res = await fetch(`${backendBase}/session/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, answer_text: answer.trim() }),
      });
      if (!res.ok) throw new Error("Could not send answer.");
      const data = await res.json();
      
      setConversation(prev => {
          const updatedConversation = [...prev];
          updatedConversation[updatedConversation.length - 1].feedback = data.feedback;
          return updatedConversation;
      });
      
      if (data.next_question) {
        setQuestion(data.next_question);
      } else {
        setIsFinalized(true); // Intervjun är slut
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  // Effekt som hämtar rapporten när intervjun är klar
  useEffect(() => {
    if (isFinalized && sessionId) {
      const fetchReport = async () => {
        setReportLoading(true);
        setReportError("");
        try {
          const res = await fetch(`${backendBase}/session/${sessionId}/report`);
          if (!res.ok) throw new Error("Could not fetch final report.");
          setReport(await res.json());
        } catch (e) {
          setReportError(e.message);
        } finally {
          setReportLoading(false);
        }
      };
      fetchReport();
    }
  }, [isFinalized, sessionId, backendBase]);

  // Funktion för att formatera rapporten som text
  const exportReportAsText = () => {
      let text = `AI INTERVIEW TRAINER - SLUTRAPPORT\n`;
      text += `=====================================\n\n`;
      text += `Rollprofil: ${role}\n`;
      text += `Session ID: ${sessionId}\n\n`;

      conversation.forEach((turn, index) => {
          text += `FRÅGA ${index + 1}: ${turn.q}\n`;
          text += `DITT SVAR: ${turn.a}\n`;
          if (turn.feedback) {
              text += `FEEDBACK:\n`;
              turn.feedback.bullets.forEach(b => text += `- ${b}\n`);
              if(turn.feedback.scores) {
                  text += `(Content: ${turn.feedback.scores.content}, Structure: ${turn.feedback.scores.structure}, Communication: ${turn.feedback.scores.communication})\n`;
              }
          }
          text += `\n---\n\n`;
      });

      if (report && report.metrics) {
          text += `SAMMANFATTNING\n`;
          text += `-----------------\n`;
          text += `Medelpoäng - Innehåll: ${report.metrics.avg_content}\n`;
          text += `Medelpoäng - Struktur: ${report.metrics.avg_structure}\n`;
          text += `Medelpoäng - Kommunikation: ${report.metrics.avg_communication}\n`;
          text += `Totalpoäng: ${report.metrics.overall_avg} / 100\n\n`;
          text += `Slutsats: ${report.final_summary}\n`;
      }
      return text;
  };
  
  const downloadReport = () => {
      const textContent = exportReportAsText();
      const blob = new Blob([textContent], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `slutrapport-${sessionId}.txt`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
  };

  // --- RENDERINGS-LOGIK ---
  return (
    <main className="min-h-screen bg-neutral-950 text-neutral-100 p-6">
      <header className="max-w-3xl mx-auto mb-6 text-center">
        <h1 className="text-2xl font-semibold">AI Interview Trainer</h1>
        <p className="text-neutral-400">MVP – Next.js + FastAPI</p>
      </header>

      <section className="max-w-3xl mx-auto space-y-4">
        {/* Startvy */}
        {!sessionId && (
          <div className="rounded-2xl border border-neutral-800 p-4">
            <label className="block text-sm mb-2">Rollprofil</label>
            <select className="w-full bg-neutral-900 border border-neutral-800 rounded-xl p-2" value={role} onChange={(e) => setRole(e.target.value)}>
              <option>Junior Developer</option>
              <option>Project Manager</option>
            </select>
            <div className="mt-4">
              <button onClick={startSession} disabled={initLoading} className="px-4 py-2 rounded-xl bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-50">
                {initLoading ? "Startar..." : "Starta intervju"}
              </button>
            </div>
          </div>
        )}

        {/* Konversationshistorik */}
        {conversation.map((turn, index) => (
            <div key={index} className="space-y-2 p-4 rounded-lg bg-neutral-900 border border-neutral-800">
                <p className="font-semibold text-emerald-400">Fråga: {turn.q}</p>
                <p className="pl-4 text-neutral-300">Ditt svar: {turn.a}</p>
                {turn.feedback && (
                    <div className="pl-4 pt-2 mt-2 border-t border-neutral-700">
                        <p className="font-semibold text-sky-400">Feedback:</p>
                        <ul className="list-disc pl-8 text-neutral-400">
                            {turn.feedback.bullets.map((b, i) => <li key={i}>{b}</li>)}
                        </ul>
                        {turn.feedback.scores && (
                            <div className="grid grid-cols-3 gap-2 text-center mt-2">
                                <div className="bg-neutral-800 p-1 rounded"><span className="text-xs">Content:</span> <span className="font-bold">{turn.feedback.scores.content}</span></div>
                                <div className="bg-neutral-800 p-1 rounded"><span className="text-xs">Structure:</span> <span className="font-bold">{turn.feedback.scores.structure}</span></div>
                                <div className="bg-neutral-800 p-1 rounded"><span className="text-xs">Communication:</span> <span className="font-bold">{turn.feedback.scores.communication}</span></div>
                            </div>
                        )}
                    </div>
                )}
            </div>
        ))}
        <div ref={endOfConversationRef}></div>

        {/* Intervju-input eller Slutrapport */}
        {sessionId && (
          <div className="rounded-2xl border border-neutral-800 p-4">
            {question && !isFinalized && (
              <>
                <h2 className="text-lg font-medium mb-2">Aktuell Fråga</h2>
                <p className="text-neutral-200 mb-4">{question}</p>
                <textarea className="w-full h-32 bg-neutral-900 border border-neutral-700 rounded-xl p-3" placeholder="Skriv ditt svar här..." value={answer} onChange={(e) => setAnswer(e.target.value)} disabled={loading}/>
                <div className="mt-3 flex justify-end">
                  <button onClick={sendAnswer} disabled={loading || !answer.trim()} className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20 disabled:opacity-50">
                    {loading ? "Analyserar..." : "Skicka Svar"}
                  </button>
                </div>
              </>
            )}

            {isFinalized && (
              <div className="text-center">
                <h2 className="text-xl font-bold text-emerald-400 mb-4">Intervju Slutförd!</h2>
                {reportLoading && <p>Genererar slutrapport...</p>}
                {reportError && <p className="text-red-500">{reportError}</p>}
                {report && (
                    <div className="animate-fade-in">
                        <p className="mb-4">{report.final_summary}</p>
                        <div className="grid grid-cols-4 gap-2 text-center mb-4">
                            <div className="bg-neutral-900 p-2 rounded">
                                <p className="text-xs">Content</p><p className="font-bold text-lg">{report.metrics.avg_content}</p>
                            </div>
                            <div className="bg-neutral-900 p-2 rounded">
                                <p className="text-xs">Structure</p><p className="font-bold text-lg">{report.metrics.avg_structure}</p>
                            </div>
                            <div className="bg-neutral-900 p-2 rounded">
                                <p className="text-xs">Communication</p><p className="font-bold text-lg">{report.metrics.avg_communication}</p>
                            </div>
                            <div className="bg-emerald-800 p-2 rounded">
                                <p className="text-xs">Overall</p><p className="font-bold text-lg">{report.metrics.overall_avg}</p>
                            </div>
                        </div>
                        <button onClick={downloadReport} className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-500">
                          Ladda ner Rapport (.txt)
                        </button>
                    </div>
                )}
              </div>
            )}
          </div>
        )}
        {error && <p className="mt-2 text-red-500 text-center">Error: {error}</p>}
      </section>
    </main>
  );
}
