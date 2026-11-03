import json
import sqlite3
import threading


class Store:
    """Append-only event log in SQLite. Ids are the replay cursor for SSE."""

    def __init__(self, path: str = ":memory:"):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT)")
        self._lock = threading.Lock()

    def append(self, event: dict) -> dict:
        with self._lock:
            cur = self._db.execute("INSERT INTO events (body) VALUES (?)", (json.dumps(event),))
            self._db.commit()
        return {**event, "id": cur.lastrowid}

    def since(self, last_id: int = 0, limit: int = 500) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, body FROM events WHERE id > ? ORDER BY id LIMIT ?", (last_id, limit)
            ).fetchall()
        return [{**json.loads(body), "id": id_} for id_, body in rows]

    def has_serial(self, serial: str) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM events WHERE json_extract(body, '$.evidence.serial') = ? LIMIT 1", (serial,)
            ).fetchone()
        return row is not None
