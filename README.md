# AI Interview Trainer (MVP)

An AI-powered mock interview trainer built with **FastAPI**, **Supabase (pgvector)** and **Next.js**.  
Practice interviews, answer AI-generated questions, and receive instant structured feedback.

---

## 🚀 Live Demo
- **Frontend (Vercel):** https://ai-interview-trainer-front-git-0af047-sarmads-projects-f3142150.vercel.app/
- **Backend (Render – API Docs):** https://ai-interview-trainer-api.onrender.com/docs

---

## ✨ Features
- Role-based sessions (Junior Developer, Project Manager).
- AI-generated interview questions (Gemini 1.5 Flash via LiteLLM).
- Answer submission with structured feedback and next question.
- Vector search using Supabase pgvector.
- Dark mode UI with smooth animations.

---

## 🛠️ Tech Stack
- **Backend:** FastAPI, SQLAlchemy, Supabase (Postgres + pgvector)  
- **LLM:** Gemini 1.5 Flash (via LiteLLM)  
- **Frontend:** Next.js (Vercel), TailwindCSS  
- **Hosting:** Backend on Render, Frontend on Vercel  

---

## 🔌 API Endpoints
- `GET /` → health check  
- `POST /session/start` → start a new interview session  
- `POST /session/answer` → submit answer and get feedback  
- `GET /db-test` → verify DB connection  

---

## 📦 Local Setup

### Backend
```bash
cd apps/backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
