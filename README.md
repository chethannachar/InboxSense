# Inbox Sense

## Frontend

```powershell
cd Frontend
Copy-Item .env.example .env
npm install
npm run dev
npm run build
```

Set `VITE_API_URL` in `Frontend/.env`. For Vercel, set Root Directory to `Frontend`, build with `npm run build`, and provide `VITE_API_URL` in project settings.

## Backend

```powershell
cd Backend
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

Set database, Google OAuth, `FRONTEND_URL`, and `SECRET_KEY` values in `Backend/.env`; set `GEMINI_API_KEY` only if Gemini classification is required. Never commit `.env` files or secrets. For AWS, deploy from `Backend/`, configure the required environment variables, and run the same Uvicorn command without `--reload`.
