# Role-based project API

The API uses HTTP-only cookies: a short-lived access token and a rotating refresh
token. The browser must send requests with credentials enabled.

## Required environment

Create `Backend/.env` (do not commit it):

```env
database_hostname=localhost
database_name=role_based
database_username=postgres
database_password=change-me
database_port=5432
secret_key=use-a-long-random-secret
algorithm=HS256
access_token_expire_minutes=15
refresh_token_expire_days=30
cookie_secure=false
allowed_origins=http://localhost:5173
```

For tests, `database_url=sqlite+pysqlite:///./test.db` may be used instead of the
individual PostgreSQL connection values. In production, set `cookie_secure=true`
and serve both apps over HTTPS.

Install the declared dependencies, then run from the repository root:

```bash
Backend/venv/bin/pip install -r Backend/requirement.txt
cd Backend && ./venv/bin/uvicorn raw.main:app --reload
```

## Frontend integration

Use `credentials: "include"` for every API request. On application startup, call
`POST /auth/refresh`. When an API request returns 401, call it once and retry the
original request; if the refresh also returns 401, send the user to sign-in. This
keeps tokens out of JavaScript and refreshes sessions before users notice expiry.

```ts
export async function api(path: string, init: RequestInit = {}) {
  const send = () => fetch(`${API_URL}${path}`, { ...init, credentials: "include" });
  let response = await send();
  if (response.status === 401 && path !== "/auth/refresh") {
    const refreshed = await fetch(`${API_URL}/auth/refresh`, { method: "POST", credentials: "include" });
    if (refreshed.ok) response = await send();
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message ?? "Something went wrong. Please try again.");
  }
  return response.status === 204 ? null : response.json();
}
```

Use one toast provider at the app root and catch errors from this wrapper there
(or in your data-fetching library's global error callback). API errors always have
the form `{ "error": { "message", "request_id?", "details?" } }`; show the
friendly `message` and include `request_id` in a support report for 500 errors.

Open one socket after a successful refresh:

```ts
const socket = new WebSocket(`${WS_URL}/ws`);
socket.onmessage = ({ data }) => {
  const event = JSON.parse(data);
  if (event.type === "notification.created") toast(event.data.title);
  if (event.type === "project.event") queryClient.invalidateQueries({ queryKey: ["project", event.data.project_id] });
};
```

The API also exposes `GET /projects/{project_id}/events?after_id=...` so the UI
can catch up after a disconnected socket reconnects. Use role values from
`GET /users/me` and project membership endpoints only to hide unavailable UI;
the backend remains the security boundary and enforces Admin, Project Lead, and
Member permissions on every protected endpoint.
