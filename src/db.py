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
    seed_player_aliases(conn)
    seed_team_aliases(conn)
    conn.close()


def _run_migrations(conn):
    """Apply schema migrations for existing databases."""
    _migrate_weeks_group_id(conn)
    _migrate_picks_enrichment(conn)
    _migrate_picks_drop_dead_columns(conn)
    _migrate_fixture_events(conn)
    _migrate_team_aliases_sport(conn)
    _migrate_players_aliases(conn)


def _column_exists(conn, table, column):
    """Check if a column exists on a table."""
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(c[1] == column for c in cols)


def _migrate_weeks_group_id(conn):
    """Add group_id column to weeks table and update UNIQUE constraint."""
    if _column_exists(conn, "weeks", "group_id"):
        return

    conn.executescript("""
        PRAGMA foreign_keys = OFF;
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
        PRAGMA foreign_keys = ON;
    """)
    conn.commit()


def _migrate_picks_enrichment(conn):
    """Add enrichment columns to picks table (Step 1 schema changes)."""
    new_cols = [
        ("sport", "TEXT"),
        ("api_fixture_id", "INTEGER"),
        ("market_price", "REAL"),
        ("confirmed_odds", "REAL"),
    ]
    for col_name, col_type in new_cols:
        if not _column_exists(conn, "picks", col_name):
            conn.execute(f"ALTER TABLE picks ADD COLUMN {col_name} {col_type}")
    conn.commit()


def _migrate_picks_drop_dead_columns(conn):
    """Drop unused picks columns: is_late, competition, event_name, market_type."""
    dead_cols = ["is_late", "competition", "event_name", "market_type"]
    for col in dead_cols:
        if _column_exists(conn, "picks", col):
            conn.execute(f"ALTER TABLE picks DROP COLUMN {col}")
    conn.commit()


def _migrate_fixture_events(conn):
    """Create fixture_events table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fixture_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_api_id INTEGER NOT NULL,
            event_key TEXT NOT NULL,
            event_type TEXT NOT NULL,
            detail TEXT,
            minute INTEGER,
            team TEXT,
            player TEXT,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(fixture_api_id, event_key)
        )
    """)
    conn.commit()


def _migrate_team_aliases_sport(conn):
    """Add sport column to team_aliases table and update UNIQUE constraint."""
    if _column_exists(conn, "team_aliases", "sport"):
        return

    conn.executescript("""
        PRAGMA foreign_keys = OFF;
        DROP TABLE IF EXISTS team_aliases_new;
        CREATE TABLE team_aliases_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alias TEXT NOT NULL COLLATE NOCASE,
            canonical_name TEXT NOT NULL,
            sport TEXT NOT NULL DEFAULT 'football',
            UNIQUE(alias, sport)
        );
        INSERT INTO team_aliases_new (id, alias, canonical_name, sport)
        SELECT id, alias, canonical_name, 'football' FROM team_aliases;
        DROP TABLE team_aliases;
        ALTER TABLE team_aliases_new RENAME TO team_aliases;
        PRAGMA foreign_keys = ON;
    """)
    conn.commit()


def _migrate_players_aliases(conn):
    """Add aliases column to players table."""
    if _column_exists(conn, "players", "aliases"):
        return
    conn.execute("ALTER TABLE players ADD COLUMN aliases TEXT DEFAULT ''")
    conn.commit()


def seed_team_aliases(conn):
    """Seed team aliases if the table is empty. Covers common abbreviations."""
    count = conn.execute("SELECT COUNT(*) FROM team_aliases").fetchone()[0]
    if count > 0:
        return

    # Football aliases (alias, canonical_name, sport)
    football_aliases = [
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

    # Rugby aliases
    rugby_aliases = [
        # Irish Provinces (URC)
        ("munster", "Munster Rugby"),
        ("leinster", "Leinster Rugby"),
        ("ulster", "Ulster Rugby"),
        ("connacht", "Connacht Rugby"),
        # Six Nations
        ("ireland", "Ireland"),
        ("scotland", "Scotland"),
        ("wales", "Wales"),
        ("france", "France"),
        ("italy", "Italy"),
        ("england", "England"),
        # Other
        ("all blacks", "New Zealand"),
        ("springboks", "South Africa"),
        ("wallabies", "Australia"),
        ("saracens", "Saracens"),
        ("bath", "Bath Rugby"),
        ("northampton", "Northampton Saints"),
        ("saints", "Northampton Saints"),
    ]

    # NFL aliases
    nfl_aliases = [
        ("kc", "Kansas City Chiefs"),
        ("philly", "Philadelphia Eagles"),
        ("sf", "San Francisco 49ers"),
        ("gb", "Green Bay Packers"),
        ("ne", "New England Patriots"),
        ("tb", "Tampa Bay Buccaneers"),
        ("la rams", "Los Angeles Rams"),
        ("la chargers", "Los Angeles Chargers"),
    ]

    # NBA aliases
    nba_aliases = [
        ("sixers", "Philadelphia 76ers"),
        ("cavs", "Cleveland Cavaliers"),
        ("mavs", "Dallas Mavericks"),
        ("wolves", "Minnesota Timberwolves"),
    ]

    rows = []
    for alias, canonical in football_aliases:
        rows.append((alias, canonical, "football"))
    for alias, canonical in rugby_aliases:
        rows.append((alias, canonical, "rugby"))
    for alias, canonical in nfl_aliases:
        rows.append((alias, canonical, "nfl"))
    for alias, canonical in nba_aliases:
        rows.append((alias, canonical, "nba"))

    conn.executemany(
        "INSERT OR IGNORE INTO team_aliases (alias, canonical_name, sport) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def seed_player_aliases(conn):
    """Seed known player aliases (idempotent — only updates empty aliases)."""
    conn.execute(
        "UPDATE players SET aliases = ? WHERE nickname = ? AND (aliases IS NULL OR aliases = '')",
        ("don", "DA"),
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
