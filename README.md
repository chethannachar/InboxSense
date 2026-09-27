# Gmail Attention Dashboard

This project currently contains a simple React + Vite landing page and a minimal FastAPI backend foundation for the Gmail attention dashboard.

## Frontend

From the project root:

```powershell
cd "c:\Users\cheth\Email"
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Frontend URL after startup:

- http://localhost:5173/

## Backend

Use Python 3.12 for the backend environment.

```powershell
cd "c:\Users\cheth\Email\backend"
& "C:\Users\cheth\AppData\Local\Programs\Python\Python312\python.exe" -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend URL after startup:

- http://localhost:8000/

Health check:

- http://localhost:8000/api/health

## Database

Create the PostgreSQL database first if needed, then run:

```bash
psql -h localhost -U postgres -d gmail_attention -f backend/sql/schema.sql
```

This project intentionally does not include Google OAuth, Gmail API, Gemini, AI classification, or email synchronization yet.
