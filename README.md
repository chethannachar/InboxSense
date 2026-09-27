# Inbox Sense

Inbox Sense is a full-stack application split into independently runnable and deployable frontend and backend projects.

## Repository Structure

- `frontend/`: React and Vite application. This is the frontend deployment root.
- `backend/`: FastAPI application, database integration, and tests. This is the backend deployment root.

Each project has its own dependencies, environment file, and README. Neither deployment requires the other project to be present in its build root.

## Run Locally

Start the backend in one terminal:

```powershell
cd backend
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Configure the database, Google OAuth, `FRONTEND_URL`, and `SECRET_KEY` in `backend/.env` before starting.

Start the frontend in another terminal:

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Set `VITE_API_URL` in `frontend/.env` to the backend API origin. See [frontend/README.md](frontend/README.md) and [backend/README.md](backend/README.md) for independent setup and deployment details.

## Environment and Secrets

Keep backend settings in `backend/.env` and frontend settings in `frontend/.env`. The `.env.example` files contain placeholders; replace them locally or configure deployment environment variables. Real `.env` files, OAuth client credentials, and other secrets must never be committed.
