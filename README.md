# AI Interview Trainer (PoC)

- Backend: FastAPI + Supabase (pgvector)
- LLM: LiteLLM → Gemini (gemini-1.5-flash-latest)
- RAG: `sources.embedding` (vector) + `<=>` cosine
- Endpoints: `/session/start`, `/session/answer`
- Status: **Step 10 done** (RAG inlined i `/session/answer`)

## Run (dev)
```bash
uvicorn main:app --reload
