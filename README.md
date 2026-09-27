# Inbox Sense

Inbox Sense is organized as one repository with independently deployable React/Vite and FastAPI applications.

## Repository Structure

```text
frontend/  React/Vite application; deploy from this directory to Vercel
backend/   FastAPI, Gmail/OAuth integrations, database access; deploy to AWS
```

The frontend talks to the backend using `VITE_API_URL`; it does not rely on a same-origin API or backend files on disk.

## Requirements

- Node.js 22 or newer
- Python 3.12
- PostgreSQL

## Local Environment

Copy `frontend/.env.example` to `frontend/.env`. Copy `backend/.env.example` to `backend/.env` if one does not already exist. Never replace an existing local `.env` containing credentials. Keep all actual secrets in ignored `.env` files or deployment environment settings.

Generate a unique backend `SECRET_KEY` for local use, for example:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Configure Google OAuth with the local redirect URI from `backend/.env.example` and allow the Gmail scopes requested by the application. Create the PostgreSQL database, then initialize its schema from the repository root:

```powershell
psql -h localhost -U postgres -d gmail_attention -f backend/sql/schema.sql
```

## Run Frontend

```powershell
cd frontend
npm install
npm run dev
```

Vite runs at `http://localhost:5173` by default. `frontend/.env` sets `VITE_API_URL=http://localhost:8000` for local development.

Build with:

```powershell
npm run build
```

## Run Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --no-access-log
```

The API health endpoint is `http://localhost:8000/api/health`. The same `uvicorn app.main:app --host 0.0.0.0 --port 8000` command is suitable for a production process; omit `--reload` in deployment.

Run backend tests from `backend/` with `python -m pytest tests` after installing `pytest` in the environment.

## Environment Variables

`frontend/.env.example` documents `VITE_API_URL`. Set it to the backend origin locally and to the AWS API origin in Vercel; do not include an application route suffix.

`backend/.env.example` documents the existing database, Google OAuth, Gemini, session-cookie, and worker settings. Important deployment values are:

- `DATABASE_URL` or the `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` fields
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI`
- `FRONTEND_URL`, used both for CORS and OAuth callback redirects
- `SECRET_KEY`, used to encrypt stored OAuth tokens and session cookies
- `SESSION_COOKIE_SAMESITE=none` and `SESSION_COOKIE_SECURE=true` when the Vercel frontend and AWS backend are on different sites; local defaults are `lax` and `false`
- `GEMINI_API_KEY` if Gemini-backed classification is enabled

Use separate local and production values. Do not commit `.env` files or place secrets in frontend variables.

## Deployment

### Vercel

Set the Vercel Root Directory to `frontend`, use `npm run build`, and set `VITE_API_URL` to the deployed AWS backend origin.

### AWS

Deploy `backend/` as the application source. Install `requirements.txt`, provide the backend environment variables, and run:

```text
uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

Set `FRONTEND_URL` to the deployed Vercel origin, configure the matching Google OAuth callback URI in Google Cloud, and use `SESSION_COOKIE_SAMESITE=none` with `SESSION_COOKIE_SECURE=true` for cross-site browser sessions. CORS always allows `http://localhost:5173` for local development and adds the configured `FRONTEND_URL`; it does not allow wildcard origins.
