# deployment.md

Repo: https://github.com/Nitheeshhd/realestate-lead-assistant · Live app: https://realestate-lead-assistant.vercel.app/
Backend API: https://realestate-lead-assistant.onrender.com

## Run locally

Needs Python 3.11+ and Node 18+.

Run the backend, frontend, and tests in separate terminals opened at the repository root.

```bash
# Backend terminal
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # optional: DJANGO_DEBUG=1 is enough locally
export DJANGO_DEBUG=1         # local only; enables the dev secret key and SQLite
python manage.py migrate
python manage.py seed         # demo staff, 2 projects, fact sheet, slots, ~60 leads, visits, spend
python manage.py runserver    # http://127.0.0.1:8000

# Frontend terminal
cd frontend
npm install
npm run dev                   # http://localhost:5173 (proxies /api to :8000)

# Test terminal
cd backend
DJANGO_DEBUG=1 python manage.py test                    # 44 tests
```

### Windows PowerShell

```powershell
# Backend
Set-Location .\backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:DJANGO_DEBUG = "1"
python manage.py migrate
python manage.py seed
python manage.py runserver

# Frontend (open a second PowerShell at the repo root)
Set-Location .\frontend
npm install
npm run dev

# Tests (third terminal at the repo root)
Set-Location .\backend
$env:DJANGO_DEBUG = "1"
python manage.py test

# Production frontend bundle (fourth terminal at repo root)
Set-Location .\frontend
npm run build
```

Without `ANTHROPIC_API_KEY` the chat uses the built-in rule agent (same tools, same guardrails),
so everything works offline. Add the key to switch to the Claude tool-use agent.

## Render and Vercel deployment

The app is deployed at the URLs above. The Render API is responding, but the live Vercel app currently cannot
load projects because the Render CORS allowlist does not include the Vercel origin. In the Render web service's
Environment tab, set both `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` to
`https://realestate-lead-assistant.vercel.app`, then redeploy. Verify that
`https://realestate-lead-assistant.onrender.com/api/public/projects` returns JSON and that the Vercel home page
loads the project selector without an error. The Render API root (`/`) is not a frontend page.

Use a persistent PostgreSQL database for Render; SQLite is for local development only.

### Render backend

1. The source repository is https://github.com/Nitheeshhd/realestate-lead-assistant.
2. In Render, choose **New + → PostgreSQL**. Create a database in the same region as the web service.
3. Choose **New + → Web Service**, connect the repository, and set:
   - Root Directory: `backend`
   - Runtime: `Python 3`
   - Build Command: `bash build.sh`
   - Start Command: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`
4. In the service's **Environment** tab, add these names. Keep secret values only in Render:
   - `DJANGO_DEBUG` = `0`
   - `DJANGO_SECRET_KEY` = generate a unique value locally with `python -c "import secrets; print(secrets.token_urlsafe(50))"` and paste it directly into Render.
   - `DJANGO_ALLOWED_HOSTS` = the Render hostname, e.g. `your-service.onrender.com` (host only; no scheme).
   - `DATABASE_URL` = the PostgreSQL **Internal Database URL** from the database's **Connect** panel; use Render's linked database variable if offered.
   - `SEED_PASSWORD` = `demo-pass-123` for the fake live-demo accounts (change it if you want a private demo).
   - `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` = the exact HTTPS Vercel production origin, e.g. `https://your-project.vercel.app` (comma-separated if using more than one origin).
   - `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` = optional; leave the key unset to use the offline rule agent.
5. Deploy. The build script installs requirements, collects static files, applies migrations, and seeds sample data. Confirm the service is **Live** before creating the frontend.
6. If the Vercel production origin changes, update both origin variables in Render and redeploy.

### Vercel frontend

1. In Vercel choose **Add New → Project**, import the same GitHub repository, and set Root Directory to `frontend`.
2. Set Framework Preset to **Vite**, Build Command to `npm run build`, and Output Directory to `dist`.
3. Add `VITE_API_URL` with the Render backend origin, e.g. `https://your-service.onrender.com` (no trailing slash or `/api`).
4. Deploy and open the production URL. `frontend/vercel.json` rewrites client routes to `index.html`; `VITE_API_URL` is used at build time.
5. Set the exact production Vercel origin in Render's CORS and CSRF environment variables, then verify the buyer chat and staff login.

**Reminder delivery is mocked.** The sales-head button stores/logs due reminders; no SMS or WhatsApp messages are sent. The reminder endpoint is `POST /api/reminders/run` (staff token required).

## API endpoints

All API paths are under `/api/`. Staff endpoints require a token; executives only see their assigned leads, and sales-head-only endpoints enforce that role.

| Area | Endpoints |
|---|---|
| Auth and project list | `POST /auth/login`, `GET /auth/me`, `GET /public/projects` |
| Buyer chat | `POST /chat/start`, `POST /chat/{lead_id}/message`, `POST /chat/{lead_id}/opt-out` |
| Leads and visits | `GET/POST /leads`, `POST /leads/import`, `GET /leads/{id}`, `POST /visits/{id}/status` |
| Handoffs | `GET /handoffs`, `GET /handoffs?review=1`, `POST /handoffs/{id}/{ack|review}` |
| Dashboard | `GET /dashboard?from=YYYY-MM-DD&to=YYYY-MM-DD&project={id}` |
| Admin editors | `GET/POST /facts`, `DELETE /facts/{id}`, `GET/POST /slots`, `PATCH/DELETE /slots/{id}`, `GET /executives` |
| Reminders | `GET /reminders`, `POST /reminders/run` |

## Environment variables (names only)

Backend: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL`,
`CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `SEED_PASSWORD`

Frontend: `VITE_API_URL`

## Demo logins (seeded, fake accounts)

| Role | Username | Password |
|---|---|---|
| Sales head | `saleshead` | value of `SEED_PASSWORD` (`demo-pass-123` locally) |
| Executive, Project 1 | `rahul`, `pooja` | same |
| Executive, Project 2 | `karan`, `anita` | same |

Buyer chat needs no login: open `/`, tick consent, start. Try: "When is possession?", "Any discount?",
"Is there a gym?", "I want to book a site visit", "I want to talk to a person", or write in Hindi or Gujarati.

## Build the two-file submission ZIP

After replacing the GitHub and live-app placeholders in `TDD.md` and `deployment.md`, run this at the repository root in PowerShell:

```powershell
python tools\build_submission.py
```

The script uses installed Microsoft Edge or Chromium to render `TDD.md` (including the screenshots) to `TDD.pdf`,
then creates `submission.zip` containing exactly `TDD.pdf` and `deployment.md`. The ZIP must be under 25 MB.
Inspect the PDF and ZIP before uploading. The browser executable can be selected with `BROWSER_BIN` if it is not on PATH.
