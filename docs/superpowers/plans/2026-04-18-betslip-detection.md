# Bet Slip Detection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restrict auto-detection of bet slip images to the designated placer only, and add a `!slip` reply command so anyone can confirm a delegated bet slip.

**Architecture:** Three-layer change — bridge passes quoted message ID on replies and caches the quoted media; `app.py` webhook restricts the existing `has_media` auto-detection path to the designated placer only; a new `!slip` command handler fetches the quoted image and confirms the slip without an LLM gate (human confirmed it).

**Tech Stack:** Python/Flask (`src/app.py`), Node.js (`bridge/index.js`), pytest

---

## File map

| File | Change |
|---|---|
| `bridge/index.js` | Add `quoted_message_id` to payload; cache quoted media on reply messages |
| `src/app.py` | Restrict `has_media` auto-detection to designated placer; pass `quoted_message_id` into `parsed` dict; add `!slip` routing + `_cmd_slip` handler |
| `tests/test_app_cumulative_picks.py` | Add regression test for non-placer image being ignored; add tests for `!slip` happy path and all guard cases |

---

## Task 1: Restrict auto-detection to designated placer

**Files:**
- Modify: `src/app.py:132-134`
- Modify: `tests/test_app_cumulative_picks.py`

### Background

Currently `app.py` lines 132-134:
```python
# Screenshot from any known player = potential bet slip (LLM validates before committing)
if not reply and has_media:
    reply = _handle_placer_bet_confirmation(sender, sender_phone, body, message_id=message_id, from_image=True)
```

This fires for any known player. Change: only fire if the sender IS the designated placer.

- [ ] **Step 1: Write the failing test**

Add to `TestBetPlacementConfirmation` in `tests/test_app_cumulative_picks.py`:

```python
def test_non_placer_image_silently_ignored(self, test_db, monkeypatch):
    """A non-placer sending an image must not trigger bet slip confirmation."""
    _seed_player_emojis()
    monkeypatch.setattr("src.app.is_within_submission_window", lambda group_id="default": True)
    monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", "test-group@g.us")
    monkeypatch.setattr(
        "src.services.bet_slip_service.fetch_image_from_bridge",
        lambda message_id: {"data": "fake_b64", "mimetype": "image/jpeg"},
    )
    monkeypatch.setattr(
        "src.llm_client.read_bet_slip",
        lambda data, mimetype: {"stake": 20.0, "total_odds": 3.0, "potential_return": 60.0, "legs": []},
    )

    from src.app import create_app
    from src.services.week_service import get_or_create_current_week
    from src.services.rotation_service import get_next_placer
    from src.services.pick_service import submit_pick
    from src.services.player_service import get_all_players
    from src.db import get_db

    app = create_app()
    client = app.test_client()

    week = get_or_create_current_week(group_id="test-group@g.us")
    players = get_all_players()
    for p in players:
        submit_pick(p["id"], week["id"], f"{p['nickname']} pick 2/1", 3.0, "2/1", "win")

    placer = get_next_placer()
    assert placer["nickname"] == "Kev"

    # Aidan sends an image — he is NOT the designated placer
    resp = client.post(
        "/webhook",
        json={
            "sender": "Aidan",
            "sender_phone": "",
            "body": "",
            "group_id": "test-group@g.us",
            "has_media": True,
            "message_id": "msg-aidan-img",
        },
        content_type="application/json",
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("action") != "replied"

    # placer_id must remain None — rotation must not advance
    conn = get_db()
    row = conn.execute("SELECT placer_id FROM weeks WHERE id = ?", (week["id"],)).fetchone()
    conn.close()
    assert row["placer_id"] is None
```

- [ ] **Step 2: Run test to verify it fails**

```
python3 -m pytest tests/test_app_cumulative_picks.py::TestBetPlacementConfirmation::test_non_placer_image_silently_ignored -v
```

Expected: FAIL (currently any known player triggers confirmation)

- [ ] **Step 3: Implement the placer check**

In `src/app.py`, replace lines 132-134:

```python
# Screenshot from any known player = potential bet slip (LLM validates before committing)
if not reply and has_media:
    reply = _handle_placer_bet_confirmation(sender, sender_phone, body, message_id=message_id, from_image=True)
```

with:

```python
# Screenshot fires auto-detection only when the sender IS the designated placer.
# Delegated slips use the explicit !slip reply command instead.
if not reply and has_media:
    _next_placer = get_next_placer()
    _sender_player = lookup_player(sender_phone=sender_phone, sender_name=sender)
    if _next_placer and _sender_player and _sender_player["id"] == _next_placer["id"]:
        reply = _handle_placer_bet_confirmation(sender, sender_phone, body, message_id=message_id, from_image=True)
```

- [ ] **Step 4: Run new test + full suite**

```
python3 -m pytest tests/test_app_cumulative_picks.py::TestBetPlacementConfirmation::test_non_placer_image_silently_ignored -v
python3 -m pytest tests/ -v
```

Expected: all pass. `test_placer_screenshot_records_bet_placed` still passes because Kevin IS the next placer in that test.

- [ ] **Step 5: Commit**

```bash
git add src/app.py tests/test_app_cumulative_picks.py
git commit -m "fix: restrict bet slip auto-detection to designated placer only"
```

---

## Task 2: Bridge — pass quoted_message_id and cache quoted media

**Files:**
- Modify: `bridge/index.js:265-273`

No Python unit tests for this task — verify manually by checking bridge logs.

- [ ] **Step 1: Add quoted message handling to bridge**

In `bridge/index.js`, after the media cache block (the `if (message.hasMedia)` block ending around line 273), add:

```javascript
    // When this message is a reply, pass the quoted message ID to Flask.
    // If the quoted message contains media, cache it now so Flask can
    // pull it via /media even if the original message has been evicted.
    if (message.hasQuotedMsg) {
      try {
        const quoted = await message.getQuotedMessage();
        payload.quoted_message_id = quoted.id._serialized;
        if (quoted.hasMedia) {
          recentMessages.set(quoted.id._serialized, quoted);
          if (recentMessages.size > 50) {
            recentMessages.delete(recentMessages.keys().next().value);
          }
        }
      } catch (err) {
        console.error("Failed to resolve quoted message:", err.message);
      }
    }
```

The full updated block (lines 267-283 after edit) should look like:

```javascript
    // Cache media messages so Flask can pull images on demand via /media
    if (message.hasMedia) {
      recentMessages.set(payload.message_id, message);
      if (recentMessages.size > 50) {
        recentMessages.delete(recentMessages.keys().next().value);
      }
    }

    // When this message is a reply, pass the quoted message ID to Flask.
    // If the quoted message contains media, cache it now so Flask can
    // pull it via /media even if the original message has been evicted.
    if (message.hasQuotedMsg) {
      try {
        const quoted = await message.getQuotedMessage();
        payload.quoted_message_id = quoted.id._serialized;
        if (quoted.hasMedia) {
          recentMessages.set(quoted.id._serialized, quoted);
          if (recentMessages.size > 50) {
            recentMessages.delete(recentMessages.keys().next().value);
          }
        }
      } catch (err) {
        console.error("Failed to resolve quoted message:", err.message);
      }
    }
```

- [ ] **Step 2: Verify manually on shadow group**

Deploy bridge to server, send a reply to an image in the shadow group, confirm that `quoted_message_id` appears in Flask logs:

```
pm2 logs punter-flask --lines 20 --nostream
```

Expected: log line showing `Message from <sender>: !slip` with the quoted_message_id arriving in the webhook payload.

- [ ] **Step 3: Commit**

```bash
git add bridge/index.js
git commit -m "feat: pass quoted_message_id to Flask when message is a reply to media"
```

---

## Task 3: Pass quoted_message_id into the parsed dict

**Files:**
- Modify: `src/app.py:62-135`

`handle_command` receives only the `parsed` dict. `quoted_message_id` comes from the raw webhook payload. This task threads it through so `_cmd_slip` can access it.

- [ ] **Step 1: Extract quoted_message_id in webhook()**

In `src/app.py`, the `webhook()` function currently extracts these fields from `data` (lines 69-74):

```python
sender = data.get("sender", "")
sender_phone = data.get("sender_phone", "")
body = data.get("body", "")
group_id = data.get("group_id", "")
has_media = data.get("has_media", False)
message_id = data.get("message_id", "")
```

Add one more line immediately after:

```python
quoted_message_id = data.get("quoted_message_id", "")
```

- [ ] **Step 2: Add quoted_message_id to parsed dict before handle_command — path 1**

Path 1 is the `body.strip().startswith("!")` block (lines 99-106). Currently:

```python
    if body.strip().startswith("!"):
        parsed = parse_message(body, sender, sender_phone)
        if parsed["type"] == "command":
            reply = handle_command(parsed)
```

Change to:

```python
    if body.strip().startswith("!"):
        parsed = parse_message(body, sender, sender_phone)
        if parsed["type"] == "command":
            parsed["quoted_message_id"] = quoted_message_id
            reply = handle_command(parsed)
```

- [ ] **Step 3: Add quoted_message_id to parsed dict before handle_command — path 2**

Path 2 is the fallback `parse_message` block (lines 121-130). Currently:

```python
            if parsed["type"] == "command":
                reply = handle_command(parsed)
```

Change to:

```python
            if parsed["type"] == "command":
                parsed["quoted_message_id"] = quoted_message_id
                reply = handle_command(parsed)
```

- [ ] **Step 4: Run full test suite**

```
python3 -m pytest tests/ -v
```

Expected: all pass (no behaviour change yet — `quoted_message_id` is in `parsed` but nothing reads it).

- [ ] **Step 5: Commit**

```bash
git add src/app.py
git commit -m "feat: thread quoted_message_id through webhook into parsed command dict"
```

---

## Task 4: `!slip` command handler

**Files:**
- Modify: `src/app.py` — add `_cmd_slip` and route it in `handle_command`
- Modify: `tests/test_app_cumulative_picks.py` — add tests

- [ ] **Step 1: Write the failing tests**

Add a new test class to `tests/test_app_cumulative_picks.py`:

```python
class TestSlipCommand:
    """Tests for !slip — explicit bet slip confirmation via reply to image."""

    GROUP_ID = "test-group@g.us"

    def _setup(self, monkeypatch):
        from src.app import create_app
        from src.services.week_service import get_or_create_current_week
        from src.services.pick_service import submit_pick
        from src.services.player_service import get_all_players

        _seed_player_emojis()
        monkeypatch.setattr("src.app.is_within_submission_window", lambda group_id="default": True)
        monkeypatch.setattr("src.config.Config.GROUP_CHAT_ID", self.GROUP_ID)
        monkeypatch.setattr("src.config.Config.GROUP_CHAT_IDS", [])
        monkeypatch.setattr("src.app.send_message", lambda chat_id, text: None)

        app = create_app()
        client = app.test_client()

        week = get_or_create_current_week(group_id=self.GROUP_ID)
        players = get_all_players()
        for p in players:
            submit_pick(p["id"], week["id"], f"{p['nickname']} pick 2/1", 3.0, "2/1", "win")

        return app, client, week, players

    def test_slip_command_confirms_bet_and_advances_rotation(self, test_db, monkeypatch):
        """Any known player replying to an image with !slip confirms the bet slip."""
        app, client, week, players = self._setup(monkeypatch)

        monkeypatch.setattr(
            "src.services.bet_slip_service.fetch_image_from_bridge",
            lambda mid: {"data": "fake_b64", "mimetype": "image/jpeg"},
        )
        monkeypatch.setattr(
            "src.app.llm_client.read_bet_slip",
            lambda data, mime: {
                "stake": 20.0,
                "total_odds": 5.0,
                "potential_return": 100.0,
                "legs": [],
            },
        )

        # Aidan (not the designated placer) uses !slip
        resp = client.post(
            "/webhook",
            json={
                "sender": "Aidan",
                "sender_phone": "",
                "body": "!slip",
                "group_id": self.GROUP_ID,
                "has_media": False,
                "message_id": "",
                "quoted_message_id": "quoted-img-456",
            },
            content_type="application/json",
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["action"] == "replied"
        assert "Bet slip received" in data["reply"]

        from src.db import get_db
        conn = get_db()
        row = conn.execute("SELECT placer_id FROM weeks WHERE id = ?", (week["id"],)).fetchone()
        slip = conn.execute("SELECT stake FROM bet_slips WHERE week_id = ?", (week["id"],)).fetchone()
        conn.close()
        assert row["placer_id"] is not None
        assert slip is not None
        assert slip["stake"] == 20.0

    def test_slip_without_quoted_message_returns_error(self, test_db, monkeypatch):
        """!slip without a quoted message returns a user-visible error."""
        app, client, week, players = self._setup(monkeypatch)

        resp = client.post(
            "/webhook",
            json={
                "sender": "Aidan",
                "sender_phone": "",
                "body": "!slip",
                "group_id": self.GROUP_ID,
                "has_media": False,
                "message_id": "",
            },
            content_type="application/json",
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["action"] == "replied"
        assert "Reply to the bet slip image" in data["reply"]

    def test_slip_when_image_not_in_cache_returns_error(self, test_db, monkeypatch):
        """!slip where the quoted image can't be fetched returns a user-visible error."""
        app, client, week, players = self._setup(monkeypatch)

        monkeypatch.setattr(
            "src.services.bet_slip_service.fetch_image_from_bridge",
            lambda mid: None,
        )

        resp = client.post(
            "/webhook",
            json={
                "sender": "Aidan",
                "sender_phone": "",
                "body": "!slip",
                "group_id": self.GROUP_ID,
                "has_media": False,
                "message_id": "",
                "quoted_message_id": "evicted-msg-id",
            },
            content_type="application/json",
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["action"] == "replied"
        assert "couldn't retrieve" in data["reply"].lower()

    def test_slip_when_placer_already_confirmed_returns_error(self, test_db, monkeypatch):
        """!slip after bet is already confirmed returns a user-visible error."""
        app, client, week, players = self._setup(monkeypatch)

        # Manually set placer_id to simulate already-confirmed
        from src.db import get_db
        conn = get_db()
        conn.execute("UPDATE weeks SET placer_id = ? WHERE id = ?", (players[0]["id"], week["id"]))
        conn.commit()
        conn.close()

        resp = client.post(
            "/webhook",
            json={
                "sender": "Aidan",
                "sender_phone": "",
                "body": "!slip",
                "group_id": self.GROUP_ID,
                "has_media": False,
                "message_id": "",
                "quoted_message_id": "any-msg-id",
            },
            content_type="application/json",
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["action"] == "replied"
        assert "already confirmed" in data["reply"].lower()

    def test_slip_unknown_sender_silently_ignored(self, test_db, monkeypatch):
        """!slip from an unrecognised sender produces no reply."""
        app, client, week, players = self._setup(monkeypatch)

        resp = client.post(
            "/webhook",
            json={
                "sender": "RandomStranger",
                "sender_phone": "99999999999@c.us",
                "body": "!slip",
                "group_id": self.GROUP_ID,
                "has_media": False,
                "message_id": "",
                "quoted_message_id": "some-msg-id",
            },
            content_type="application/json",
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("action") != "replied"
```

- [ ] **Step 2: Run tests to verify they all fail**

```
python3 -m pytest tests/test_app_cumulative_picks.py::TestSlipCommand -v
```

Expected: all FAIL with "I don't recognise the command !slip"

- [ ] **Step 3: Add `_cmd_slip` to `src/app.py`**

Add this function after `_cmd_removepick` (around line 291):

```python
def _cmd_slip(parsed):
    """!slip (as a reply to an image) — any known player confirms a delegated bet slip.
    Unlike auto-detection, the LLM result does not gate the confirmation — a human
    explicitly tagged the image, so rotation always advances. LLM extraction is
    best-effort for confirmed_odds only.
    """
    from src.services.bet_slip_service import (
        fetch_image_from_bridge, record_bet_slip, match_legs_to_picks, update_confirmed_odds,
    )

    quoted_message_id = parsed.get("quoted_message_id", "")
    if not quoted_message_id:
        return "Reply to the bet slip image with !slip"

    week = get_current_week(group_id=_get_group_id())
    if not week:
        return None

    if week.get("placer_id"):
        return "Bet slip already confirmed for this week"

    if not all_picks_in(week["id"]):
        return "Still waiting for all picks before recording the slip"

    sender_player = lookup_player(sender_phone=parsed.get("sender_phone", ""), sender_name=parsed["sender"])
    if not sender_player:
        return None

    next_placer = get_next_placer()
    if not next_placer:
        return None

    image = fetch_image_from_bridge(quoted_message_id)
    if not image:
        return "Couldn't retrieve the image — make sure you're replying directly to the bet slip image"

    extracted = llm_client.read_bet_slip(image["data"], image.get("mimetype", "image/jpeg")) or {}

    advance_rotation(week["id"], next_placer["id"])
    picks = get_picks_for_week(week["id"])
    try:
        record_bet_slip(week["id"], next_placer["id"], extracted)
        legs = extracted.get("legs") or []
        if legs and picks:
            matched = match_legs_to_picks(legs, picks)
            if matched:
                update_confirmed_odds(matched)
    except Exception:
        logger.exception("Failed to persist bet slip data via !slip (week_id=%d)", week["id"])

    return butler.bet_slip_received(next_placer)
```

- [ ] **Step 4: Add `!slip` routing in `handle_command`**

In `handle_command` (around line 200 where `!removepick` is routed), add:

```python
    if command == "slip":
        return _cmd_slip(parsed)
```

- [ ] **Step 5: Run new tests**

```
python3 -m pytest tests/test_app_cumulative_picks.py::TestSlipCommand -v
```

Expected: all pass

- [ ] **Step 6: Run full test suite**

```
python3 -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add src/app.py tests/test_app_cumulative_picks.py
git commit -m "feat: add !slip command for explicit delegated bet slip confirmation"
```

---

## Deploy

- [ ] **Deploy to server**

```bash
git push
ssh -i ~/Documents/Oracle/ssh-key-2026-02-18.key ubuntu@193.123.179.96 \
  "cd ~/punter-bot && git pull && pm2 restart all --update-env"
```

- [ ] **Smoke test on shadow group**

1. Submit picks for all players in shadow group
2. Have a non-placer send an unrelated image → confirm no response from bot
3. Have anyone reply to a bet slip image with `!slip` → confirm bot responds with "Bet slip received"
