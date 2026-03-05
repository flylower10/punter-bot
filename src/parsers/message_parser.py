import re

from src.config import Config

# Player nicknames/names used for result detection and test mode prefix matching
# Include both nicknames (Pawn, DA) and first names (Aidan) for flexibility
PLAYER_NICKNAMES = {"ed", "kev", "da", "don", "nug", "nialler", "pawn", "nugget", "aidan"}

# Test mode prefix pattern: "Kev: some message" or "Ed: !stats"
TEST_PREFIX = re.compile(
    r"^(" + "|".join(PLAYER_NICKNAMES) + r")\s*:\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)

# Odds patterns
FRACTIONAL_ODDS = re.compile(r"\b(\d+/\d+)\b")
DECIMAL_ODDS = re.compile(r"\b(\d+\.\d{1,2})\b")
EVENS = re.compile(r"\bevens?\b", re.IGNORECASE)

# Result emojis
WIN_EMOJI = "\u2705"  # green check
LOSS_EMOJI = "\u274c"  # red cross

# Bet type keywords
BET_TYPE_PATTERNS = {
    "btts": re.compile(r"\bbtts\b", re.IGNORECASE),
    "over_under": re.compile(r"\b(over|under)\s+\d+\.?\d*\b", re.IGNORECASE),
    "handicap": re.compile(r"(?<!\d)[+-]\s*\d+\.?\d*\b"),
    "ht_ft": re.compile(r"\bht[/_]?ft\b", re.IGNORECASE),
}

# Win bet patterns (for no-odds picks: "Dortmund to beat Mainz", "Liverpool to win")
WIN_PICK_PATTERNS = [
    re.compile(r"\bto\s+beat\b", re.IGNORECASE),
    re.compile(r"\bto\s+win\b", re.IGNORECASE),
]

# Sport detection keywords — order matters (checked first to last, first match wins)
SPORT_KEYWORDS = {
    "rugby": re.compile(
        r"\b(rugby|six\s*nations|pro\s*14|urc|heineken\s*cup|"
        r"munster|leinster|ulster|connacht|"
        r"all\s*blacks|springboks|wallabies|"
        r"try\s*scorer)\b",
        re.IGNORECASE,
    ),
    "nfl": re.compile(
        r"\b(nfl|super\s*bowl|touchdown|"
        r"chiefs|eagles|49ers|niners|bills|ravens|cowboys|packers|dolphins|"
        r"lions|bengals|jets|patriots|steelers|broncos|chargers|raiders|"
        r"seahawks|rams|cardinals|falcons|panthers|saints|buccaneers|bucs|"
        r"bears|vikings|commanders|giants|texans|colts|jaguars|jags|titans)\b",
        re.IGNORECASE,
    ),
    "nba": re.compile(
        r"\b(nba|lakers|celtics|warriors|bucks|nuggets|76ers|sixers|"
        r"nets|knicks|heat|suns|clippers|mavericks|mavs|grizzlies|"
        r"cavaliers|cavs|timberwolves|wolves|pelicans|kings|hawks|"
        r"raptors|thunder|blazers|spurs|rockets|pistons|pacers|"
        r"hornets|wizards|magic|jazz)\b",
        re.IGNORECASE,
    ),
    "nhl": re.compile(
        r"\b(nhl|stanley\s*cup|"
        r"maple\s*leafs|canadiens|habs|bruins|rangers|islanders|"
        r"penguins|capitals|caps|flyers|red\s*wings|blackhawks|"
        r"oilers|flames|canucks|avalanche|stars|predators|preds|"
        r"lightning|panthers|hurricanes|canes|blue\s*jackets|"
        r"kraken|wild|senators|sens|sabres|devils|ducks)\b",
        re.IGNORECASE,
    ),
    "mma": re.compile(
        r"\b(mma|ufc|bellator|ko|tko|submission|"
        r"by\s*decision|by\s*knockout|octagon|"
        r"flyweight|bantamweight|featherweight|lightweight|"
        r"welterweight|middleweight|heavyweight)\b",
        re.IGNORECASE,
    ),
    "horse_racing": re.compile(
        r"\b(horse\s*racing|cheltenham|aintree|grand\s*national|"
        r"royal\s*ascot|epsom|guineas|nap|"
        r"each\s*way|going\s*ground|furlong|"
        r"novice\s*hurdle|champion\s*hurdle|gold\s*cup)\b",
        re.IGNORECASE,
    ),
    "tennis": re.compile(
        r"\b(tennis|wimbledon|roland\s*garros|french\s*open|"
        r"us\s*open\s*tennis|australian\s*open|grand\s*slam|"
        r"atp|wta|sets?\s*handicap)\b",
        re.IGNORECASE,
    ),
    "golf": re.compile(
        r"\b(golf|masters|pga|ryder\s*cup|"
        r"open\s*championship|us\s*open\s*golf|"
        r"top\s*\d+\s*finish|outright\s*winner)\b",
        re.IGNORECASE,
    ),
    "boxing": re.compile(
        r"\b(boxing|bout|rounds?\s*betting|"
        r"by\s*stoppage|on\s*points|undisputed)\b",
        re.IGNORECASE,
    ),
    "darts": re.compile(
        r"\b(darts|pdc|bdo|"
        r"premier\s*league\s*darts|"
        r"world\s*darts|180s?\s*over)\b",
        re.IGNORECASE,
    ),
    "formula1": re.compile(
        r"\b(f1|formula\s*1|formula\s*one|grand\s*prix|gp|"
        r"red\s*bull|ferrari|mclaren|mercedes|alpine|aston\s*martin|"
        r"williams|haas|rb|sauber|kick\s*sauber|"
        r"verstappen|hamilton|leclerc|norris|piastri|sainz|russell|"
        r"alonso|stroll|gasly|ocon|tsunoda|hulkenberg)\b",
        re.IGNORECASE,
    ),
}

# GAA county classification for two-step sport detection
_HURLING_COUNTIES = {"kilkenny", "waterford", "wexford", "clare"}
_FOOTBALL_COUNTIES = {
    "tyrone", "donegal", "monaghan", "cavan", "fermanagh", "leitrim", "longford",
    "sligo", "roscommon", "mayo", "louth", "carlow", "wicklow",
}
_DUAL_COUNTIES = {
    "dublin", "cork", "kerry", "galway", "limerick", "tipperary",
    "meath", "kildare", "laois", "offaly", "westmeath",
    "down", "armagh", "derry", "antrim",
}
_ALL_COUNTIES = _HURLING_COUNTIES | _FOOTBALL_COUNTIES | _DUAL_COUNTIES

_HURLING_KEYWORDS_RE = re.compile(
    r"\b(hurling|camogie|liam\s*maccarthy)\b", re.IGNORECASE
)
_GAA_FOOTBALL_KEYWORDS_RE = re.compile(
    r"\b(gaa\s*football|sam\s*maguire)\b", re.IGNORECASE
)
_GAA_GENERIC_RE = re.compile(
    r"\b(gaa|all[\s-]*ireland)\b", re.IGNORECASE
)
_COUNTY_RE = re.compile(
    r"\b(" + "|".join(sorted(_ALL_COUNTIES, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def detect_sport(text):
    """
    Detect the sport from pick text using keyword matching.

    Returns the sport name (e.g. "rugby", "nfl", "tennis") or "football" as default.
    GAA uses two-step detection: county names + explicit keywords → gaa_football or gaa_hurling.
    """
    if not text:
        return "football"
    for sport, pattern in SPORT_KEYWORDS.items():
        if pattern.search(text):
            return sport

    # Two-step GAA detection (after other sports, before football fallback)
    gaa = _detect_gaa(text)
    if gaa:
        return gaa

    # Handicap heuristic: football handicaps rarely exceed ±3.5.
    # A large handicap (e.g. "Ireland -26") strongly suggests rugby.
    m = re.search(r"(?<!\d)[+-]\s*(\d+\.?\d*)\b", text)
    if m and float(m.group(1)) >= 4:
        return "rugby"

    return "football"


def _detect_gaa(text):
    """
    Detect GAA football vs hurling from pick text.

    Returns 'gaa_football', 'gaa_hurling', or None.
    """
    has_hurling = bool(_HURLING_KEYWORDS_RE.search(text))
    has_gaa_football = bool(_GAA_FOOTBALL_KEYWORDS_RE.search(text))
    has_gaa_generic = bool(_GAA_GENERIC_RE.search(text))

    # Explicit hurling keyword always wins
    if has_hurling:
        return "gaa_hurling"

    # Explicit GAA football keyword
    if has_gaa_football:
        return "gaa_football"

    # Generic "gaa" or "all-ireland" → default gaa_football
    if has_gaa_generic:
        return "gaa_football"

    # County name detection
    match = _COUNTY_RE.search(text)
    if match:
        county = match.group(1).lower()
        if county in _HURLING_COUNTIES:
            return "gaa_hurling"
        # Football-only or dual county → gaa_football
        return "gaa_football"

    return None


def gaa_needs_clarification(text):
    """
    Return True if the pick was detected as GAA via a dual-code county
    without an explicit hurling/football qualifier.
    """
    if not text:
        return False
    # If there's an explicit keyword, no ambiguity
    if _HURLING_KEYWORDS_RE.search(text):
        return False
    if _GAA_FOOTBALL_KEYWORDS_RE.search(text):
        return False
    if _GAA_GENERIC_RE.search(text):
        return False
    # Check if a dual county triggered the detection
    match = _COUNTY_RE.search(text)
    if match and match.group(1).lower() in _DUAL_COUNTIES:
        return True
    return False


def _looks_like_pick(text):
    """Check if text looks like a pick (bet description) without explicit odds."""
    # Long messages are almost certainly chat, not picks
    if len(text.split()) > 15:
        return False
    # Bet type keywords (BTTS, handicap, over/under, ht/ft)
    for pattern in BET_TYPE_PATTERNS.values():
        if pattern.search(text):
            return True
    # Win bet patterns ("to beat", "to win")
    for pattern in WIN_PICK_PATTERNS:
        if pattern.search(text):
            return True
    # Team vs team (e.g. "Leicester/Soton", "Leicester v Soton")
    if re.search(r"\w+\s+(?:vs?\.?|@)\s+\w+", text, re.IGNORECASE):
        return True
    if re.search(r"\w+/\w+", text) and len(text.split()) <= 8:
        return True
    if re.search(r"[+-]\s*\d+\.?\d*", text):  # Handicap-style
        return True
    return False


def extract_test_prefix(text):
    """
    In test mode, extract player prefix from messages like 'Kev: Manchester United 2/1'.

    Returns (sender_override, remaining_text) or (None, original_text).
    """
    if not Config.TEST_MODE:
        return None, text

    match = TEST_PREFIX.match(text.strip())
    if match:
        return match.group(1), match.group(2).strip()

    return None, text


def parse_message(text, sender="", sender_phone="", emoji_map=None):
    """
    Classify a message and extract relevant data.

    Returns a dict with:
        type: 'command' | 'pick' | 'result' | 'general'
        raw_text: the original message
        sender: who sent it
        sender_phone: sender's phone number
        parsed_data: dict with type-specific fields

    emoji_map: optional dict of emoji -> player for emoji-based result detection.
    """
    text = text.strip()

    if not text:
        return _make_result("general", text, sender, {}, sender_phone)

    # In test mode, extract player prefix (e.g., "Kev: Manchester United 2/1")
    sender_override, text = extract_test_prefix(text)
    if sender_override:
        sender = sender_override

    # Commands: starts with !
    if text.startswith("!"):
        return _parse_command(text, sender, sender_phone)

    # Results: player name or emoji + win/loss emoji
    result = _parse_result(text, sender, sender_phone, emoji_map=emoji_map)
    if result:
        return result

    # Picks: contains odds
    pick = _parse_pick(text, sender, sender_phone)
    if pick:
        return pick

    return _make_result("general", text, sender, {}, sender_phone)


def _parse_command(text, sender, sender_phone=""):
    """Parse a !command message."""
    parts = text[1:].strip().split()
    command = parts[0].lower() if parts else ""
    args = parts[1:] if len(parts) > 1 else []

    return _make_result("command", text, sender, {
        "command": command,
        "args": args,
    }, sender_phone)


def _parse_result(text, sender, sender_phone="", emoji_map=None):
    """Detect result messages like 'Kev check_emoji' or '♟️❌'."""
    if WIN_EMOJI not in text and LOSS_EMOJI not in text:
        return None

    outcome = "win" if WIN_EMOJI in text else "loss"

    # Match nicknames as whole words (so "da" doesn't match inside "Aidan")
    # Sort by length descending so "nialler" matches before "nug" in "Nialler"
    for nickname in sorted(PLAYER_NICKNAMES, key=len, reverse=True):
        pattern = re.compile(r"\b" + re.escape(nickname) + r"\b", re.IGNORECASE)
        if pattern.search(text):
            return _make_result("result", text, sender, {
                "player_nickname": nickname,
                "outcome": outcome,
            }, sender_phone)

    # Emoji-based result: e.g. "♟️❌" or "🍋✅"
    if emoji_map:
        for emoji_str, player in sorted(emoji_map.items(), key=lambda x: -len(x[0])):
            if emoji_str in text:
                return _make_result("result", text, sender, {
                    "player_nickname": player["nickname"],
                    "outcome": outcome,
                }, sender_phone)

    return None


def _parse_pick(text, sender, sender_phone=""):
    """Detect pick submissions containing odds."""
    odds_original = None
    odds_decimal = None

    # Check for fractional odds (e.g. 2/1, 11/4)
    match = FRACTIONAL_ODDS.search(text)
    if match:
        odds_original = match.group(1)
        num, den = odds_original.split("/")
        odds_decimal = round(int(num) / int(den) + 1, 4)

    # Check for "evens"
    if not odds_original and EVENS.search(text):
        odds_original = "evens"
        odds_decimal = 2.0

    # Check for decimal odds (e.g. 2.0, 3.75)
    if not odds_original:
        match = DECIMAL_ODDS.search(text)
        if match:
            odds_original = match.group(1)
            odds_decimal = float(odds_original)

    # No odds: allow if text looks like a pick (player trusts placer, odds >= 1.5)
    if not odds_original:
        if not _looks_like_pick(text):
            return None
        odds_original = "placer"
        odds_decimal = 2.0  # Default; placer confirms at bookie

    # Detect bet type
    bet_type = "win"
    for bt, pattern in BET_TYPE_PATTERNS.items():
        if pattern.search(text):
            bet_type = bt
            break

    # Description is the full text minus the odds
    description = text

    # Detect sport from pick text
    sport = detect_sport(text)

    return _make_result("pick", text, sender, {
        "description": description,
        "odds_original": odds_original,
        "odds_decimal": odds_decimal,
        "bet_type": bet_type,
        "sport": sport,
    }, sender_phone)


def _make_result(msg_type, text, sender, parsed_data, sender_phone=""):
    return {
        "type": msg_type,
        "raw_text": text,
        "sender": sender,
        "sender_phone": sender_phone,
        "parsed_data": parsed_data,
    }


def parse_cumulative_picks(text, emoji_to_player):
    """
    Parse a message containing multiple picks, one per line, each prefixed with
    a player's emoji. Format: "♟️ Dortmund 6/10\\n🃏 Liverpool 2/1"

    Returns list of (player_dict, pick_parsed_data) for each valid line.
    emoji_to_player: dict from get_emoji_to_player_map().
    """
    if not emoji_to_player:
        return []

    # Sort emojis by length descending so longer sequences match first
    emojis = sorted(emoji_to_player.keys(), key=len, reverse=True)

    results = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # Find which emoji (if any) this line starts with
        matched_emoji = None
        for emoji in emojis:
            if line.startswith(emoji):
                matched_emoji = emoji
                break

        if not matched_emoji:
            continue

        player = emoji_to_player[matched_emoji]
        pick_text = line[len(matched_emoji) :].strip()

        pick = _parse_pick(pick_text, player["nickname"], "")
        if pick and pick["type"] == "pick":
            results.append((player, pick["parsed_data"]))
        elif pick_text:
            # In cumulative format, emoji prefix = pick line. Accept bare team names
            # (e.g. "Villa", "Dortmund") that _parse_pick would reject.
            results.append((player, {
                "description": pick_text,
                "odds_original": "placer",
                "odds_decimal": 2.0,
                "bet_type": "win",
                "sport": detect_sport(pick_text),
            }))

    return results
