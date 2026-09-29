"""Small local incident ledger with an atomic duplicate-retention guard."""
import json
import sqlite3
from contextlib import contextmanager


class IncidentStore:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, owner TEXT, payload TEXT, state TEXT)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, incident, owner, state="OPEN"):
        with self.connect() as db:
            db.execute("INSERT INTO incidents VALUES (?, ?, ?, ?)",
                       (incident["incident_id"], owner, json.dumps(incident), state))

    def get(self, incident_id, owner):
        with self.connect() as db:
            row = db.execute("SELECT payload, state FROM incidents WHERE id=? AND owner=?", (incident_id, owner)).fetchone()
        return ({**json.loads(row[0]), "state": row[1]} if row else None)

    def list_for(self, owner):
        with self.connect() as db:
            rows = db.execute("SELECT payload, state FROM incidents WHERE owner=? ORDER BY rowid DESC", (owner,)).fetchall()
        return [{**json.loads(payload), "state": state} for payload, state in rows]

    def claim(self, incident_id, owner):
        with self.connect() as db:
            return db.execute("UPDATE incidents SET state='RETAINING' WHERE id=? AND owner=? AND state='OPEN'", (incident_id, owner)).rowcount == 1

    def update(self, incident, owner, state):
        with self.connect() as db:
            db.execute("UPDATE incidents SET payload=?, state=? WHERE id=? AND owner=?",
                       (json.dumps(incident), state, incident["incident_id"], owner))
