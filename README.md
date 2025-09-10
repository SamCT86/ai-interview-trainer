# 🎯 AI Interview Trainer

Your personal AI-powered mock interview coach — practice real interviews, get instant feedback, and track your progress.
> Fullstack AI app: **Next.js (App Router)** + **FastAPI** + **Supabase (Postgres + pgvector)**.  
> Deployed to **Vercel** (frontend) & **Render** (API). CI/CD via **GitHub Actions**.

---

## 🚀 Live Demo

- 🌐 **Frontend (Vercel):** https://ai-interview-trainer-frontend-tawny.vercel.app  
- ⚡ **Backend API Docs (Render/Swagger):** https://ai-interview-trainer-api.onrender.com/docs
 
---

## ✨ What It Does (Overview)

**AI Interview Trainer** simulates realistic interviews for different roles. It asks **role-specific questions**, generates **smart follow-ups** based on your answers, and provides **structured, quantitative feedback** after each response.  
At the end, it produces a **summary report** with average scores and an overall assessment.

**Use cases**
- Job-seekers who want realistic practice.
- Bootcamp/education programs that need a self-serve interview prep tool.
- Teams running mock interviews internally.

---

## 🔑 Features

- 🎭 **Role-based interviews** (e.g., Junior Developer, Project Manager).
- 🤖 **Dynamic AI**: unique follow-up questions using **Gemini 1.5 Flash** via **LiteLLM**.
- 📝 **Structured scoring** per answer: *content, structure, communication*.
- 📊 **Final report**: session summary with per-category averages.
- 🔎 **Vector search**: **pgvector** to ground follow-ups in relevant context.
- 🌙 **Modern UI**: Next.js + TailwindCSS, dark mode, smooth animations.
- 🧪 **Tested backend**: pytest for core flows.
- 🔄 **CI/CD**: GitHub Actions, auto-deploys to Vercel/Render.

---

## 🧰 Tech Stack

**Frontend:** Next.js (App Router), React, TailwindCSS  
**Backend:** FastAPI, SQLAlchemy, pydantic  
**Data:** Supabase (Postgres + pgvector), psycopg v3  
**AI/LLM:** Gemini 1.5 Flash via LiteLLM  
**Infra/DevOps:** Vercel (FE), Render (API), GitHub Actions (CI/CD), CORS hardened

---

## 🗺️ Architecture (High Level)

[User] → Next.js (Vercel) → FastAPI (Render) → Supabase (Postgres + pgvector)
│
└─ LiteLLM → Gemini 1.5 Flash (Q&A + feedback)

---

## 📂 Project Structure

apps/
frontend/ # Next.js (App Router), Tailwind, API calls
backend/ # FastAPI app, routers, services, models
infra/
vercel/ # (optional) Vercel config
render/ # (optional) Render config
.github/
workflows/ # CI: lint, test, build/deploy

---

## 🔌 API (Core Endpoints)

```http
GET  /               # health check
GET  /docs           # Swagger UI
POST /session/start  # start a new interview session
POST /session/answer # submit answer → get feedback + next question
/session/start (request)

{
  "role_profile": "Junior Developer"
}

⚙️ Local Setup

Prereqs
Node.js LTS, Python 3.11+, Docker (optional), Supabase project (or Postgres)

API keys: Gemini via LiteLLM (or your LLM provider)

1) Backend

cd apps/backend
python -m venv venv
source venv/bin/activate   # Mac/Linux
.\venv\Scripts\activate    # Windows
pip install -r requirements.txt

# set env (see .env example below)
uvicorn main:app --reload

2) Frontend

cd apps/frontend
npm install
npm run dev
3) Environment (.env examples)
apps/backend/.env

DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
SUPABASE_URL=https://YOUR-PROJECT.supabase.co
SUPABASE_ANON_KEY=YOUR-ANON-KEY
LITELLM_API_BASE=https://api.litellm.ai
LITELLM_API_KEY=YOUR-LITELLM-KEY
MODEL_NAME=gemini/gemini-1.5-flash
CORS_ORIGINS=http://localhost:3000,https://*.vercel.app
apps/frontend/.env.local

NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
Security: never commit real keys. Use GitHub Actions secrets for CI/CD.

🧪 Testing

Backend (pytest): session creation, DB connection, scoring pipeline smoke tests.

cd apps/backend
pytest -q
Planned: integration tests for /session/answer.

🔄 CI/CD

GitHub Actions: lint + tests on every PR/commit
Vercel: auto-deploy frontend on main
Render: auto-deploy FastAPI with health checks

📊 Metrics & Logs

Supabase: query logs
Vercel: analytics on frontend
Render: API logs (request/response status, error traces)

🔒 Security & Privacy (Basics)

CORS restricted (localhost + trusted domains)
Minimal PII storage (only session metadata needed)
Do not log raw answers with user identifiers in production

🧭 Roadmap

 Additional roles (Data Analyst, Product Owner)
 Session history & progress tracking
 Audio input + speech-to-text
 Improved scoring rubric per role
 Exportable PDF report

🧠 Why This Project Matters (Portfolio Signal)

This project demonstrates ability to:

Build end-to-end apps (React/Next.js + FastAPI).
Integrate LLM workflows into a real UX.
Operate cloud deployments with CI/CD.
Ship a usable demo (not just a notebook).

Recruiters: check the live demo

❓ FAQ
Why Gemini 1.5 Flash?
Fast, cost-effective, good for short-turn Q&A and structured feedback via prompts.

Why pgvector?
To ground follow-ups with relevant context and enable semantic search over prior answers/prompt snippets.

Can I run without Supabase?
Yes, swap for standard Postgres (install pgvector extension) and adjust DATABASE_URL.

🧩 Troubleshooting

CORS errors: Ensure CORS_ORIGINS includes your dev/prod domains.
DB connection fails: Verify DATABASE_URL and that the pgvector extension is installed.
LLM 401/403: Check LITELLM_API_KEY and provider limits.
Render deploy issues: Confirm health check path /.

🤝 Contributing

PRs welcome! Please open an issue for major changes.
Run lint/test before submitting.

📜 License

MIT

🙌 Acknowledgements

LiteLLM team and open-source community
Supabase for developer-friendly Postgres + pgvector
Vercel & Render for generous free tiers
