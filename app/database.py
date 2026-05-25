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
        # NEW: Add the ETA column
        try: conn.execute("ALTER TABLE queue ADD COLUMN eta TEXT DEFAULT ''")
        except sqlite3.OperationalError: pass

        # Reset all telemetry on startup
        conn.execute("UPDATE queue SET status = 'QUEUED', progress = '0', speed = '', size = '', eta = '' WHERE status IN ('DOWNLOADING', 'VERIFYING')")
        conn.commit()

def add_task(url: str, referer: str = None, origin: str = None, title: str = None):
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO queue (url, referer, origin, title) VALUES (?, ?, ?, ?)",
            (url, referer, origin, title)
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
        # 1. Fetch the tasks we are about to delete so we know their filenames
        tasks_to_delete = conn.execute("SELECT id, title FROM queue WHERE status IN ('COMPLETED', 'FAILED', 'CANCELED')").fetchall()
        
        # 2. Delete them from the database
        conn.execute("DELETE FROM queue WHERE status IN ('COMPLETED', 'FAILED', 'CANCELED')")
        conn.commit()

    # 3. Garbage Collection: Sweep the /media/ directory
    work_dir = "/media"
    if not os.path.exists(work_dir): 
        return

    for task in tasks_to_delete:
        task_id = task['id']
        title = task['title']
        
        # Reconstruct the exact filename the downloader would have used
        if not title:
            safe_title = f"movie_{task_id}"
        else:
            safe_title = re.sub(r'[^\w\-_\. ]', '_', title).strip() or f"movie_{task_id}"

        # Delete any files in the working directory that belong to this dead task
        for f in os.listdir(work_dir):
            if f.startswith(safe_title + ".") and os.path.isfile(os.path.join(work_dir, f)):
                try:
                    os.remove(os.path.join(work_dir, f))
                except Exception:
                    pass # Skip if locked

def get_task(task_id: int):
    """Retrieves a single task's data so we can reuse the custom title."""
    with get_db() as conn:
        return conn.execute("SELECT * FROM queue WHERE id = ?", (task_id,)).fetchone()

def update_task_source(task_id: int, new_url: str):
    """Replaces the expired URL with a fresh one."""
    with get_db() as conn:
        conn.execute("UPDATE queue SET url = ? WHERE id = ?", (new_url, task_id))
        conn.commit()