# Backend

FastAPI service for Inbox Sense. Run commands from this directory; it is a standalone deployment root and does not require the frontend source to start.

## Local Development

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Configure a PostgreSQL connection using `DATABASE_URL` or the `DB_*` fields in `.env`. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `FRONTEND_URL`, and a unique `SECRET_KEY`. `GEMINI_API_KEY` is optional. Use `http://localhost:5173` for local `FRONTEND_URL` and register the redirect URI with the Google OAuth client.

## Tests

Run the backend test suite from this directory with `python -m pytest` after installing pytest in the environment.

## Deployment

Set this folder as the deployment root, install dependencies from `requirements.txt`, configure the required environment variables in the platform, and start the service with:

```text
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Keep backend environment values in `backend/.env` locally. Never commit `.env` files or OAuth credentials.