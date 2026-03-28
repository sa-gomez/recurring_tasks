import sqlite3
import os
from datetime import date, timedelta
from flask import Flask, g, jsonify, render_template, request

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "tasks.db")

# Spaced repetition intervals in days.
# Each completion advances to the next index; past the last, the interval doubles.
INTERVALS = [1, 3, 7, 14, 30, 90, 180, 365]


def next_interval(interval_index: int) -> int:
    """Return the number of days until next recurrence given current index."""
    if interval_index < len(INTERVALS):
        return INTERVALS[interval_index]
    # Past the defined schedule: double the last interval each time
    doublings = interval_index - len(INTERVALS)
    return INTERVALS[-1] * (2 ** (doublings + 1))


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            description     TEXT,
            created_at      TEXT NOT NULL DEFAULT (date('now')),
            interval_index  INTEGER NOT NULL DEFAULT 0,
            next_due_date   TEXT NOT NULL,
            is_active       INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS completions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id      INTEGER NOT NULL REFERENCES tasks(id),
            completed_at TEXT NOT NULL DEFAULT (datetime('now')),
            interval_days INTEGER NOT NULL
        );
    """)
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/tasks")
def list_tasks():
    db = get_db()
    today = date.today().isoformat()
    rows = db.execute(
        "SELECT id, name, description, created_at, interval_index, next_due_date "
        "FROM tasks WHERE is_active = 1 ORDER BY next_due_date ASC"
    ).fetchall()

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
def create_task():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    description = (data.get("description") or "").strip()
    start_date = data.get("start_date") or date.today().isoformat()

    db = get_db()
    cursor = db.execute(
        "INSERT INTO tasks (name, description, next_due_date) VALUES (?, ?, ?)",
        (name, description, start_date),
    )
    db.commit()
    task_id = cursor.lastrowid

    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return jsonify({
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "created_at": row["created_at"],
        "interval_index": row["interval_index"],
        "next_due_date": row["next_due_date"],
        "current_interval_days": next_interval(0),
        "next_interval_days": next_interval(1),
    }), 201


@app.post("/api/tasks/<int:task_id>/complete")
def complete_task(task_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM tasks WHERE id = ? AND is_active = 1", (task_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "task not found"}), 404

    new_index = row["interval_index"] + 1
    days = next_interval(new_index)
    new_due = (date.today() + timedelta(days=days)).isoformat()

    db.execute(
        "INSERT INTO completions (task_id, interval_days) VALUES (?, ?)",
        (task_id, next_interval(row["interval_index"])),
    )
    db.execute(
        "UPDATE tasks SET interval_index = ?, next_due_date = ? WHERE id = ?",
        (new_index, new_due, task_id),
    )
    db.commit()

    return jsonify({
        "id": task_id,
        "interval_index": new_index,
        "next_due_date": new_due,
        "next_interval_days": next_interval(new_index + 1),
    })


@app.delete("/api/tasks/<int:task_id>")
def delete_task(task_id):
    db = get_db()
    result = db.execute(
        "UPDATE tasks SET is_active = 0 WHERE id = ? AND is_active = 1", (task_id,)
    )
    db.commit()
    if result.rowcount == 0:
        return jsonify({"error": "task not found"}), 404
    return "", 204


@app.get("/api/tasks/<int:task_id>/history")
def task_history(task_id):
    db = get_db()
    rows = db.execute(
        "SELECT completed_at, interval_days FROM completions WHERE task_id = ? ORDER BY completed_at DESC",
        (task_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
