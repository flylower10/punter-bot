"""
Connection-level SQLite settings: Flask request threads and APScheduler
jobs share the database, so connections must use WAL (readers don't block
the writer) and a busy timeout (writers wait instead of failing with
'database is locked' mid-match on a Saturday).
"""

from src.db import get_db


class TestConnectionSettings:
    def test_wal_journal_mode(self):
        conn = get_db()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode.lower() == "wal"

    def test_busy_timeout_set(self):
        conn = get_db()
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        conn.close()
        assert timeout >= 5000

    def test_foreign_keys_still_enforced(self):
        conn = get_db()
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        conn.close()
        assert fk == 1
