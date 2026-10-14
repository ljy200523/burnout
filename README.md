# Student Wellbeing API

Python backend and browser frontend MVP for student workload and well-being tracking. It provides an OpenAI-powered supportive chatbot, daily well-being logs, normalized calendar event import, and daily workload summaries.

## Run locally

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and set OPENAI_API_KEY before using chat.
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/` for the frontend or `http://127.0.0.1:8000/docs` for interactive API documentation. SQLite data is stored in `burnout.db` by default.

## Main endpoints

- `POST /api/v1/students`, `GET /api/v1/students/{id}`, `PATCH /api/v1/students/{id}`
- `PUT /api/v1/students/{id}/wellbeing` (one upsertable entry per day)
- `GET /api/v1/students/{id}/wellbeing?start=YYYY-MM-DD&end=YYYY-MM-DD`
- `POST /api/v1/students/{id}/calendar/events`, `GET .../calendar/events`
- `POST /api/v1/students/{id}/calendar/sync` with normalized Google/Apple events
- `GET /api/v1/students/{id}/calendar/workload?start=YYYY-MM-DD&days=7`
- `POST /api/v1/students/{id}/chat`, `GET .../chat/history`

## MVP boundaries

Calendar sync currently accepts normalized events. Production Google Calendar and Apple Calendar connections require provider OAuth/authorization, credential storage, token refresh, and provider-specific fetching; those credentials are intentionally not collected by this API. Chat uses OpenAI's Responses API; configure `OPENAI_API_KEY` and optionally `OPENAI_MODEL` in `.env`. The key is only read by the backend. This is a prototype data model: add authentication and authorization before storing real student data, and avoid treating the chatbot as clinical or emergency care.
