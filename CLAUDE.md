# Recurring Tasks — Project Context

## What this is
A spaced repetition task scheduler. Users add tasks and mark them complete; each completion reschedules the task at a longer interval (1, 3, 7, 14, 30, 90, 180, 365 days, then doubling).

## Stack
- **Backend:** Python/Flask
- **Database:** PostgreSQL (psycopg2), local via Homebrew postgresql@17
- **Auth:** Google OAuth via Authlib
- **Server:** gunicorn (use `--worker-class=gthread` on macOS to avoid fork issues)
- **Hosting:** Railway (in progress)
- **Frontend:** Vanilla JS, no build step

## Running locally
```bash
python3 app.py          # Flask dev server, port 5000
gunicorn --worker-class=gthread -b 127.0.0.1:5000 app:app  # gunicorn (macOS)
```

## Key files
- `app.py` — everything: config, DB, auth, routes (candidate for future split into app.py + db.py)
- `templates/index.html` + `static/app.js` + `static/style.css` — frontend
- `.env` — local environment variables (gitignored)
- `Procfile` — tells Railway to use gunicorn

## Environment variables
| Var | Notes |
|-----|-------|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | Flask session signing key |
| `GOOGLE_CLIENT_ID` | From Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | From Google Cloud Console |
| `ALLOWED_EMAILS` | Comma-separated allowlist |

## Railway deployment status (as of late March 2026)
- App service and Postgres service are created and in the same group
- `DATABASE_URL` is not being injected correctly — health endpoint at `/health` shows `DATABASE_URL: false`
- Purple variables (variable references) are not showing up in deployment details, only white (plain text) variables are
- Tried: variable reference via dropdown, plain text copy-paste of connection string — neither worked
- Next thing to try: ensure services are properly linked in Railway canvas (no connecting line between them currently)
- Google OAuth redirect URI for prod needs to be added to Google Cloud Console once Railway URL is confirmed

## Architecture decisions
- SQLite → PostgreSQL migration already done
- Tasks are scoped per user (user_id foreign key on tasks table)
- `init_db()` runs at startup under gunicorn (module level), creates tables if not exist
- Google OAuth blocks in-app browsers (e.g. iPhone Messages app) — users must open in Safari/Chrome
- No plans for ORM — raw SQL via psycopg2 is fine for this scale

## Planned refactor (not yet done)
Split `app.py` into:
- `app.py` — routes only
- `db.py` — all SQL queries
