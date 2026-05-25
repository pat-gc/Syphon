import sqlite3
from pathlib import Path
import os
import re

DB_PATH = Path("data/downloads.db")

def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                referer TEXT,
                origin TEXT,
                status TEXT DEFAULT 'QUEUED',
                file_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        try: conn.execute("ALTER TABLE queue ADD COLUMN title TEXT")
        except sqlite3.OperationalError: pass
        try: conn.execute("ALTER TABLE queue ADD COLUMN progress TEXT DEFAULT '0'")
        except sqlite3.OperationalError: pass
        try: conn.execute("ALTER TABLE queue ADD COLUMN speed TEXT DEFAULT ''")
        except sqlite3.OperationalError: pass
        try: conn.execute("ALTER TABLE queue ADD COLUMN size TEXT DEFAULT ''")
        except sqlite3.OperationalError: pass
        try: conn.execute("ALTER TABLE queue ADD COLUMN eta TEXT DEFAULT ''")
        except sqlite3.OperationalError: pass
        # NEW: Add the auto_verify toggle column
        try: conn.execute("ALTER TABLE queue ADD COLUMN auto_verify INTEGER DEFAULT 1")
        except sqlite3.OperationalError: pass

        # Reset interrupted active tasks (Leave 'AWAITING_VERIFICATION' alone, it's a stable state)
        conn.execute("UPDATE queue SET status = 'QUEUED', progress = '0', speed = '', size = '', eta = '' WHERE status IN ('DOWNLOADING', 'VERIFYING')")
        conn.commit()

def add_task(url: str, referer: str = None, origin: str = None, title: str = None, auto_verify: bool = True):
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO queue (url, referer, origin, title, auto_verify) VALUES (?, ?, ?, ?, ?)",
            (url, referer, origin, title, int(auto_verify))
        )
        conn.commit()
        return cursor.lastrowid

def update_status(task_id: int, status: str, file_path: str = None, progress: str = None, speed: str = None, size: str = None, eta: str = None):
    with get_db() as conn:
        if file_path:
            conn.execute("UPDATE queue SET status = ?, file_path = ? WHERE id = ?", (status, file_path, task_id))
        elif progress is not None:
            conn.execute("""
                UPDATE queue 
                SET status = ?, 
                    progress = ?, 
                    speed = COALESCE(?, speed), 
                    size = COALESCE(?, size),
                    eta = COALESCE(?, eta)
                WHERE id = ?
            """, (status, progress, speed, size, eta, task_id))
        else:
            conn.execute("UPDATE queue SET status = ? WHERE id = ?", (status, task_id))
        conn.commit()

def get_queued_tasks():
    with get_db() as conn:
        return conn.execute("SELECT * FROM queue WHERE status = 'QUEUED'").fetchall()

def clear_history():
    """Deletes inactive tasks from the DB and sweeps their orphaned files from the drive."""
    with get_db() as conn:
        # Ignore AWAITING_VERIFICATION so we don't accidentally delete pending files
        tasks_to_delete = conn.execute("SELECT id, title FROM queue WHERE status IN ('COMPLETED', 'FAILED', 'CANCELED')").fetchall()
        
        conn.execute("DELETE FROM queue WHERE status IN ('COMPLETED', 'FAILED', 'CANCELED')")
        conn.commit()

    work_dir = "/media"
    if not os.path.exists(work_dir): 
        return

    for task in tasks_to_delete:
        task_id = task['id']
        title = task['title']
        
        if not title:
            safe_title = f"movie_{task_id}"
        else:
            safe_title = re.sub(r'[^\w\-_\. ]', '_', title).strip() or f"movie_{task_id}"

        for f in os.listdir(work_dir):
            if f.startswith(safe_title + ".") and os.path.isfile(os.path.join(work_dir, f)):
                try: os.remove(os.path.join(work_dir, f))
                except Exception: pass

def get_task(task_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM queue WHERE id = ?", (task_id,)).fetchone()

def update_task_source(task_id: int, new_url: str):
    with get_db() as conn:
        conn.execute("UPDATE queue SET url = ? WHERE id = ?", (new_url, task_id))
        conn.commit()