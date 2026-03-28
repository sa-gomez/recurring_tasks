import os
from datetime import date, timedelta
from functools import wraps
from dotenv import load_dotenv
from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from authlib.integrations.flask_client import OAuth
import psycopg2
import psycopg2.extras

load_dotenv()

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# Some platforms (Heroku, Railway) provide postgres:// URLs; psycopg2 needs postgresql://
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)
DATABASE_URL = _db_url

# Spaced repetition intervals in days.
# Each completion advances to the next index; past the last, the interval doubles.
INTERVALS = [1, 3, 7, 14, 30, 90, 180, 365]

ALLOWED_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("ALLOWED_EMAILS", "").split(",")
    if e.strip()
}

# ---------------------------------------------------------------------------
# Google OAuth
# ---------------------------------------------------------------------------

oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def api_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "not authenticated"}), 401
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Interval helpers
# ---------------------------------------------------------------------------

def next_interval(interval_index: int) -> int:
    if interval_index < len(INTERVALS):
        return INTERVALS[interval_index]
    doublings = interval_index - len(INTERVALS)
    return INTERVALS[-1] * (2 ** (doublings + 1))


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = psycopg2.connect(DATABASE_URL)
    return g.db


def query(sql, params=(), one=False, returning=False):
    """Execute a query and return results as dicts."""
    db = get_db()
    with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        if returning:
            result = cur.fetchone()
            db.commit()
            return result
        if cur.description:
            rows = cur.fetchall()
            return (rows[0] if rows else None) if one else rows
        db.commit()
        return cur.rowcount


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         SERIAL PRIMARY KEY,
            google_id  TEXT UNIQUE NOT NULL,
            email      TEXT NOT NULL,
            name       TEXT,
            picture    TEXT,
            created_at DATE NOT NULL DEFAULT CURRENT_DATE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id             SERIAL PRIMARY KEY,
            user_id        INTEGER REFERENCES users(id),
            name           TEXT NOT NULL,
            description    TEXT,
            created_at     DATE NOT NULL DEFAULT CURRENT_DATE,
            interval_index INTEGER NOT NULL DEFAULT 0,
            next_due_date  DATE NOT NULL,
            is_active      INTEGER NOT NULL DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS completions (
            id            SERIAL PRIMARY KEY,
            task_id       INTEGER NOT NULL REFERENCES tasks(id),
            completed_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            interval_days INTEGER NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def get_or_create_user(google_id, email, name, picture):
    row = query("SELECT id FROM users WHERE google_id = %s", (google_id,), one=True)
    if row:
        query(
            "UPDATE users SET email=%s, name=%s, picture=%s WHERE google_id=%s",
            (email, name, picture, google_id),
        )
        return row["id"]
    row = query(
        "INSERT INTO users (google_id, email, name, picture) VALUES (%s, %s, %s, %s) RETURNING id",
        (google_id, email, name, picture),
        returning=True,
    )
    return row["id"]


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.get("/login")
def login_page():
    if "user_id" in session:
        return redirect("/")
    return render_template("login.html")


@app.get("/auth/google")
def auth_google():
    redirect_uri = url_for("auth_google_callback", _external=True)
    return google.authorize_redirect(redirect_uri)


@app.get("/auth/google/callback")
def auth_google_callback():
    token = google.authorize_access_token()
    userinfo = token.get("userinfo") or google.userinfo()

    if ALLOWED_EMAILS and userinfo["email"].lower() not in ALLOWED_EMAILS:
        return render_template("denied.html", email=userinfo["email"]), 403

    user_id = get_or_create_user(
        google_id=userinfo["sub"],
        email=userinfo["email"],
        name=userinfo.get("name", ""),
        picture=userinfo.get("picture", ""),
    )
    session["user_id"] = user_id
    session["user_name"] = userinfo.get("name", userinfo["email"])
    session["user_picture"] = userinfo.get("picture", "")
    return redirect("/")


@app.get("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------------------------------------------------------------------
# App routes
# ---------------------------------------------------------------------------

@app.get("/")
@login_required
def index():
    return render_template(
        "index.html",
        user_name=session.get("user_name"),
        user_picture=session.get("user_picture"),
    )


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/api/tasks")
@api_login_required
def list_tasks():
    today = date.today().isoformat()
    rows = query(
        "SELECT id, name, description, created_at::text, interval_index, next_due_date::text "
        "FROM tasks WHERE is_active = 1 AND user_id = %s ORDER BY next_due_date ASC",
        (session["user_id"],),
    )
    tasks = []
    for r in rows:
        idx = r["interval_index"]
        tasks.append({
            "id": r["id"],
            "name": r["name"],
            "description": r["description"],
            "created_at": r["created_at"],
            "interval_index": idx,
            "next_due_date": r["next_due_date"],
            "is_overdue": r["next_due_date"] < today,
            "is_due_today": r["next_due_date"] == today,
            "current_interval_days": next_interval(idx),
            "next_interval_days": next_interval(idx + 1),
        })
    return jsonify(tasks)


@app.post("/api/tasks")
@api_login_required
def create_task():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    description = (data.get("description") or "").strip()
    start_date = data.get("start_date") or date.today().isoformat()

    row = query(
        "INSERT INTO tasks (user_id, name, description, next_due_date) "
        "VALUES (%s, %s, %s, %s) RETURNING id, name, description, created_at::text, interval_index, next_due_date::text",
        (session["user_id"], name, description, start_date),
        returning=True,
    )
    today = date.today().isoformat()
    return jsonify({
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "created_at": row["created_at"],
        "interval_index": row["interval_index"],
        "next_due_date": row["next_due_date"],
        "is_overdue": row["next_due_date"] < today,
        "is_due_today": row["next_due_date"] == today,
        "current_interval_days": next_interval(0),
        "next_interval_days": next_interval(1),
    }), 201


@app.post("/api/tasks/<int:task_id>/complete")
@api_login_required
def complete_task(task_id):
    row = query(
        "SELECT interval_index FROM tasks WHERE id = %s AND is_active = 1 AND user_id = %s",
        (task_id, session["user_id"]),
        one=True,
    )
    if not row:
        return jsonify({"error": "task not found"}), 404

    new_index = row["interval_index"] + 1
    days = next_interval(new_index)
    new_due = (date.today() + timedelta(days=days)).isoformat()

    query(
        "INSERT INTO completions (task_id, interval_days) VALUES (%s, %s)",
        (task_id, next_interval(row["interval_index"])),
    )
    query(
        "UPDATE tasks SET interval_index = %s, next_due_date = %s WHERE id = %s",
        (new_index, new_due, task_id),
    )
    return jsonify({
        "id": task_id,
        "interval_index": new_index,
        "next_due_date": new_due,
        "next_interval_days": next_interval(new_index + 1),
    })


@app.delete("/api/tasks/<int:task_id>")
@api_login_required
def delete_task(task_id):
    rowcount = query(
        "UPDATE tasks SET is_active = 0 WHERE id = %s AND is_active = 1 AND user_id = %s",
        (task_id, session["user_id"]),
    )
    if rowcount == 0:
        return jsonify({"error": "task not found"}), 404
    return "", 204


@app.get("/api/tasks/<int:task_id>/history")
@api_login_required
def task_history(task_id):
    row = query(
        "SELECT id FROM tasks WHERE id = %s AND user_id = %s",
        (task_id, session["user_id"]),
        one=True,
    )
    if not row:
        return jsonify({"error": "task not found"}), 404

    rows = query(
        "SELECT completed_at::text, interval_days FROM completions "
        "WHERE task_id = %s ORDER BY completed_at DESC",
        (task_id,),
    )
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
