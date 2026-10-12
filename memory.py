"""Persistent memory backed by sqlite. Facts survive across sessions."""
import datetime
import os
import sqlite3


class Memory:
    def __init__(self, path: str):
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        # check_same_thread=False: shared with FastAPI worker threads; writes are tiny.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS facts ("
            "key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)"
        )
        self.conn.commit()

    def read(self, key: str = ""):
        cur = self.conn.cursor()
        if key:
            cur.execute(
                "SELECT key, value, updated_at FROM facts WHERE key LIKE ?",
                (f"%{key}%",),
            )
        else:
            cur.execute(
                "SELECT key, value, updated_at FROM facts ORDER BY updated_at DESC"
            )
        return [
            {"key": k, "value": v, "updated_at": t}
            for k, v, t in cur.fetchall()
        ]

    def write(self, key: str, value: str) -> bool:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            "INSERT INTO facts(key, value, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
            "updated_at=excluded.updated_at",
            (key, value, now),
        )
        self.conn.commit()
        return True
