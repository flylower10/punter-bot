import os
import sqlite3
from pathlib import Path

from src.config import Config


def get_db():
    """Return a connection to the SQLite database."""
    db_path = Config.DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables from schema.sql if they don't exist, then seed players."""
    schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path) as f:
        schema_sql = f.read()

    conn = get_db()
    conn.executescript(schema_sql)
    conn.commit()

    _run_migrations(conn)
    seed_players(conn)
    seed_team_aliases(conn)
    conn.close()


def _run_migrations(conn):
    """Apply schema migrations for existing databases."""
    _migrate_weeks_group_id(conn)
    _migrate_picks_enrichment(conn)


def _column_exists(conn, table, column):
    """Check if a column exists on a table."""
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(c[1] == column for c in cols)


def _migrate_weeks_group_id(conn):
    """Add group_id column to weeks table and update UNIQUE constraint."""
    if _column_exists(conn, "weeks", "group_id"):
        return

    conn.executescript("""
        DROP TABLE IF EXISTS weeks_new;
        CREATE TABLE weeks_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_number INTEGER NOT NULL,
            season TEXT NOT NULL,
            group_id TEXT NOT NULL DEFAULT 'default',
            deadline TIMESTAMP NOT NULL,
            status TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'closed', 'completed')),
            placer_id INTEGER REFERENCES players(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(week_number, season, group_id)
        );
        INSERT INTO weeks_new
            (id, week_number, season, group_id, deadline, status, placer_id, created_at)
        SELECT id, week_number, season, 'default', deadline, status, placer_id, created_at
        FROM weeks;
        DROP TABLE weeks;
        ALTER TABLE weeks_new RENAME TO weeks;
    """)
    conn.commit()


def _migrate_picks_enrichment(conn):
    """Add enrichment columns to picks table (Step 1 schema changes)."""
    new_cols = [
        ("sport", "TEXT"),
        ("competition", "TEXT"),
        ("event_name", "TEXT"),
        ("market_type", "TEXT"),
        ("api_fixture_id", "INTEGER"),
        ("market_price", "REAL"),
        ("confirmed_odds", "REAL"),
    ]
    for col_name, col_type in new_cols:
        if not _column_exists(conn, "picks", col_name):
            conn.execute(f"ALTER TABLE picks ADD COLUMN {col_name} {col_type}")
    conn.commit()


def seed_team_aliases(conn):
    """Seed team aliases if the table is empty. Covers common abbreviations."""
    count = conn.execute("SELECT COUNT(*) FROM team_aliases").fetchone()[0]
    if count > 0:
        return

    aliases = [
        # Premier League
        ("leics", "Leicester City"),
        ("leicester", "Leicester City"),
        ("soton", "Southampton"),
        ("man utd", "Manchester United"),
        ("man u", "Manchester United"),
        ("united", "Manchester United"),
        ("man city", "Manchester City"),
        ("city", "Manchester City"),
        ("spurs", "Tottenham"),
        ("tottenham", "Tottenham Hotspur"),
        ("villa", "Aston Villa"),
        ("wolves", "Wolverhampton Wanderers"),
        ("wolverhampton", "Wolverhampton Wanderers"),
        ("newc", "Newcastle United"),
        ("newcastle", "Newcastle United"),
        ("bha", "Brighton & Hove Albion"),
        ("brighton", "Brighton & Hove Albion"),
        ("whu", "West Ham United"),
        ("west ham", "West Ham United"),
        ("qpr", "Queens Park Rangers"),
        ("arsenal", "Arsenal"),
        ("chelsea", "Chelsea"),
        ("liverpool", "Liverpool"),
        ("everton", "Everton"),
        ("palace", "Crystal Palace"),
        ("crystal palace", "Crystal Palace"),
        ("forest", "Nottingham Forest"),
        ("nottm forest", "Nottingham Forest"),
        ("nott forest", "Nottingham Forest"),
        ("bournemouth", "AFC Bournemouth"),
        ("brentford", "Brentford"),
        ("fulham", "Fulham"),
        ("ipswich", "Ipswich Town"),
        # Common European
        ("barca", "Barcelona"),
        ("real", "Real Madrid"),
        ("psg", "Paris Saint-Germain"),
        ("dortmund", "Borussia Dortmund"),
        ("bayern", "Bayern Munich"),
        ("juve", "Juventus"),
        ("atletico", "Atletico Madrid"),
        ("atleti", "Atletico Madrid"),
        ("inter", "Inter Milan"),
        ("ac milan", "AC Milan"),
        ("milan", "AC Milan"),
        ("benfica", "SL Benfica"),
        # Scottish
        ("celtic", "Celtic"),
        ("rangers", "Rangers"),
    ]

    conn.executemany(
        "INSERT OR IGNORE INTO team_aliases (alias, canonical_name) VALUES (?, ?)",
        aliases,
    )
    conn.commit()


def seed_players(conn):
    """Insert the 6 players if the table is empty."""
    count = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    if count > 0:
        return

    players = [
        ("Edmund", "Ed", "Mr Edmund", "🍋,🍋🍋🍋", None, 6),
        ("Kevin", "Kev", "Mr Kevin", "🧌", None, 1),
        ("Declan", "DA", "Mr Declan", "👴🏻", None, 5),
        ("Ronan", "Nug", "Mr Ronan", "🍗", None, 3),
        ("Nialler", "Nialler", "Mr Niall", "🔫", None, 2),
        ("Aidan", "Pawn", "Mr Aidan", "♟️", None, 4),
    ]

    conn.executemany(
        "INSERT INTO players (name, nickname, formal_name, emoji, phone, rotation_position) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        players,
    )
    conn.commit()
