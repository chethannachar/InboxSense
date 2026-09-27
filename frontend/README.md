# Frontend

React and Vite client for Inbox Sense. This folder is a standalone deployment root and does not require the backend source to build.

## Local Development

```powershell
Copy-Item .env.example .env
npm install
npm run dev
```

Set `VITE_API_URL` in `.env` to the backend API origin, such as `http://localhost:8000`. The client requires this value when it starts.

## Build and Deploy

```powershell
npm run build
npm run preview
```

Deploy with this folder as the project root, run `npm run build`, and publish the generated `dist/` directory. Configure `VITE_API_URL` in the deployment environment to point to the separately deployed backend.