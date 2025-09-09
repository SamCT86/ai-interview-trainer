'use client';

import { useState, useRef, useEffect } from 'react';

// En ny komponent för att visa feedback på ett strukturerat sätt
const FeedbackCard = ({ feedback }) => {
  if (!feedback) return null;

  return (
    <div className="mt-2 ml-4 p-4 bg-gray-800 border border-gray-700 rounded-lg animate-fade-in">
      <h3 className="font-semibold text-green-400 mb-2">Feedback Analysis:</h3>

      {/* Poängsektion */}
      {feedback.scores && (
        <div className="flex gap-4 mb-3 text-center">
          <div className="flex-1">
            <p className="text-sm text-gray-400">Content</p>
            <p className="text-xl font-bold text-blue-400">{feedback.scores.content || 0}</p>
          </div>
          <div className="flex-1">
            <p className="text-sm text-gray-400">Structure</p>
            <p className="text-xl font-bold text-blue-400">{feedback.scores.structure || 0}</p>
          </div>
          <div className="flex-1">
            <p className="text-sm text-gray-400">Communication</p>
            <p className="text-xl font-bold text-blue-400">{feedback.scores.communication || 0}</p>
          </div>
        </div>
      )}

      {/* Bullet points */}
      <ul className="list-disc list-inside text-gray-300 space-y-1">
        {feedback.bullets.map((bullet, i) => <li key={i}>{bullet}</li>)}
      </ul>

      {/* Källhänvisningar */}
      {feedback.citations?.length > 0 && (
         <p className="text-xs text-gray-500 mt-3 pt-2 border-t border-gray-700">
           Sources: {feedback.citations.map(c => c.title || 'Unknown Source').join(', ')}
         </p>
      )}
    </div>
  );
};


export default function Home() {
  const [session, setSession] = useState(null);
  const [conversation, setConversation] = useState([]);
  const [currentQuestion, setCurrentQuestion] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [answerText, setAnswerText] = useState('');

  const endOfMessagesRef = useRef(null);

  useEffect(() => {
    endOfMessagesRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversation, currentQuestion]);

  const handleStartSession = async (role) => {
    // ... (samma kod som tidigare)
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

    // Lägg till den nuvarande frågan och svaret i UI direkt för en snabbare upplevelse
    setConversation(prev => [...prev, currentTurn]);
    setCurrentQuestion('');
    setAnswerText('');

    try {
      const response = await fetch('http://127.0.0.1:8000/session/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: session.id, answer_text: answerText }),
      });

      if (!response.ok) throw new Error(`API Error: ${response.status}`);
      const data = await response.json();

      // Uppdatera den sista turnen med feedbacken och sätt nästa fråga
      setConversation(prev => {
          const newConversation = [...prev];
          newConversation[newConversation.length - 1].feedback = data.feedback;
          return newConversation;
      });
      setCurrentQuestion(data.next_question);

    } catch (err) {
      setError(err.message);
      // Om anropet misslyckas, lägg till ett felmeddelande i konversationen
      setConversation(prev => {
          const newConversation = [...prev];
          newConversation[newConversation.length - 1].feedback = { bullets: [`System Error: ${err.message}`], scores: {} };
          return newConversation;
      });
    } finally {
      setIsLoading(false);
    }
  };

  if (!session) {
    // ---- STARTVY ----
    // ... (samma kod som tidigare)
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
    <main className="flex flex-col h-screen bg-gray-900 text-white">
      <header className="p-4 border-b border-gray-700 text-center sticky top-0 bg-gray-900 z-10">
        <h1 className="text-2xl font-bold">Interview for: <span className="text-blue-400">{session.role}</span></h1>
        <p className="text-sm text-gray-500 font-mono">Session ID: {session.id}</p>
      </header>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {conversation.map((turn, index) => (
          <div key={index}>
            <p className="text-lg text-blue-300 font-semibold">{turn.q}</p>
            <p className="text-gray-200 my-2 p-3 bg-gray-800 rounded-r-lg rounded-bl-lg">{turn.a}</p>
            <FeedbackCard feedback={turn.feedback} />
          </div>
        ))}

        {currentQuestion && (
          <div>
            <p className="text-lg text-blue-300 font-semibold">{currentQuestion}</p>
          </div>
        )}
         {isLoading && <p className="text-center text-gray-400">AI is thinking...</p>}
        <div ref={endOfMessagesRef} />
      </div>

      <footer className="p-4 border-t border-gray-700 sticky bottom-0 bg-gray-900 z-10">
        {currentQuestion ? (
          <div className="flex gap-4">
            <textarea
              value={answerText}
              onChange={(e) => setAnswerText(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSendAnswer(); } }}
              disabled={isLoading}
              placeholder="Type your answer here... (Shift+Enter for new line)"
              className="flex-1 p-3 bg-gray-800 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none resize-none"
              rows={2}
            />
            <button onClick={handleSendAnswer} disabled={isLoading || !answerText.trim()} className="px-6 py-3 bg-blue-600 rounded-lg hover:bg-blue-700 disabled:bg-gray-500">
              Send
            </button>
          </div>
        ) : (
          <div className="text-center">
              <p className="text-green-400 font-bold">Interview Complete!</p>
              <button onClick={() => setSession(null)} className="mt-4 px-6 py-3 bg-gray-600 rounded-lg hover:bg-gray-700">Start New Interview</button>
          </div>
        )}
        {error && <p className="mt-2 text-red-500 text-center">Error: {error}</p>}
      </footer>
    </main>
  );