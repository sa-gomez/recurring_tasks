# Recurring Tasks

A spaced repetition task scheduler. Add tasks once and let the app figure out when to resurface them — intervals grow automatically each time you mark something complete, so high-priority items fade into the background once you've truly learned or handled them.

![Recurring Tasks UI](static/screenshot.png)

## How it works

Each task has an interval that advances on every completion:

| Completion | Interval |
|-----------|----------|
| 1st | 1 day |
| 2nd | 3 days |
| 3rd | 7 days |
| 4th | 14 days |
| 5th | 30 days |
| 6th | 90 days |
| 7th | 180 days |
| 8th | 365 days |
| 9th+ | doubles each time |

## Setup

**Prerequisites:** Python 3, PostgreSQL (e.g. `brew install postgresql@17`)

```bash
# Install dependencies
pip3 install -r requirements.txt

# Create the local database
createdb recurring_tasks

# Configure environment
cp .env.example .env
# Fill in SECRET_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, ALLOWED_EMAILS
# DATABASE_URL defaults to postgresql://localhost/recurring_tasks
```

**Google OAuth:** Create OAuth 2.0 credentials at [console.cloud.google.com](https://console.cloud.google.com) and add `http://localhost:5000/auth/google/callback` as an authorized redirect URI.

```bash
# Run the development server
python3 app.py
```

Or with gunicorn:
```bash
gunicorn -b 127.0.0.1:5000 app:app
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000).

## Deploying

The app is configured for [Railway](https://railway.app). Push to GitHub, connect the repo in Railway, add a Postgres database, and set the environment variables from `.env` in the Railway dashboard (`DATABASE_URL` is injected automatically when you link the database).

## Features

- **Due / Upcoming / All Tasks** tabs
- Overdue tasks highlighted in red, due-today in green
- Badges show current interval and what the next interval will be after completion
- Completion history per task
