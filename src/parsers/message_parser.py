import re

from src.config import Config

# Player nicknames used for result detection and test mode prefix matching
PLAYER_NICKNAMES = {"ed", "kev", "da", "don", "nug", "nialler", "pawn", "nugget"}

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


def _looks_like_pick(text):
    """Check if text looks like a pick (bet description) without explicit odds."""
    # Bet type keywords (BTTS, handicap, over/under, ht/ft)
    for pattern in BET_TYPE_PATTERNS.values():
        if pattern.search(text):
            return True
    # Win bet patterns ("to beat", "to win")
    for pattern in WIN_PICK_PATTERNS:
        if pattern.search(text):
            return True
    # Team vs team (e.g. "Leicester/Soton", "Scotland + 8")
    if re.search(r"\w+[/\s]+(v|vs\.?|@)\s*\w+", text, re.IGNORECASE):
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


def parse_message(text, sender="", sender_phone=""):
    """
    Classify a message and extract relevant data.

    Returns a dict with:
        type: 'command' | 'pick' | 'result' | 'general'
        raw_text: the original message
        sender: who sent it
        sender_phone: sender's phone number
        parsed_data: dict with type-specific fields
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

    # Results: player name + win/loss emoji
    result = _parse_result(text, sender, sender_phone)
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


def _parse_result(text, sender, sender_phone=""):
    """Detect result messages like 'Kev check_emoji' or 'DA cross_emoji'."""
    if WIN_EMOJI not in text and LOSS_EMOJI not in text:
        return None

    text_lower = text.lower()
    for nickname in PLAYER_NICKNAMES:
        if nickname in text_lower:
            outcome = "win" if WIN_EMOJI in text else "loss"
            return _make_result("result", text, sender, {
                "player_nickname": nickname,
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

    return _make_result("pick", text, sender, {
        "description": description,
        "odds_original": odds_original,
        "odds_decimal": odds_decimal,
        "bet_type": bet_type,
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

    return results
