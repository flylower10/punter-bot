# Test Patterns — Punter Bot

Read this before writing any tests. It documents the conventions
used across the 365-test suite so new tests fit without friction.

---

## Test infrastructure

**Runner:** `python3 -m pytest tests/ -v`

**Database:** Every test gets a fresh temporary SQLite database.
The `test_db` fixture in `conftest.py` is `autouse=True` — it runs
automatically for every test. You do not need to request it.

**What `conftest.py` patches for every test:**
```python
Config.DB_PATH      → fresh temp file
Config.TIMEZONE     → "Europe/Dublin"
Config.TEST_MODE    → True
Config.ROTATION_ORDER → []  # uses DB rotation_position, not config list
Config.LLM_ENABLED  → False
Config.GROQ_API_KEY → ""
Config.API_FOOTBALL_KEY → ""
Config.ODDS_API_KEY → ""
```

**Seeded players:** `init_db()` seeds the players table from the schema.
Call `get_all_players()` to get them — do not hardcode player IDs.
The seeded players are: Kev (pos 1), Nialler (pos 2), Nug (pos 3),
Ed (pos 4), Pawn (pos 5), DA (pos 6), Declan/Don (pos 7).

---

## Common setup patterns

### Get a player by nickname
```python
from src.services.player_service import get_all_players
players = get_all_players()
kev = next(p for p in players if p["nickname"] == "Kev")
```

### Create a week and submit picks
```python
from src.services.week_service import get_or_create_current_week
from src.services.pick_service import submit_pick

week = get_or_create_current_week()
submit_pick(player["id"], week["id"], "Liverpool to win", 2.0, "evens", "win")
```

### Submit picks for all players (fully-submitted week)
```python
week = get_or_create_current_week()
players = get_all_players()
for p in players:
    submit_pick(p["id"], week["id"], "Team to win", 2.0, "evens", "win")
```

### Advance rotation and complete a week
```python
from src.services.rotation_service import advance_rotation
from src.db import get_db

advance_rotation(week["id"], player["id"])

conn = get_db()
conn.execute("UPDATE weeks SET status = 'completed' WHERE id = ?", (week["id"],))
conn.commit()
conn.close()
```

### Group ID
Tests that need a group_id should use a named constant, not "default":
```python
GROUP_ID = "test-group@g.us"
week = get_or_create_current_week(group_id=GROUP_ID)
```
This prevents leakage between tests that use the default group and
webhook tests that simulate a real WhatsApp group ID.

---

## Testing WhatsApp webhook flows (app.py)

Use Flask's test client. The webhook expects JSON with `sender` and
`content` keys matching the bridge format.

```python
import pytest
from src.app import app as flask_app

@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c

def test_something(client):
    response = client.post("/webhook", json={
        "sender": "447700000000@s.whatsapp.net",
        "content": "Liverpool 2/1",
        "group_id": "test-group@g.us",
        "type": "text",
    })
    assert response.status_code == 200
```

**Sender format:** WhatsApp JIDs — `{phone}@s.whatsapp.net` for users,
`{id}@g.us` for groups. The sender must match a phone number in the
seeded players table for the message to be attributed to a player.

**To get a player's phone number for use as sender:**
```python
player = next(p for p in get_all_players() if p["nickname"] == "Kev")
sender = f"{player['phone']}@s.whatsapp.net"
```

---

## Testing LLM-dependent paths

LLM calls are disabled by default (`Config.LLM_ENABLED = False`).
To test code that calls the LLM, mock the relevant function directly:

```python
# For bet slip extraction (Groq vision):
monkeypatch.setattr(
    "src.services.bet_slip_service.read_bet_slip",
    lambda image_data: {"stake": 10.0, "total_odds": 5.0, "legs": [...]},
)

# For bridge image fetch:
monkeypatch.setattr(
    "src.services.bet_slip_service.fetch_image_from_bridge",
    lambda msg_id: b"fake-image-bytes",
)
```

**Important:** `read_bet_slip` always returns a dict (never None).
An all-null response `{"stake": None, "total_odds": None, "legs": []}`
means no bet slip was found. Test both the null-response rejection path
and the valid-slip path.

---

## Test file conventions

- One file per module: `test_{module_name}.py`
- One class per logical group of related tests: `class TestPickSubmission:`
- Test method names describe the scenario: `test_general_chat_not_classified_as_pick`
- Use `assert` statements directly — no unittest-style assertions
- DB state assertions: query `get_db()` directly, then `conn.close()`

---

## What is and is not tested at each layer

| Layer | What to test | What not to test |
|-------|-------------|-----------------|
| `message_parser.py` | Classification logic, edge cases, aliases | WhatsApp transport |
| `*_service.py` | Business logic, DB state changes | Message formatting |
| `app.py` webhook | End-to-end flows, routing decisions | Service internals |
| `butler.py` | Message formatting output | Business logic |

---

## Known gaps (Phase 2 targets)

1. **General chat → false pick**: `_looks_like_pick` / `_parse_pick` edge cases
2. **Alias failures**: "Don" / "Declan" / "DA" resolution when recording results
3. **Rotation edge cases**: delegation + penalty queue interaction
4. **Window enforcement on general chat**: out-of-window pick-like messages triggering replies
