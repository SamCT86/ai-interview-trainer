"use client";
import { useState } from "react";

export default function Home() {
  const [role, setRole] = useState("Junior Backend Developer");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [session, setSession] = useState(null);

  const startSession = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_BACKEND_URL}/session/start`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ role_profile: role }),
        }
      );
      if (!res.ok) {
        const t = await res.text();
        throw new Error(`API error: ${res.status} ${t}`);
      }
      const data = await res.json();
      setSession(data);
    } catch (e) {
      setError(e.message || "Failed to start session");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
      <div className="w-full max-w-xl bg-white rounded-2xl shadow p-6 space-y-6">
        <h1 className="text-2xl font-bold">AI Interview Trainer</h1>

        <div className="space-y-2">
          <label className="text-sm font-medium">Role profile</label>
          <select
            className="w-full rounded-xl border p-2"
            value={role}
            onChange={(e) => setRole(e.target.value)}
          >
            <option>Junior Backend Developer</option>
            <option>Senior Project Manager</option>
            <option>Frontend Engineer</option>
            <option>Data Scientist</option>
          </select>
        </div>

        <button
          onClick={startSession}
          disabled={loading}
          className="w-full rounded-2xl border bg-black text-white py-2 font-medium disabled:opacity-50"
        >
          {loading ? "Starting…" : "Start Interview"}
        </button>

        {error && (
          <div className="rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {session && (
          <div className="rounded-2xl border p-4 space-y-2">
            <div className="text-sm text-gray-500">Session ID</div>
            <div className="font-mono break-all">{session.session_id}</div>
            <div className="text-sm text-gray-500 pt-2">First Question</div>
            <div className="font-medium">{session.first_question}</div>
          </div>
        )}

        <p className="text-xs text-gray-500">
          Backend: {process.env.NEXT_PUBLIC_BACKEND_URL}
        </p>
      </div>
    </main>
  );
}