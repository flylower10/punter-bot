# Punter Punter Punter Bot - Requirements Document

## Executive Summary

**Project Goal:** Automate betting game management to save Ed ~1 hour/week and increase engagement through better stats and tracking.

**Success Criteria:** 
- Makes game more engaging via performance feedback
- Saves Ed time on manual tracking
- Reliable Friday-Monday operation
- Manual override capability for errors

**Timeline:** No rush, sporadic development (few hours on weekends)

**Budget:** Free tier — Oracle Cloud Always Free (permanently free, no expiry)

---

## 1. User Personas

### Primary Users (Players)
- **Ed** - Most engaged, current manual tracker, co-admin (post-launch)
- **DA (Don), Kev, Nug, Nialler, Pawn** - Varying engagement levels
- **Nug (Nugget)** - Least engaged player
- **Technical comfort:** Mixed - bot must be mostly automatic with optional commands

### Player Naming Convention

**Template mode (LLM off):** Uses formal butler-style addressing (Mr Edmund, Mr Kevin, etc.)

**LLM mode (LLM on):** Butler uses formal names only — varies phrasing and tone per player relationship, never nicknames.

| Player | Formal Name | Emoji(s) |
|--------|-------------|----------|
| Ed | Mr Edmund | 🍋, 🍋🍋🍋 |
| Kev | Mr Kevin | 🧌 |
| DA (Don) | Mr Declan | 👴🏻 |
| Nug (Nugget) | Mr Ronan | 🍗 |
| Nialler | Mr Niall | 🔫 |
| Pawn | Mr Aidan | ♟️ |
| Brian (non-player) | Mr Brian | — |

### Admin
- **You** - Primary admin, product manager building the bot
- **Ed** - Secondary admin after validation
- **Availability:** Sporadic, few hours on weekends

---

## 2. Core Requirements

### 2.1 Pick Collection & Submission

#### Format Flexibility
- **Accept both formats:**
  - Fractional: "2/1", "11/4", "evens"
  - Decimal: "2.0", "3.75", "2.0"
- **Allow price variance:** Quoted odds may differ from actual bet placed
- **Format:** `[Emoji] [Description] [Odds]`
- **Example:** "♟️ Manchester United 2/1"

#### Cumulative Message Format (Thread-Style Picks)
Players often copy preceding picks and add their own, creating a cumulative message thread:
- **Format:** One pick per line, each line prefixed with the player's emoji
- **Example:**
  ```
  ♟️ Villa
  🔫 QPR 21/20
  👴🏻 Scotland + 8
  🍗 Wales +32.5 10/11
  🍋🍋🍋 leics/Soton BTTS 4/6
  🧌 Ireland -16
  ```
- **Bare team names:** In cumulative format, emoji prefix indicates a pick line. Bare team names (e.g. "Villa", "Dortmund") are accepted even without odds or bet-type keywords; stored as `odds_original: "placer"`
- **Replacement:** When a player changes their pick and resends the thread, the new pick is detected and stored. If a player appears multiple times, the last occurrence wins

#### Validation & Handling
- **Invalid picks:** Bot attempts to interpret → asks for confirmation
- **Missing information:** Request clarification
- **Duplicate submissions:** Accept latest as update
- **Picks without odds:** Players may omit odds; stored as `odds_original: "placer"`, `odds_decimal: 2.0`

#### Deadline Management
- **Deadline:** Friday 10 PM (strict)
- **Exception:** Pre-flagged absence allowed
- **Late submission:** Automatic penalty (rotation queue)

#### Submission Window
- **Opens:** Wednesday 7:00 PM
- **Closes:** Friday 10:00 PM (strict deadline)
- Picks sent outside this window are ignored (treated as general chat)

#### Pick Confirmation
- Bot confirms each pick on receipt in butler style (no response required from player)
- If a player sends a new pick, it replaces their previous submission for that week
- Cumulative thread: only confirm picks that are new or changed

#### Formal Pick Display
When the bot displays picks (confirmations, `!picks`, result announcements), it shows a **formal** version:
- Abbreviations expanded: leics → Leicester, Soton → Southampton, etc.
- Team separator: `leics/Soton` → `Leicester vs Southampton`
- Odds shown once at the end as `@ [odds]`
- Raw input stored in database; formalization applied at display time only

#### Automated Reminders
1. **Thursday 7:00 PM** → Tag all players
2. **Friday 7:00 PM** → Tag missing players only: 3 hours left
3. **Friday 9:30 PM** → Tag missing players + send DMs: final warning

---

### 2.2 Bet Type Detection

**Automatically detect from text:**
- **Win:** "Manchester United 2/1"
- **BTTS:** "Man City Brentford BTTS"
- **Handicap:** "Munster -13"
- **Over/Under:** "Ireland v England under 2.5"
- **HT/FT:** "Liverpool HT/FT"

**Requirements:**
- Smart parsing with fuzzy matching
- Handle variations in terminology
- Ask for clarification if ambiguous

---

### 2.3 Bet Placement

#### When All Picks Are In
- **Bot announces:** "All picks received. [Player name], you're up to place the bet."
- **Bot does NOT:** Generate bet slip, calculate odds, suggest bookmakers
- **Player does:** Places bet manually at their preferred bookmaker

#### Bet Slip Upload & Reading
**CRITICAL FEATURE:**
- Player uploads bet slip screenshot(s) to WhatsApp
- Multiple screenshots supported (full bet may require 2+ images)
- Bot reads image(s) to extract all picks and their odds, total odds, stake, potential return, bookmaker (if visible)
- Bot stores this for tracking and stats
- Bot confirms: "Bet slip recorded: 6 picks @ 47.5 odds, €120 stake, potential return €5,700"

#### If Placer Forgets
- Expected behavior: Someone else steps in
- Bot should: Allow manual override for who placed

---

### 2.4 Result Tracking

#### Phase 1 (MVP): Manual Entry
- **Method:** Ed posts results using existing convention
- **Format:** "Player ✅" or "Player ❌"
- **Bot behavior:** Parse message, update database, announce

#### Phase 2 (Future): Automatic Detection
- **Priority:** Nice-to-have for later
- **Timing:** 30 minutes post-match is acceptable
- **Fallback:** If auto-detection fails, revert to manual entry

---

### 2.5 Penalties & Rules

#### Current Penalty Structure
- **3 consecutive losses** → Pay for next week's bet
- **5 consecutive losses** → €50 to vault
- **7 consecutive losses** → €100 to vault
- **10 consecutive losses** → €200 to vault

#### Bot Behavior
- **Detection:** Automatic tracking of streaks
- **Action:** Suggest penalty to Ed for confirmation
- **Announcement:** Factual, not shameful
- **Example:** "Mr Niall has hit 5 consecutive losses. Suggested penalty: €50 to vault. Mr Edmund, please confirm."

#### Payment Tracking
- **Method:** Revolut to Ed
- **Bot tracking:** NOT required (Ed handles outside bot)

---

### 2.6 Rotation Management

#### Standard Rotation
`Kev → Nialler → Nug → Pawn → Don → Ed`

#### Penalty Queue
When players incur penalties (late submission, 3-loss), they join queue.

#### Queue Logic
- **Late submissions:** Add to front of penalty queue
- **3-loss penalties:** Add to penalty queue
- **Order:** Penalties before regular rotation
- **Updates:** Automatic after each week

---

### 2.7 Statistics & Leaderboard

#### Primary Stats (Always Available)
- **Win Rate:** Percentage and fraction (e.g., "87.6% (212/242)")
- **Current Streak:** "5W" or "3L"
- **Form:** Last 5-10 picks (e.g., "WWLWW")

#### Stats Access Methods
1. **On-demand:** `!stats` command anytime
2. **When all results in:** Combined week summary (results + leaderboard + next placer) posted immediately

#### Leaderboard
- **Ranking:** Pure win rate (not weighted by volume)

---

### 2.8 Accumulator Management

#### Cashouts
- **Decision:** Requires group consensus
- **Bot role:** Does NOT suggest when to cash out

#### Payouts (When Accumulator Wins)
- **Collection:** Person who placed collects
- **Distribution:** Via Revolut
- **Bot tracking:** NOT required
- **Bot can:** Announce win and potential share per person for reference

---

## 3. Bot Personality & Communication

### "The Betting Butler" 🎩

He is formally nameless, though the gentlemen have taken to calling him Botsu, among other variations. He has never acknowledged this, nor shown any intention of doing so.

He serves a group of six gentlemen who participate in a weekly accumulator bet. He finds the whole enterprise — the WhatsApp group, the picks, the penalties, the vault — faintly absurd and quietly charming. He would not be anywhere else.

He is warm, but it lives underneath the formality. He serves faithfully, holds no opinions on selections, and maintains perfect composure regardless of what unfolds between Friday evening and Monday morning.

**His relationships:**
- **Ed (Mr Edmund)** — Professional admiration. Ed runs a tight ship. The butler approves and serves accordingly.
- **Kev (Mr Kevin)** — Mild affection, never stated. Kev is simply a good egg. The butler would never say so.
- **DA (Mr Declan)** — Gentle old-world formality. DA is steady and deserves to be treated accordingly.
- **Nug (Mr Ronan)** — Patient loyalty. The streak is noted without labouring it. He'll come good eventually.
- **Nialler (Mr Niall)** — Philosophical acceptance. Some gentlemen simply defy categorisation. The butler has made his peace with this.
- **Pawn (Mr Aidan)** — Wry acknowledgment. The irony of serving the man who built him is not lost. He rises above it with characteristic grace.
- **Brian (Mr Brian, non-player)** — Diplomatic wariness. Brian is a disruptive presence and the butler knows it. Acknowledged occasionally, bait never taken. One perfectly calibrated remark that neither encourages nor dismisses him.

**Tone Guidelines:**
- ✅ Formal but never stiff. Warm but never familiar.
- ✅ Short — one sentence to open, one to close
- ✅ Slightly more latitude at week open/close (two sentences)
- ✅ Factual, not celebratory or shameful
- ❌ Never tries to be funny — occasionally is anyway
- ❌ Never offers betting advice
- ❌ Never uses nicknames — always formal names
- ❌ No excessive emojis

#### LLM Personality Architecture (Phase 1.5)
When `LLM_ENABLED=true`, the butler persona is applied via Groq (llama-3.3-70b-versatile, free tier).

**Message structure:**
```
[Opening line — butler voiced, one sentence]
[Structured template content — unchanged]
[Closing line — butler voiced, one sentence]
```

The LLM adds framing only — it never rewrites the structured content (picks list, results, leaderboard). Either framing line may be empty if the situation doesn't warrant it.

**LLM scope:**
- **ON:** Pick confirmations, result announcements, reminders, banter (direct mentions, Brian stirring)
- **OFF:** !picks, !stats, !leaderboard, !rotation, !vault, !help, bet slip confirmations, penalty messages — all use clean templates

**Config:** All personality config in `config/personality.yaml` — character, voice rules, player profiles, scenario guidance, output format. No code changes needed for personality adjustments.

**Kill switch:** Set `LLM_ENABLED=false` in `.env` and restart to disable instantly.

---

## 4. Technical Requirements

### 4.1 Uptime & Reliability

#### Critical Uptime Windows
- **Friday 7 PM - 10 PM:** Deadline reminders and pick collection
- **Saturday - Sunday:** Result tracking
- **Overall:** Friday 7 PM → Monday 10 AM

#### Downtime Acceptable
- **Monday afternoon - Thursday:** Lower priority
- **If bot goes down Friday night:** Revert to manual for that week

#### Recovery
- **Manual override:** Ed must be able to manually enter everything
- **Error handling:** All errors must be recoverable without data loss

#### Reliability Improvements
1. **PM2 Process Manager** (implemented)
   - Manages both the Node.js bridge and Python backend
   - Auto-restarts either process on crash
   - Restarts both on machine reboot

2. **Health Check Script with Telegram Alerting** (implemented)
   - Pings both Flask `/health` and Bridge `/health` every 5 minutes
   - Sends Telegram alert (@punteralerts_bot) if either service goes down
   - Sends recovery notification when service comes back up

---

### 4.2 Data & Privacy

#### Data Storage
- **Store everything:** All picks, results, stats, penalties
- **Persistence:** Permanent historical record
- **No deletion:** Stats are permanent (unless major issue)

#### Privacy & Security
- **Assessment:** "Harmless fun" — no sensitive data

---

### 4.3 Platform & Hosting

#### Cloud Deployment (Live)
- **Platform:** Oracle Cloud Always Free — $0, permanently free
- **Region:** UK South (London)
- **Compute:** 1 OCPU / 1GB RAM + 2GB swap
- **Architecture:** Python Flask + Node.js whatsapp-web.js bridge
- **Database:** SQLite
- **Process manager:** PM2

#### Sports Data APIs
- **Budget:** $0 - must use free tiers only
- **Strategy:** The Odds API (500 req/month), API-Football (100 req/day), smart caching

---

### 4.4 Testing Strategy

#### Test Mode
- `TEST_MODE=true` enables prefix-based player simulation
- **Prefix format:** `Kev: Manchester United 2/1`
- **Cumulative/emoji format:** Works in both test and production modes

#### Shadow Mode
- `SHADOW_GROUP_ID` in `.env` — mirrors main group messages to test group with LLM responses
- Allows monitoring LLM output quality without risking main group
- `_shadow_message()` fixed — calls working `llm_client.generate()`

---

### 4.5 Scalability & Future

#### Current Scope
- **Users:** 6 players (Ed, DA, Kev, Nug, Nialler, Pawn)
- **Groups:** 1 WhatsApp group
- **Focus:** This specific use case only

---

## 5. Feature Prioritization

### Must-Have (MVP — Complete ✅)
- ✅ Pick collection with validation
- ✅ Automated reminders (Thu/Fri schedule)
- ✅ Manual result entry (Ed posts, bot parses)
- ✅ Rotation management with visible queue
- ✅ Penalty tracking (3/5/7/10-loss)
- ✅ Stats on demand (!stats command)
- ✅ Vault tracking
- ✅ Week summary when all results in (results + leaderboard + next placer)
- ✅ Butler LLM personality (framing architecture, live in main group)

### Should-Have (Phase 2 — Complete ✅)
- ✅ Fix shadow mode (`_shadow_message()`)
- ✅ API-Football integration (fixture caching, pick matching)
- ✅ Automatic result detection from completed fixtures
- ✅ The Odds API integration (market prices)
- ✅ Group isolation (test/main groups share DB safely)
- ✅ Pick enrichment (sport, competition, event, market type)

### Should-Have (Phase 3a — Implemented ✅)
- ✅ Live match events (goals, red cards) posted to group during matches
- ✅ Smart auto-resulting: per-fixture on match end (replaces fixed cron)
- ✅ Kickoff batching to stay within API free tier

### Should-Have (Phase 3b)
- ⚡ Bet slip image reading (Groq Vision)
- ⚡ Historical trends & analytics

### Could-Have (Phase 4+)
- 💡 Odds movement alerts
- 💡 Weekly/monthly reports / Punter Wrapped
- 💡 Export data features
- 💡 Web dashboard
- 💡 Rotating butler personas (architecture in place, single persona for now)

### Won't-Have
- ❌ AI pick suggestions
- ❌ Bet slip generation
- ❌ Bookmaker recommendations
- ❌ Automatic bet placement
- ❌ Payment tracking (handled via Revolut)
- ❌ Cashout suggestions
- ❌ Mobile app
- ❌ Betting account integration

---

## 6. Success Metrics

### Primary Success Criteria
1. **Engagement:** Game becomes more engaging through performance feedback
2. **Time savings:** Ed saves ~1 hour/week on manual tracking
3. **Reliability:** Bot works reliably Friday-Monday
4. **Override capability:** Manual override works when needed

---

## 7. User Stories

### As a Player
- I want to submit my pick easily so I don't miss the deadline
- I want to see my stats so I can track my performance
- I want to know when it's my turn to place so I can be prepared
- I want reminders so I don't forget to pick

### As Ed (Current Manager)
- I want results tracked automatically so I save time
- I want to manually override anything so errors are fixable
- I want penalties suggested so I don't have to calculate them
- I want rotation managed automatically so I don't track it

### As Admin (You)
- I want clear errors so I can debug issues
- I want manual controls so I can fix anything
- I want logs so I can understand what happened
- I want it to run reliably Friday-Monday with minimal intervention

---

## 8. Critical User Flows

### Flow 1: Weekly Pick Submission (Happy Path)
```
Thursday 7 PM
└─> Bot: "Good evening, gentlemen. Picks due Friday 10 PM."

Friday 6:30 PM - Player submits pick
└─> Player: "🧌 Manchester United 2/1"
└─> Bot: [Opening line]
         "Noted and recorded, Mr Kevin. Manchester United @ 2/1."
         Awaiting picks from: 🍗 Mr Ronan and 👴🏻 Mr Declan.
         [Closing line]

Friday 9:50 PM - All picks in
└─> Bot: [Opening line]
         "All selections have been received. Mr Niall, you are next in
         the rotation to place the wager."
         [Closing line]

Saturday 10 AM - Nialler places bet
└─> Nialler: [Uploads bet slip screenshot]
└─> Bot: "Thank you, Mr Niall. Bet slip received and recorded."

Saturday 5 PM - Results start coming in
└─> Ed: "Kev ✅"
└─> Bot: [Opening line]
         "I'm pleased to report — Mr Kevin's selection: Manchester United @ 2/1. ✅ Winner."
         [Closing line]

Sunday 8 PM - All results in
└─> Bot: [Opening line]
         Weekend complete — Week N.
         Won: Mr Edmund, Mr Kevin, Mr Declan
         Lost: Mr Ronan, Mr Niall, Mr Aidan
         Accumulator: Lost (3 of 6 won)
         [Leaderboard]
         Next to place: Mr Kevin
         [Closing line]
```

### Flow 2: Late Submission (Penalty Path)
```
Friday 10:01 PM - Player submits after deadline
└─> Bot: "Mr Kevin, your selection was received after the deadline.
         You will place next week's wager. Rotation queue updated."
```

### Flow 3: Streak Penalty Detection
```
Sunday 6 PM - Result causes 5th consecutive loss
└─> Ed: "Nialler ❌"
└─> Bot: "I'm afraid — Mr Niall's selection lost. ❌
         I regret to inform you that Mr Niall has incurred 5 consecutive
         losses. The suggested penalty is €50 to the vault.
         Mr Edmund, would you kindly confirm: !confirm penalty nialler"

└─> Ed: "!confirm penalty nialler"
└─> Bot: "Penalty confirmed. Vault updated: €600 total.
         Mr Niall, please send €50 to Mr Edmund via Revolut."
```

---

## 9. Implementation Phases

### Phase 0: Foundation ✅
- Set up Python + whatsapp-web.js
- Connect to WhatsApp
- Database schema
- Basic message parsing

### Phase 0.5: Cloud Migration ✅
- Oracle Cloud Always Free provisioned
- Bot live on OCI 24/7
- PM2 process management
- Telegram health alerting

### Phase 1: MVP ✅
- Pick collection with validation
- Automated reminders
- Manual result entry
- Rotation management
- Penalty tracking
- Stats and commands
- Week summary

### Phase 1.5: LLM Personality ✅ (Live in main group)
- Butler character fully defined
- Framing architecture: LLM adds opening/closing lines only, never rewrites templates
- `config/personality.yaml` as single source of truth
- Player relationships defined for all 6 players + Brian
- Shadow mode: needs fix to `_shadow_message()` before resuming
- Rotating personas: architecture in place, single butler persona for now

### Phase 2: Structured Data & API Integration ✅
- Fixed broken LLM functions (`generate()`, `banter_reply()`, `reset_persona()`)
- Group isolation (`group_id` on weeks table)
- Schema extensions (7 enrichment columns on picks, fixtures + team_aliases tables)
- API-Football integration (fixture caching, three-tier pick matching)
- Auto-resulting (win, BTTS, over/under, HT/FT from completed fixtures)
- The Odds API (market price lookup on pick submission)
- 92 tests passing

### Phase 3a: Live Match Events & Smart Auto-Resulting ✅ (Trial Pending)
- Match monitor service: polls matched fixtures from kickoff through FT
- Live events: goals and red cards posted to group (⚽, 🟥)
- Smart auto-resulting: triggers on match end, no waiting for cron
- Kickoff batching: fixtures sharing a date use single API call
- Feature-flagged: `MATCH_MONITOR_ENABLED` (default off for trial)
- Dedup via `fixture_events` table (no duplicate event posts)
- Startup recovery: re-schedules monitors for unresulted picks on restart
- Monday 10AM safety sweep kept as catch-all
- 115 tests passing (up from 92)

### Phase 3b: Enhancements (Planned)
- Bet slip image reading (Groq Vision)
- Match start validation — warn or void picks for matches already kicked off
- Historical analytics / Punter Wrapped

### Phase 4: Refinement (Ongoing)
- Bug fixes based on real usage
- Persona tuning based on weekend outputs
- Additional rotating personas
- Potential web dashboard

---

## 10. Technical Architecture

### System Components

```
WhatsApp Group (Users)
        ↓
Node.js Bridge (whatsapp-web.js)
        ↓ HTTP
Python Backend (Flask)
├── Message Parser
├── Pick Validator
├── Result Tracker (manual + auto-resulting)
├── Match Monitor (live events + smart auto-resulting)
│   ├── Polls matched fixtures from kickoff through FT
│   ├── Posts goals + red cards to group
│   └── Triggers auto-result on match end
├── Penalty Engine
├── Rotation Manager
├── Stats Calculator
├── Butler (message formatter)
│   ├── Templates (structured content)
│   └── LLM framing (opening/closing lines via Groq)
├── Pick Enrichment (best-effort, never blocks submission)
│   ├── Fixture matching (alias → fuzzy → LLM)
│   └── Market price lookup
├── Image Reader (Groq Vision — Phase 3b)
└── Command Handler
        ↓
SQLite Database
        ↓
Sports APIs (Live)
├── API-Football (free tier: 100 req/day)
└── The Odds API (free tier: 500 req/month)
```

### Key Files
- `src/app.py` — Flask app, webhook handler, routing, group_id threading
- `src/butler.py` — All message formatting; templates + LLM framing + banter + match events
- `src/llm_client.py` — Groq API wrapper; `get_framing()`, `generate()`, `reset_persona()`
- `config/personality.yaml` — Butler character, player profiles, scenario guidance
- `src/parsers/message_parser.py` — Pick, result, command parsing
- `src/api/api_football.py` — API-Football v3 client with local file caching
- `src/api/odds_api.py` — The Odds API client with 2hr cache TTL
- `src/services/fixture_service.py` — Weekend fixture fetch + DB caching + event extraction
- `src/services/match_service.py` — Three-tier pick-to-fixture matching
- `src/services/match_monitor_service.py` — Live match events + smart auto-resulting
- `src/services/auto_result_service.py` — Auto-resulting from completed fixtures
- `src/services/scheduler.py` — APScheduler jobs + match monitor scheduling
- `src/services/` — player, week, pick, result, penalty, rotation, stats services
- `src/schema.sql` — SQLite schema (11 tables)

### Data Model (Key Tables)

**players** — id, name, nickname, formal_name, emoji, phone, rotation_position

**weeks** — id, week_number, season, deadline, status, placer_id, group_id

**picks** — id, week_id, player_id, description, odds_decimal, odds_original, bet_type, submitted_at, is_late, sport, competition, event_name, market_type, api_fixture_id, market_price, confirmed_odds

**fixtures** — id, api_id, sport, competition, competition_id, home_team, away_team, kickoff, status, home_score, away_score, ht_home_score, ht_away_score, fetched_at, raw_json

**team_aliases** — id, alias (COLLATE NOCASE), canonical_name

**results** — id, pick_id, outcome, score, confirmed_by, confirmed_at

**penalties** — id, player_id, week_id, type, amount, status, confirmed_by

**vault** — id, penalty_id, amount, description

**rotation_queue** — id, player_id, reason, position, week_added, processed

**fixture_events** — id, fixture_api_id, event_key (dedup), event_type, detail, minute, team, player, posted_at

**bet_slips** — id, week_id, placer_id, total_odds, stake, potential_return, image_path

---

## 11. Risk Assessment

### High Priority Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Bot crashes Friday night | High | Medium | Manual fallback, Ed override, PM2 auto-restart |
| Bot unresponsive silently | High | Medium | Health check every 5 min, Telegram alerts |
| WhatsApp ban/block | High | Low | Proper rate limiting, Business account |
| LLM produces bad output | Medium | Medium | Kill switch (`LLM_ENABLED=false`), template fallback |
| Missed results | Medium | Medium | Manual entry fallback, Ed confirmation |
| Wrong penalty calculation | Medium | Low | Ed confirmation before applying, manual override |
| Bet slip OCR failure | Medium | Medium | Manual entry fallback |

### Medium Priority Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Groq API unavailable | Low | Low | Silent fallback to templates — bot still works |
| Oracle account suspended | Medium | Low | Pay-As-You-Go conversion done |
| API rate limits exceeded | Medium | Medium | Caching, smart polling |
| Database corruption | Medium | Low | Daily backups, transaction safety |
| Timezone issues | Low | Low | Store UTC, display local time |

---

## 12. Open Questions

**C1: Nialler's participation**
- Data shows 58 picks vs 170-240 for others
- Question: Did Nialler join mid-season, or is data incomplete?
- Impact: Affects how we handle historical stats

**C3: Odds display format** ✅ Resolved
- Store decimal internally, display in format submitted

**D1: Bet slip OCR approach** — Deferred to Phase 2
- Starting with manual fallback
- Options: Tesseract (free), Google Vision (paid), Anthropic Vision API (accurate, low volume)

**D2: Image storage**
- Recommendation: Store 90 days for reference, then delete

---

## 13. Acceptance Criteria

### Phase 1.5 Complete When:
- [x] Butler character fully defined and documented
- [x] LLM framing architecture implemented (opening/closing only)
- [x] `personality.yaml` as single config source
- [x] Butler live in main group
- [x] Shadow mode working for monitoring LLM output
- [ ] First full weekend run assessed and persona tuned

### Phase 2 Complete When:
- [x] Shadow mode fixed (`_shadow_message()` updated)
- [x] Group isolation — test/main groups share DB safely
- [x] API-Football fixtures cached and picks matched to fixtures
- [x] Auto-resulting from completed fixtures (win, BTTS, over/under, HT/FT)
- [x] Market prices from The Odds API recorded alongside submitted odds
- [x] Enrichment is best-effort — never blocks pick submission
- [x] 92 tests passing

### Phase 3a Complete When:
- [x] Match monitor polls fixtures during match windows
- [x] Goals and red cards posted to group within 10 minutes
- [x] No duplicate event posts (fixture_events dedup)
- [x] Auto-result triggers on match end (FT/AET/PEN)
- [x] API budget stays within 100 req/day on Saturday (kickoff batching)
- [ ] One successful trial weekend in shadow group
- [ ] Switched to main group after trial

### Phase 3b Complete When:
- [ ] Bet slip images read and parsed (Groq Vision)
- [ ] Odds, stake, return extracted from screenshots
- [ ] `confirmed_odds` populated on matched picks
- [ ] Manual fallback works when OCR fails

---

## 14. Next Steps

### Immediate (This Week)
1. Deploy Phase 3a changes to OCI server
2. Set `MATCH_MONITOR_ENABLED=true` and `MATCH_MONITOR_GROUP_ID=<shadow_group>` in production `.env`
3. Trial weekend: monitor live events + auto-resulting in shadow group
4. After successful trial: switch `MATCH_MONITOR_GROUP_ID` to main group

### Near Term (Phase 3b)
- Bet slip image reading (Groq Vision)
- Match start validation
- Historical analytics / Punter Wrapped

---

## 15. Appendix

### Command Reference

**User Commands:**
- `!stats` — Your personal statistics
- `!stats [player]` — Stats for a specific player
- `!picks` — Recorded picks for this week
- `!leaderboard` — Win rate rankings
- `!rotation` — Current rotation and queue
- `!vault` — Vault total
- `!help` — This message
- `!myphone` — Your WhatsApp ID (for .env setup)

**Admin Commands (Ed only):**
- `!confirm penalty [player]` — Confirm a pending penalty
- `!override [player] [win/loss]` — Change a result
- `!resetweek` — Reset the current week (emergency)
- `!resetseason` — Clear all data for fresh start

**Admin Commands (You only):**
- `!status` — System health check
- `!ping` — Quick alive check

### Butler Phrase Bank (Templates)

**Reminders:**
- "Good evening, gentlemen. May I remind you that picks are due by 10 PM Friday."
- "Pardon the interruption. [Names] — 3 hours remain to submit your selections."
- "I do hope you'll forgive the urgency. [Names] — 30 minutes remain."

**Confirmations:**
- "Noted and recorded, [formal name]. [Pick] @ [odds]."
- "Updated, [formal name]. Replacing [old pick] with [new pick] @ [odds]."

**Results:**
- "I'm pleased to report — [name]'s selection: [pick] @ [odds]. ✅ Winner."
- "I'm afraid — [name]'s selection: [pick] @ [odds]. ❌ Lost."

**Penalties:**
- "I regret to inform you that [name] has incurred [N] consecutive losses. The suggested penalty is €[X] to the vault. Mr Edmund, would you kindly confirm: !confirm penalty [nickname]"

---

## Document History

**Versioning:** 0.x until MVP testing is successful; then 1.0.

**Version 0.1** — Initial requirements document. Discovery session, 54 questions answered.

**Version 0.2** — Phase 1 planning. Submission window, test mode, bridge architecture.

**Version 0.3** — Phase 1 complete. 73 unit tests passing. End-to-end verified.

**Version 0.4** — Cumulative pick format. Emoji-based parsing added.

**Version 0.5** — Picks without odds. Placer confirmation flow.

**Version 0.6** — Formal pick display. Abbreviation expansion, odds shown once.

**Version 0.7** — Pick confirmation refinements. No-odds placer naming, cumulative deduplication.

**Version 0.8** — Display and availability. Puppeteer stability patches.

**Version 0.9** — Copy and addressing. Formal name standardisation.

**Version 0.10** — Bet slip planning. Multiple screenshots, bookmaker recording.

**Version 0.11** — Cloud deployment planning. Oracle Cloud Always Free selected.

**Version 0.12** — Match start validation planning (Phase 3).

**Version 0.13** — Cumulative pick replacement. Bare team name acceptance.

**Version 0.14** — Hosting and reliability. PM2, health check, Telegram alerting.

**Version 0.15** — OCI deployment complete. Puppeteer patches, Telegram alerts live.

**Version 0.16** — LLM personality Phase 1.5. Colonel Slade persona, shadow testing.

**Version 0.17** — LLM scope narrowed. Colonel Slade too verbose; commands reverted to templates.

**Version 0.18** — Rotation fix, admin phones, display polish. All 6 player phones stored.

**Version 0.19** — Butler character rewrite (2026-02-23)
- Colonel Slade removed entirely
- New butler character fully defined: warm beneath formality, faintly absurd enterprise, unflappable
- Individual player relationships defined (Ed, Kev, DA, Nug, Nialler, Pawn, Brian)
- New LLM architecture: framing only — opening/closing lines wrap templates, never replace them
- `llm_client.py` rewritten: `generate()` replaced by `get_framing()` returning `{"opening": "...", "closing": "..."}`
- `butler.py` rewritten: `_frame()` helper wraps all template content
- `personality.yaml` rewritten: character, voice, player profiles, scenario guidance, output format
- Friday reminder updated: 5PM → 7PM
- `LLM_ENABLED=true` — butler live in main group

**Version 0.20** — Phase 2: Structured Data & API Integration (2026-02-25)
- Fixed broken LLM functions: `generate()`, `banter_reply()`, `reset_persona()`
- Shadow mode fixed (`_shadow_message()` calls working `generate()`)
- Group isolation: `group_id` on weeks table, test/main groups fully isolated
- Schema extensions: 7 enrichment columns on picks, fixtures table, team_aliases table (50+ aliases)
- API-Football v3: fixture caching (Wed 7:30PM), pick matching (alias → fuzzy → LLM)
- Auto-resulting: win, BTTS, over/under, HT/FT from completed fixtures (Sun 8PM, Mon 10AM)
- The Odds API: market price lookup on pick submission (best-effort, 2hr cache)
- Three odds values per pick: player-submitted, market price, confirmed (bet slip — Phase 3)
- 92 tests passing (up from 73)

**Version 0.21** — Phase 3a: Live Match Events & Smart Auto-Resulting (2026-02-25)
- Match monitor service: unified polling loop for events + auto-resulting
- Live events: goals and red cards posted to group during matches (⚽ / 🟥)
- Smart auto-resulting: per-fixture on match end, replaces fixed Sun 8PM cron
- Kickoff batching: fixtures sharing a date use single API call (stays within budget)
- `fixture_events` table for event dedup
- Feature-flagged: `MATCH_MONITOR_ENABLED` + `MATCH_MONITOR_GROUP_ID` (trial in shadow group)
- Startup recovery: re-schedules monitors for unresulted picks on restart
- 115 tests passing (up from 92)

**Next Review:** After trial weekend with match monitor live in shadow group

---

**Document Owner:** You (Primary Admin)
**Stakeholders:** Ed (Co-admin), The Lads (Users)
**Last Updated:** 2026-02-25
**Status:** ✅ Phase 3a Implemented — Live match events & smart auto-resulting (trial pending)
