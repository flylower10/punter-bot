-- Punter Bot Database Schema

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    nickname TEXT NOT NULL UNIQUE,
    formal_name TEXT NOT NULL,
    emoji TEXT,
    phone TEXT,
    rotation_position INTEGER NOT NULL,
    aliases TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS weeks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_number INTEGER NOT NULL,
    season TEXT NOT NULL,
    group_id TEXT NOT NULL DEFAULT 'default',
    deadline TIMESTAMP NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed', 'completed')),
    placer_id INTEGER REFERENCES players(id),
    placer_is_penalty INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(week_number, season, group_id)
);

CREATE TABLE IF NOT EXISTS picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_id INTEGER NOT NULL REFERENCES weeks(id),
    player_id INTEGER NOT NULL REFERENCES players(id),
    description TEXT NOT NULL,
    odds_decimal REAL NOT NULL,
    odds_original TEXT NOT NULL,
    bet_type TEXT NOT NULL DEFAULT 'win' CHECK (bet_type IN ('win', 'btts', 'handicap', 'over_under', 'ht_ft', 'other')),
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Enrichment columns (populated by API matching, nullable)
    sport TEXT,
    api_fixture_id INTEGER,
    market_price REAL,
    confirmed_odds REAL,
    UNIQUE(week_id, player_id)
);

CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pick_id INTEGER NOT NULL UNIQUE REFERENCES picks(id),
    outcome TEXT NOT NULL CHECK (outcome IN ('win', 'loss', 'void', 'pending')),
    score TEXT,
    confirmed_by TEXT,
    confirmed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS penalties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id),
    week_id INTEGER REFERENCES weeks(id),
    type TEXT NOT NULL CHECK (type IN ('late', 'streak_3', 'streak_5', 'streak_7', 'streak_10')),
    amount REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'suggested' CHECK (status IN ('suggested', 'confirmed', 'paid')),
    confirmed_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vault (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    penalty_id INTEGER REFERENCES penalties(id),
    amount REAL NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rotation_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id),
    reason TEXT NOT NULL,
    position INTEGER NOT NULL,
    week_added INTEGER REFERENCES weeks(id),
    processed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fixtures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_id INTEGER NOT NULL UNIQUE,
    sport TEXT NOT NULL DEFAULT 'football',
    competition TEXT NOT NULL,
    competition_id INTEGER,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    kickoff TIMESTAMP NOT NULL,
    status TEXT DEFAULT 'NS',
    home_score INTEGER,
    away_score INTEGER,
    ht_home_score INTEGER,
    ht_away_score INTEGER,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS team_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias TEXT NOT NULL COLLATE NOCASE,
    canonical_name TEXT NOT NULL,
    sport TEXT NOT NULL DEFAULT 'football',
    UNIQUE(alias, sport)
);

CREATE TABLE IF NOT EXISTS bet_slips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_id INTEGER NOT NULL REFERENCES weeks(id),
    placer_id INTEGER NOT NULL REFERENCES players(id),
    total_odds REAL,
    stake REAL,
    potential_return REAL,
    image_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
);
