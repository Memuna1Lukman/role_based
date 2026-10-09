# Flowboard React frontend

## Start

```bash
cd Frontend
npm install
npm run dev
```

Vite serves the app at `http://localhost:5173`. Set `allowed_origins=http://localhost:5173` in `Backend/.env` and run the FastAPI API on port 8000.

Copy `.env.example` to `.env` when the API is hosted elsewhere.

## Backend integration

- HTTP-only access and refresh cookies; requests always use `credentials: "include"`.
- Refreshes once after a 401, then returns the user to login if the session cannot be refreshed.
- Gets the authenticated user from `GET /users/me`.
- Fetches projects, project members/tasks, and notifications from the FastAPI routes.
- Opens `/ws` for real-time project changes and notification toasts.
- Uses global role and current-project membership only to guide the UI; the backend remains the permission authority.
