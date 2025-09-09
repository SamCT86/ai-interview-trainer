# AI Interview Trainer (MVP)

An AI-powered mock interview trainer built with **FastAPI**, **Supabase (pgvector)** and **Next.js**.  
Practice interviews, answer AI-generated questions, and receive instant structured feedback.

---

## 🚀 Live Demo
- **Frontend (Vercel):** https://ai-interview-trainer-frontend-f1gt19unm.vercel.app
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
- **Backend:** FastAPI, SQLAlchemy, Supabase (Postgres + pgvector), psycopg v3  
- **LLM:** Gemini 1.5 Flash (via LiteLLM)  
- **Frontend:** Next.js (Vercel), TailwindCSS  
- **Hosting:** Backend on Render, Frontend on Vercel  
- **CORS:** localhost + `https://*.vercel.app`

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

🧪 Testing

Basic backend tests with pytest (session creation, DB connection).
Integration tests planned for /session/answer flow.

🔄 CI/CD

GitHub Actions for linting & tests on each commit.
Vercel auto-deploy (frontend).
Render auto-deploy (backend).


📊 Metrics & Logs

Supabase query logs enabled
Vercel analytics for frontend traffic
Render logs for API monitoring

📜 License

MIT License
