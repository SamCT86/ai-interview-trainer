# AI Interview Trainer (MVP)

An **AI-powered mock interview trainer** built with **FastAPI**, **Supabase (pgvector)** and **Next.js**.  
Practice interviews, answer AI-generated questions, and receive instant structured feedback.

---

## 🚀 Live Demo
- **Frontend (Vercel):** [ai-interview-trainer-frontend](https://ai-interview-trainer-frontend-f1gt19unm.vercel.app)  
- **Backend (Render – API Docs):** [ai-interview-trainer-api](https://ai-interview-trainer-api.onrender.com/docs)

---

## ✨ Features
- 🎭 Role-based sessions (Junior Developer, Project Manager).  
- 🤖 AI-generated interview questions (Gemini 1.5 Flash via LiteLLM).  
- 📝 Answer submission with structured feedback and next question.  
- 🔎 Vector search using Supabase **pgvector**.  
- 🌙 Dark mode UI with smooth animations.  

---

## 🖼️ Screenshots
*(lägg till egna bilder i `docs/`-mappen och byt ut filnamnen nedan)*

![UI Example](docs/screenshot-ui.png)  
![API Docs](docs/screenshot-api.png)

---

## 🛠️ Tech Stack
- **Backend:** FastAPI, SQLAlchemy, Supabase (Postgres + pgvector), psycopg v3  
- **AI/LLM:** Gemini 1.5 Flash via LiteLLM  
- **Frontend:** Next.js (App Router), TailwindCSS  
- **Infra:** Render (API), Vercel (Frontend), GitHub Actions (CI/CD)  
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
.\venv\Scripts\activate   # (Windows)
source venv/bin/activate  # (Mac/Linux)
pip install -r requirements.txt
uvicorn main:app --reload
Frontend
bash
Kopiera kod
cd apps/frontend
npm install
npm run dev
🧪 Testing
Basic backend tests with pytest (session creation, DB connection).

Integration tests planned for /session/answer flow.

🔄 CI/CD
GitHub Actions for linting & tests on each commit.

Vercel auto-deploy (frontend).

Render auto-deploy (backend).

📊 Metrics & Logs
Supabase query logs enabled.

Vercel analytics for frontend traffic.

Render logs for API monitoring.

📜 License
MIT License
