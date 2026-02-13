# Punter Punter Punter Bot - Requirements Document

## Executive Summary

**Project Goal:** Automate betting game management to save Ed ~1 hour/week and increase engagement through better stats and tracking.

**Success Criteria:** 
- Makes game more engaging via performance feedback
- Saves Ed time on manual tracking
- Reliable Friday-Monday operation
- Manual override capability for errors

**Timeline:** No rush, sporadic development (few hours on weekends)

**Budget:** Free tier (local hosting initially, AWS later if needed)

---

## 1. User Personas

### Primary Users (Players)
- **Ed** - Most engaged, current manual tracker, co-admin (post-launch)
- **DA (Don), Kev, Nug, Nialler, Pawn** - Varying engagement levels
- **Nug (Nugget)** - Least engaged player
- **Technical comfort:** Mixed - bot must be mostly automatic with optional commands

### Formal Addressing Convention
The bot uses formal butler-style addressing for all players:

| Player Nickname | Formal Address |
|----------------|----------------|
| Ed | Mr Edmund |
| Kev | Mr Kevin |
| DA (Don) | Mr Declan |
| Nug (Nugget) | Mr Ronan |
| Nialler | Mr Niall |
| Pawn | Master |

**Usage:** The bot uses these formal addresses in all communications (reminders, announcements, results, penalties).

**Example:** "Good evening, gentlemen. Currently awaiting selections from Mr Ronan and Master."

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
  ♟️ Dortmund to beat Mainz 6/10
  🧌 Liverpool to win 2/1
  🍋 Man City Brentford BTTS 8/11
  ```
- **Player emoji mapping** (stored in `players.emoji`, supports multiple aliases comma-separated):

| Player | Nickname | Emoji(s) |
|--------|----------|----------|
| Edmund | Ed | 🍋, 🍋🍋🍋 |
| Kevin | Kev | 🧌 |
| Declan | DA | 👴🏻 |
| Ronan | Nug | 🍗 |
| Nialler | Niall | 🔫 |
| Aidan | Pawn | ♟️ |

- Bot parses each line, matches emoji to player, and submits all picks in one message

#### Validation & Handling
- **Invalid picks:** Bot attempts to interpret â†’ asks for confirmation
- **Missing information:** Request clarification
- **Duplicate submissions:** Accept latest as update
- **Picks without odds:** Players may omit odds; they trust the placer to use whatever is available at the bookie (≥1.5). Stored as `odds_original: "placer"`, `odds_decimal: 2.0`. Bot confirms: "— placer to confirm odds at the bookie."

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
- If the bot misreads a pick, the player simply resends the corrected version

#### Formal Pick Display
When the bot displays picks (confirmations, `!picks`, result announcements), it shows a **formal** version rather than echoing the raw message:
- **Abbreviations expanded:** leics → Leicester, Soton → Southampton, Man City → Manchester City, etc.
- **Team separator:** `leics/Soton` → `Leicester vs Southampton`
- **Odds preserved:** Fractional odds (4/6, 2/1) are shown as submitted
- Raw input is stored in the database; formalization is applied only for display

#### Automated Reminders
1. **Thursday 7:00 PM** â†' Tag all players: "Reminder: Submit your picks by Friday 10 PM"
2. **Friday 5:00 PM** â†' Tag missing players only: "Reminder: [Player list] - 5 hours left"
3. **Friday 9:30 PM** â†' Tag missing players + send DMs: "Final warning - 30 minutes!"

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
- Player uploads bet slip screenshot to WhatsApp
- Bot reads image to extract:
  - All picks and their odds
  - Total odds
  - Stake amount
  - Potential return
- Bot stores this for tracking and stats
- Bot confirms: "Bet slip recorded: 6 picks @ 47.5 odds, â‚¬120 stake, potential return â‚¬5,700"

#### If Placer Forgets
- **Hasn't happened yet**
- **Expected behavior:** Someone else steps in
- **Bot should:** Allow manual override for who placed

---

### 2.4 Result Tracking

#### Phase 1 (MVP): Manual Entry
- **Method:** Ed posts results using existing convention
- **Format:** "Player âœ…" or "Player âŒ"
- **Bot behavior:** Parse message, update database, announce
- **Precision:** For complex bets (handicap, O/U), provide detailed explanation

#### Phase 2 (Future): Automatic Detection
- **Priority:** Nice-to-have for later
- **Timing:** 30 minutes post-match is acceptable
- **Announcement:** Real-time as results come in (throughout weekend)
- **Fallback:** If auto-detection fails, revert to manual entry

---

### 2.5 Penalties & Rules

#### Current Penalty Structure
- **3 consecutive losses** â†’ Pay for next week's bet
- **5 consecutive losses** â†’ â‚¬50 to vault
- **7 consecutive losses** â†’ â‚¬100 to vault
- **10 consecutive losses** â†’ â‚¬200 to vault

#### Bot Behavior
- **Detection:** Automatic tracking of streaks
- **Action:** Suggest penalty to Ed for confirmation
- **Announcement:** Factual, not shameful
- **Example:** "Mr Nialler has hit 5 consecutive losses. Suggested penalty: â‚¬50 to vault. Mr Edmund, please confirm."

#### Payment Tracking
- **Method:** Revolut to Ed
- **Bot tracking:** NOT required (Ed handles outside bot)

#### Rule Evolution
- **Status:** Mostly stable, unlikely to change
- **Flexibility:** Allow Ed to modify rules in config

---

### 2.6 Rotation Management

#### Standard Rotation
`Kev â†’ Nialler â†’ Nug â†’ Pawn â†’ Don â†’ Ed`

#### Penalty Queue
When players incur penalties (late submission, 3-loss), they join queue.

#### Visibility Requirements
**Queue Display Format:**
```
ðŸ“… ROTATION STATUS
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”
Last Placed: Ed (Week 23)
Next Up: Kev ðŸ‘ˆ

Queue:
1. Nialler
2. Nug (penalty - late)
3. Pawn
4. DA
5. Ed (penalty - 3-loss)
6. Kev

Penalties in Queue:
â€¢ Ed - 3-loss streak
â€¢ Nug - Late submission
```

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

#### Secondary Stats (Occasional/On-Demand)
- **Favorite bet types:** Most successful bet type
- **Sport performance:** Best/worst sports
- **Team/player performance:** If killing it or failing badly at specific teams
- **Volume stats:** Total picks, penalties incurred

#### Stats Access Methods
1. **On-demand:** `!stats` command anytime
2. **Monday morning recap:** Automated weekly summary

#### Leaderboard
- **Ranking:** Pure win rate (not weighted by volume)
- **Format:**
```
ðŸ† LEADERBOARD
â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”
ðŸ¥‡ Ed: 87.6% (212/242)
   Form: WWLWW
   
ðŸ¥ˆ Kev: 84.1% (143/170)
   Form: WWWWL
   
ðŸ¥‰ DA: 83.3% (150/180)
   Form: WWWWW
```

---

### 2.8 Accumulator Management

#### Cashouts
- **Decision:** Requires group consensus
- **Bot role:** Does NOT suggest when to cash out
- **Tracking:** Not required

#### Payouts (When Accumulator Wins)
- **Collection:** Person who placed collects
- **Distribution:** Via Revolut
- **Bot tracking:** NOT required
- **Bot can:** Announce win and potential share per person for reference

---

## 3. Bot Personality & Communication

### "The Betting Butler" ðŸŽ©

**Inspiration:** Butler from *Remains of the Day*
- Polite, proper, efficient
- Formal but not stuffy
- Helpful without being overbearing
- Does NOT try to copy group banter (would feel inauthentic)

**Example Communications:**

**Reminder:**
> "Good evening, gentlemen. May I remind you that picks are due by 10 PM Friday. Currently awaiting selections from Mr Ronan and Master."

**Penalty:**
> "I regret to inform you that Mr Nialler has incurred five consecutive losses. The suggested penalty is €50 to the vault. Mr Edmund, would you kindly confirm?"

**All Picks In:**
> "All selections have been received. Mr Kevin, you are next in the rotation to place the wager."

**Result:**
> "Mr Declan's selection: Chelsea BTTS @ 8/11
> Result: Chelsea 2-1 Arsenal
> Both teams scored. ✅ Winner."

**Tone Guidelines:**
- âœ… Polite and formal
- âœ… Clear and informative
- âœ… Factual, not celebratory or shameful
- âŒ Don't try to be funny or banterous
- âŒ Don't use excessive emojis (except functional ones)
- âŒ Don't be overly wordy

---

## 4. Technical Requirements

### 4.1 Uptime & Reliability

#### Critical Uptime Windows
- **Friday 5 PM - 10 PM:** Deadline reminders and pick collection
- **Saturday - Sunday:** Result tracking
- **Monday morning:** Weekly recap
- **Overall:** Friday 5 PM â†’ Monday 10 AM

#### Downtime Acceptable
- **Monday afternoon - Thursday:** Lower priority
- **If bot goes down Friday night:** Revert to manual for that week

#### Recovery
- **Manual override:** Ed must be able to manually enter everything
- **Error handling:** All errors must be recoverable without data loss
- **Backup:** Ed can access bot admin to fix issues

---

### 4.2 Data & Privacy

#### Data Storage
- **Store everything:** All picks, results, stats, penalties
- **Persistence:** Permanent historical record
- **No deletion:** Stats are permanent (unless major issue)

#### Privacy & Security
- **WhatsApp messages on server:** Not a concern
- **Betting data in cloud:** Not a concern
- **Assessment:** "Harmless fun" - no sensitive data

---

### 4.3 Platform & Hosting

#### Initial Setup
- **Platform:** Local hosting (your machine)
- **Architecture:** Python + whatsapp-web.js
- **Database:** SQLite
- **Budget:** Free

#### Future Migration
- **Platform:** AWS (when ready)
- **You cover costs:** Long-term AWS hosting
- **Budget:** Keep minimal (~$6/month EC2)

#### Sports Data APIs
- **Budget:** $0 - must use free tiers only
- **Strategy:** 
  - The Odds API: 500 requests/month (free)
  - API-Football: 100 requests/day (free)
  - Stay within limits through smart caching

---

### 4.4 Testing Strategy

#### Test Mode
- **TEST_MODE=true** enables prefix-based player simulation in the test group
- **Prefix format:** `Kev: Manchester United 2/1` — bot attributes the pick to Kev
- **Cumulative/emoji format:** Copy messages from main group into test group — each line `[emoji] [pick]` is parsed and attributed to the matching player (see Player emoji mapping above)
- Allows a single user to simulate all 6 players for end-to-end testing
- In production (TEST_MODE=false), players are identified by phone number or emoji (cumulative format works in both modes)

#### Architecture Decisions (from Phase 0)
- **Bridge uses Node.js `http` module** (not `fetch`) — Node 18's experimental fetch is unreliable for localhost
- **Bridge connects to `127.0.0.1`** (not `localhost`) — avoids IPv6/IPv4 mismatch on macOS
- **Bridge uses `message_create` event** (not `message`) — captures own messages for test group use
- **Bot reply loop prevention** — bridge tracks sent messages via `botSentMessages` set
- **Flask runs on port 5001** — port 5000 is used by AirPlay Receiver on macOS

---

### 4.5 Scalability & Future

#### Current Scope
- **Users:** 6 players (Ed, DA, Kev, Nug, Nialler, Pawn)
- **Groups:** 1 WhatsApp group
- **Focus:** This specific use case only

#### Future Possibilities (NOT MVP)
- Additional players to existing group
- Separate friend groups
- Sharing bot with other betting groups
- Web dashboard (maybe)
- Mobile app (no)
- Betting account integration (no)

---

## 5. Feature Prioritization

### Must-Have (MVP - Phase 1)
**Dealbreaker:** Read messages from group

**Core Features:**
- âœ… Pick collection with validation
- âœ… Automated reminders (Thu/Fri schedule)
- âœ… Manual result entry (Ed posts, bot parses)
- âœ… Rotation management with visible queue
- âœ… Penalty tracking (3/5/7/10-loss)
- âœ… Stats on demand (!stats command)
- âœ… Vault tracking
- âœ… Monday morning recap
- âœ… Bet slip image reading & parsing

### Should-Have (Phase 2)
- âš¡ Automatic result detection from APIs
- âš¡ Leaderboard (!leaderboard command)
- âš¡ Historical trends & analytics
- âš¡ Live score updates during matches
- âš¡ Web dashboard

### Could-Have (Phase 3+)
- ðŸ’¡ Odds movement alerts
- ðŸ’¡ Weekly/monthly reports
- ðŸ’¡ Export data features
- ðŸ’¡ Advanced bet type support

### Won't-Have
- âŒ AI pick suggestions
- âŒ Bet slip generation (player does this)
- âŒ Bookmaker recommendations
- âŒ Automatic bet placement
- âŒ Payment tracking (handled via Revolut)
- âŒ Cashout suggestions
- âŒ Mobile app
- âŒ Betting account integration

---

## 6. Success Metrics

### Primary Success Criteria
1. **Engagement:** Game becomes more engaging through performance feedback
2. **Time savings:** Ed saves ~1 hour/week on manual tracking
3. **Reliability:** Bot works reliably Friday-Monday
4. **Override capability:** Manual override works when needed

### Measurement Methods
- **User feedback:** Direct feedback from the lads
- **Usage stats:** Commands used, engagement with stats
- **Time tracking:** Ed's time spent on manual tasks
- **Error rate:** Frequency of manual interventions needed

### Acceptable Failure Modes
- **Bot mistakes:** Minor annoyance, manually fixable
- **Bugs:** Expected in early phase, part of learning
- **Downtime:** Can revert to manual for a week

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
â””â”€> Bot: "Good evening, gentlemen. Picks due Friday 10 PM."

Friday 6:30 PM - Player submits pick
â””â”€> Player: "ðŸ§Œ Manchester United 2/1"
â””â”€> Bot: "Mr Kevin's selection recorded: Manchester United @ 2/1. 
         Awaiting picks from: DA, Nug."

Friday 9:50 PM - All picks in
â””â”€> Bot: "All selections received. Mr Nialler, you are next to place."

Saturday 10 AM - Nialler places bet
â””â”€> Nialler: [Uploads bet slip screenshot]
â””â”€> Bot: "Bet slip recorded. 6 picks @ 47.5 total odds. â‚¬120 stake. 
         Potential return: â‚¬5,700."

Saturday 5 PM - Results start coming in
â””â”€> Ed: "Kev âœ…"
â””â”€> Bot: "Mr Kevin's selection: Manchester United @ 2/1
         Result: Manchester United 2-1 Liverpool âœ…"

Sunday 8 PM - All results in
â””â”€> Bot: "Weekend complete.
         Won: Ed, Kev, DA
         Lost: Nug, Nialler, Pawn
         Accumulator: Lost (3 of 6 won)"

Monday 9 AM - Weekly recap
â””â”€> Bot: [Posts weekly statistics summary]
```

### Flow 2: Late Submission (Penalty Path)
```
Friday 10:01 PM - Player submits after deadline
â””â”€> Player: "ðŸ§Œ Manchester United 2/1"
â””â”€> Bot: "Mr Kevin, your selection is after the deadline. 
         Penalty: You will place next week's wager.
         Rotation queue updated."

â””â”€> Bot: "ðŸ“… ROTATION UPDATE
         Next: DA (Week 24)
         Queue: Kev (penalty), Nialler, Nug, Pawn, Ed"
```

### Flow 3: Streak Penalty Detection
```
Sunday 6 PM - Result causes 5th consecutive loss
â””â”€> Ed: "Nialler âŒ"
â””â”€> Bot: "Mr Nialler's selection lost.
         Current streak: 5 consecutive losses.
         Suggested penalty: â‚¬50 to vault.
         Mr Edmund, please confirm: !confirm penalty Nialler"

â””â”€> Ed: "!confirm penalty Nialler"
â””â”€> Bot: "Penalty confirmed. Vault updated: â‚¬600 total.
         Mr Nialler, please send â‚¬50 to Ed via Revolut."
```

### Flow 4: Bet Slip Reading Error
```
Saturday 10 AM - Unclear bet slip image
â””â”€> Nialler: [Uploads blurry/unclear bet slip]
â””â”€> Bot: "I'm unable to read the bet slip clearly. 
         Could you please confirm:
         - Total odds: ?
         - Stake: â‚¬120?
         - Potential return: ?"

â””â”€> Nialler: "47.5 odds, â‚¬120 stake, â‚¬5700 return"
â””â”€> Bot: "Confirmed. Bet slip recorded manually."
```

---

## 9. Implementation Phases

### Phase 0: Foundation (Week 1-2)
- âœ… Set up Python + whatsapp-web.js
- âœ… Connect to WhatsApp
- âœ… Database schema
- âœ… Basic message parsing
- âœ… Test with group

### Phase 1: MVP (Week 3-4)
- Pick collection with validation
- Automated reminders
- Manual result entry
- Basic rotation management
- Penalty tracking
- Stats (!stats command)
- Deploy locally

### Phase 2: Enhancements (Week 5-6)
- Bet slip image reading (OCR)
- Rotation queue visibility
- Leaderboard
- Monday recap
- Polish butler personality

### Phase 3: Intelligence (Week 7-8)
- API integration (The Odds API, API-Football)
- Automatic result detection
- Live score updates
- Historical analytics

### Phase 4: Refinement (Ongoing)
- Bug fixes based on real usage
- Performance optimization
- Feature requests from users
- Potential web dashboard

---

## 10. Technical Architecture

### System Components

```
WhatsApp Group (Users)
        â†“
Node.js Bridge (whatsapp-web.js)
        â†“ HTTP
Python Backend (Flask)
â”œâ”€â”€ Message Parser
â”œâ”€â”€ Pick Validator
â”œâ”€â”€ Result Tracker
â”œâ”€â”€ Penalty Engine
â”œâ”€â”€ Rotation Manager
â”œâ”€â”€ Stats Calculator
â”œâ”€â”€ Image Reader (OCR)
â””â”€â”€ Command Handler
        â†“
SQLite Database
        â†“
Sports APIs (Phase 3)
â”œâ”€â”€ The Odds API (free tier)
â””â”€â”€ API-Football (free tier)
```

### Data Model (Key Tables)

**players**
- id, name, emoji, phone

**picks**
- week, player, description, odds, bet_type, submitted_at

**results**
- week, player, outcome, score, auto_detected

**penalties**
- player, type, amount, timestamp

**vault**
- amount, transaction_type, description, timestamp

**rotation_queue**
- player, reason, position, processed

**bet_slips**
- week, placer, total_odds, stake, potential_return, image_path

---

## 11. Risk Assessment

### High Priority Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Bot crashes Friday night | High | Medium | Manual fallback, Ed override, PM2 auto-restart |
| WhatsApp ban/block | High | Low | Use official Business API eventually, proper rate limiting |
| Missed results | Medium | Medium | Manual entry fallback, Ed confirmation |
| Wrong penalty calculation | Medium | Low | Ed confirmation before applying, manual override |
| Bet slip OCR failure | Medium | Medium | Manual entry fallback, ask for confirmation |

### Medium Priority Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| API rate limits exceeded | Medium | Medium | Caching, smart polling, free tier monitoring |
| Database corruption | Medium | Low | Daily backups, transaction safety |
| Player confusion with commands | Low | Medium | Clear help text, butler clarifications |
| Timezone issues | Low | Low | Store UTC, display local time |

---

## 12. Open Questions & Decisions Needed

### Clarifications from Discovery

**C1: Nialler's participation**
- You mentioned Nialler's participation might not actually be low
- Data shows 58 picks vs 170-240 for others
- **Question:** Did Nialler join mid-season, or is data incomplete?
- **Impact:** Affects how we handle historical stats

**C2: Butler personality scope**
- Every message in butler style, or just certain announcements?
- **Options:**
  1. All messages (consistent but potentially annoying)
  2. Just reminders/announcements (balanced)
  3. Just general polite tone (subtle)
- **Recommendation:** Option 2 - Butler for official announcements, normal for responses

**C3: Odds display format**
- Accept both decimal and fractional (confirmed âœ…)
- **Question:** How to display in stats/announcements?
  - Show in original format submitted?
  - Standardize to one format?
  - Show both?
- **Recommendation:** Store decimal internally, display in format submitted

### Technical Decisions Needed

**D1: Bet slip OCR approach**
- **Options:**
  1. Tesseract (free, offline, lower accuracy)
  2. Google Vision API (paid, higher accuracy)
  3. Manual entry fallback only
- **Recommendation:** Start with #3, add Tesseract in Phase 2

**D2: Image storage**
- Should bet slip images be:
  - Stored permanently (takes space)
  - Stored temporarily (30 days)
  - Not stored (just extract data)
- **Recommendation:** Store 90 days for reference, then delete

**D3: Stats calculation timing**
- When to calculate stats:
  - On-demand (slower but accurate)
  - Cached (faster but periodic updates)
  - Hybrid (cache with smart invalidation)
- **Recommendation:** Hybrid - recalculate on new results, cache otherwise

---

## 13. Acceptance Criteria

### MVP Complete When:
- [ ] Bot connects to WhatsApp group
- [ ] Thursday 7 PM reminder sends automatically
- [ ] Friday 5 PM reminder tags missing players
- [ ] Friday 9:30 PM reminder tags + DMs missing players
- [ ] Picks submitted in various formats are parsed correctly
- [ ] Late picks trigger rotation queue penalty
- [ ] Ed can post "Player âœ…/âŒ" and bot updates results
- [ ] Streak penalties (3/5/7/10) are detected and suggested
- [ ] Ed can confirm penalties with command
- [ ] Rotation queue displays correctly
- [ ] !stats command shows player statistics
- [ ] Monday 9 AM recap posts automatically
- [ ] Ed can manually override any result
- [ ] Bot runs Friday-Monday without intervention
- [ ] All data persists in database

### Phase 2 Complete When:
- [ ] Bet slip images are read and parsed
- [ ] Odds, stake, return extracted from images
- [ ] Manual fallback works when OCR fails
- [ ] Leaderboard displays with !leaderboard
- [ ] Historical stats track trends over time

### Phase 3 Complete When:
- [ ] API integration finds fixtures automatically
- [ ] Results detected within 30 minutes of match end
- [ ] Live scores update during matches
- [ ] 90% of results detected automatically
- [ ] Fallback to manual works seamlessly

---

## 14. Next Steps

### Immediate Actions (This Week)
1. âœ… Complete requirements discovery (DONE)
2. Create detailed technical specification
3. Set up development environment
4. Initialize project structure
5. Get WhatsApp connection working

### Week 1-2 Goals
- Basic bot responding to messages
- Pick collection working
- Database storing picks
- Manual result entry functional

### Before Launch Checklist
- [ ] Test with 2-3 weeks of real data
- [ ] Ed validates all features
- [ ] Error handling tested
- [ ] Manual override confirmed working
- [ ] Group briefed on bot commands
- [ ] Backup/recovery plan documented

---

## 15. Appendix

### Command Reference (MVP)

**User Commands:**
- `!stats` - Show your personal statistics
- `!stats [player]` - Stats for a specific player
- `!picks` - Recorded picks for this week (formal display)
- `!leaderboard` - Show win rate rankings
- `!rotation` - Show current rotation and queue
- `!vault` - Show vault total
- `!help` - Show available commands

**Admin Commands (Ed only):**
- `!confirm penalty [player]` - Confirm suggested penalty
- `!override [player] [win/loss]` - Manually set result
- `!resetweek` - Reset current week (emergency)

**Admin Commands (You only):**
- `!status` - System health check
- `!logs` - View recent errors
- `!restart` - Restart bot components

### Butler Phrase Bank

**Reminders:**
- "Good evening, gentlemen. May I remind you..."
- "Pardon the interruption, but the deadline approaches..."
- "I do hope you'll forgive the reminder..."

**Confirmations:**
- "Very good, sir."
- "Noted and recorded."
- "Duly noted."
- "As you wish."

**Penalties:**
- "I regret to inform you..."
- "Unfortunately, Mr [Player Name] has incurred..."
- "May I suggest the appropriate penalty is..."

**Results:**
- "The result has been determined..."
- "I'm pleased to report..." (for wins)
- "I'm afraid the selection did not succeed..." (for losses)

**Errors:**
- "I beg your pardon, but I'm unable to..."
- "My apologies, I require clarification..."
- "Forgive me, but could you please..."

---

## Document History

**Version 1.0** - Initial requirements document
- Based on discovery session with product owner
- 54 questions answered
- All critical decisions documented
- Ready for technical specification phase

**Version 1.1** - Phase 1 planning updates
- Submission window changed from Thursday 7PM to Wednesday 7PM
- Added pick confirmation behavior (confirm on receipt, no response required)
- Added test mode documentation (prefix format for test group)
- Documented bridge architecture decisions (IPv4, message_create event, http module)

**Version 1.2** - Phase 1 implementation complete (2026-02-12)
- Phase 0 and Phase 1 fully implemented and tested
- 73 unit tests passing across parser and all service modules
- End-to-end WhatsApp testing verified (picks, results, commands, penalties, rotation)
- Formal name updated: Mr Nialler -> Mr Niall
- Bridge now loads .env via dotenv (shared config with Flask backend)
- Command args parser fixed to split all arguments individually
- `!stats [player]` added for viewing other players' stats

**Version 1.3** - Cumulative pick format (2026-02-13)
- Added emoji-based cumulative message parsing: one pick per line, `[emoji] [pick]`
- Player emoji mapping stored in `players.emoji` (supports multiple aliases, e.g. Ed: 🍋,🍋🍋🍋)
- Enables copying thread-style messages from main group into test group for testing
- All 6 players have emojis configured

**Version 1.4** - Picks without odds (2026-02-13)
- Players may submit picks without explicit odds (e.g. "Scotland + 8", "Dortmund to beat Mainz")
- Player trusts placer to use whatever odds are available at the bookie (≥1.5)
- Stored as `odds_original: "placer"`, `odds_decimal: 2.0`
- Pick detection: bet type keywords (BTTS, handicap, over/under), "to beat"/"to win", team vs team
- Cumulative thread: only acknowledge new picks, not re-submissions already in the thread

**Version 1.5** - Formal pick display (2026-02-13)
- Bot displays formalized pick text in confirmations, `!picks`, and result announcements
- Abbreviations expanded (leics→Leicester, Soton→Southampton, Man City→Manchester City, etc.)
- Team separator `/` rendered as " vs " (e.g. leics/Soton → Leicester vs Southampton)
- Raw input stored in DB; formalization applied at display time only
- `!picks` command added to view recorded picks for the current week

**Next Review:** After Phase 2 planning

---

**Document Owner:** You (Primary Admin)
**Stakeholders:** Ed (Co-admin), The Lads (Users)
**Last Updated:** 2026-02-13
**Status:** âœ… Requirements Complete - Ready for Development