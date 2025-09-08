'use client';

import { useState, useRef, useEffect } from 'react';

export default function Home() {
  // State för att hantera hela sessionen
  const [session, setSession] = useState(null); // Innehåller session_id och role_profile
  const [conversation, setConversation] = useState([]); // [ {q: 'fråga', a: 'svar', feedback: {...} } ]
  const [currentQuestion, setCurrentQuestion] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [answerText, setAnswerText] = useState('');

  const endOfMessagesRef = useRef(null);

  // Skrolla ner automatiskt när nya meddelanden dyker upp
  useEffect(() => {
    endOfMessagesRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversation]);

  const handleStartSession = async (role) => {
    setIsLoading(true);
    setError('');
    setConversation([]);
    setCurrentQuestion('');

    try {
      const response = await fetch('http://127.0.0.1:8000/session/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role_profile: role }),
      });

      if (!response.ok) throw new Error(`API Error: ${response.status}`);
      const data = await response.json();

      setSession({ id: data.session_id, role: role });
      setCurrentQuestion(data.first_question);

    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendAnswer = async () => {
    if (!answerText.trim() || !session) return;

    setIsLoading(true);
    setError('');

    const currentTurn = { q: currentQuestion, a: answerText, feedback: null };

    try {
      const response = await fetch('http://127.0.0.1:8000/session/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: session.id, answer_text: answerText }),
      });

      if (!response.ok) throw new Error(`API Error: ${response.status}`);
      const data = await response.json();

      // Uppdatera konversationen med feedback och sätt nästa fråga
      currentTurn.feedback = data.feedback;
      setConversation(prev => [...prev, currentTurn]);
      setCurrentQuestion(data.next_question);
      setAnswerText(''); // Rensa textrutan

    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // ---- RENDERINGS-LOGIK ----

  if (!session) {
    // ---- STARTVY ----
    return (
      <main className="flex min-h-screen flex-col items-center justify-center p-24 bg-gray-900 text-white">
        <div className="text-center">
          <h1 className="text-4xl font-bold mb-4">AI Interview Trainer</h1>
          <p className="text-lg text-gray-400 mb-8">Select a role to start your mock interview.</p>
          <div className="flex gap-4 justify-center">
            <button onClick={() => handleStartSession('Junior Developer')} disabled={isLoading} className="px-6 py-3 bg-blue-600 rounded-lg hover:bg-blue-700 disabled:bg-gray-500">Start as Junior Dev</button>
            <button onClick={() => handleStartSession('Project Manager')} disabled={isLoading} className="px-6 py-3 bg-green-600 rounded-lg hover:bg-green-700 disabled:bg-gray-500">Start as Project Manager</button>
          </div>
          {isLoading && <p className="mt-4">Initializing session...</p>}
          {error && <p className="mt-4 text-red-500">Error: {error}</p>}
        </div>
      </main>
    );
  }

  // ---- INTERVJUVY ----
  return (
    <main className="flex flex-col h-screen bg-gray-900 text-white p-4">
      <header className="p-4 border-b border-gray-700 text-center">
        <h1 className="text-2xl font-bold">Interview for: <span className="text-blue-400">{session.role}</span></h1>
        <p className="text-sm text-gray-500 font-mono">Session ID: {session.id}</p>
      </header>

      <div className="flex-1 overflow-y-auto p-4 space-y-8">
        {conversation.map((turn, index) => (
          <div key={index}>
            <p className="text-blue-300 font-semibold">Q: {turn.q}</p>
            <p className="text-gray-300 ml-4">{turn.a}</p>
            {turn.feedback && (
              <div className="mt-2 ml-4 p-3 bg-gray-800 border border-gray-700 rounded-lg">
                <h3 className="font-semibold text-green-400">Feedback:</h3>
                <ul className="list-disc list-inside text-gray-300">
                  {turn.feedback.bullets.map((bullet, i) => <li key={i}>{bullet}</li>)}
                </ul>
                {turn.feedback.citations?.length > 0 && (
                   <p className="text-xs text-gray-500 mt-2">Sources: {turn.feedback.citations.map(c => c.title).join(', ')}</p>
                )}
              </div>
            )}
          </div>
        ))}

        {currentQuestion && (
          <div>
            <p className="text-blue-300 font-semibold">Q: {currentQuestion}</p>
          </div>
        )}
        <div ref={endOfMessagesRef} />
      </div>

      <footer className="p-4 border-t border-gray-700">
        {currentQuestion ? (
          <div className="flex gap-4">
            <textarea
              value={answerText}
              onChange={(e) => setAnswerText(e.target.value)}
              disabled={isLoading}
              placeholder="Type your answer here..."
              className="flex-1 p-3 bg-gray-800 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              rows={3}
            />
            <button onClick={handleSendAnswer} disabled={isLoading || !answerText.trim()} className="px-6 py-3 bg-blue-600 rounded-lg hover:bg-blue-700 disabled:bg-gray-500">
              {isLoading ? 'Processing...' : 'Send Answer'}
            </button>
          </div>
        ) : (
          <p className="text-center text-green-400 font-bold">Interview Complete!</p>
        )}
        {error && <p className="mt-2 text-red-500 text-center">Error: {error}</p>}
      </footer>
    </main>
  );
}