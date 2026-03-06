"""Tests for rotation_service."""

from src.services.rotation_service import (
    get_next_placer, add_to_penalty_queue, advance_rotation, get_rotation_display,
)
from src.services.player_service import get_all_players
from src.services.week_service import get_or_create_current_week


class TestGetNextPlacer:
    def test_first_placer_is_kev(self):
        """With no history, the first in rotation (Kev, position 1) should be next."""
        placer = get_next_placer()
        assert placer is not None
        assert placer["nickname"] == "Kev"

    def test_rotation_advances(self):
        """After Kev places, Nialler (position 2) should be next."""
        week = get_or_create_current_week()
        players = get_all_players()

        # Kev is first (rotation_position=1)
        kev = next(p for p in players if p["nickname"] == "Kev")
        advance_rotation(week["id"], kev["id"])

        # Complete the week so rotation advances
        from src.db import get_db
        conn = get_db()
        conn.execute("UPDATE weeks SET status = 'completed' WHERE id = ?", (week["id"],))
        conn.commit()
        conn.close()

        placer = get_next_placer()
        assert placer["nickname"] == "Nialler"


class TestPenaltyQueue:
    def test_penalty_queue_takes_priority(self):
        """Penalty queue entries should come before standard rotation."""
        players = get_all_players()
        nug = next(p for p in players if p["nickname"] == "Nug")

        add_to_penalty_queue(nug["id"], "3 consecutive losses")

        placer = get_next_placer()
        assert placer["nickname"] == "Nug"

    def test_penalty_queue_processed(self):
        """After advancing, penalty entry should be marked processed."""
        week = get_or_create_current_week()
        players = get_all_players()
        nug = next(p for p in players if p["nickname"] == "Nug")

        add_to_penalty_queue(nug["id"], "3 consecutive losses")
        advance_rotation(week["id"], nug["id"])

        from src.db import get_db
        conn = get_db()
        conn.execute("UPDATE weeks SET status = 'completed' WHERE id = ?", (week["id"],))
        conn.commit()
        conn.close()

        # After processing, standard rotation resumes from after Nug (position 3)
        placer = get_next_placer()
        # Next after Nug in rotation is Pawn (position 4)
        assert placer["nickname"] == "Pawn"


class TestPenaltyQueueRotationOrder:
    def test_penalty_does_not_disrupt_standard_rotation(self):
        """Penalty entry should appear at top; standard rotation continues from last placer."""
        # Rotation order: Kev(1), Nialler(2), Nug(3), Pawn(4), DA(5), Ed(6)
        # Simulate: Ed placed last (week closed, not completed), DA has penalty
        from src.db import get_db
        players = get_all_players()
        ed = next(p for p in players if p["nickname"] == "Ed")
        da = next(p for p in players if p["nickname"] == "DA")

        week = get_or_create_current_week()
        advance_rotation(week["id"], ed["id"])
        # Week is only 'closed', not 'completed'
        conn = get_db()
        conn.execute("UPDATE weeks SET status = 'closed' WHERE id = ?", (week["id"],))
        conn.commit()
        conn.close()

        add_to_penalty_queue(da["id"], "3 consecutive losses")

        data = get_rotation_display()

        # Last placer should be Ed (even though week is only 'closed')
        assert data["last_placer"]["nickname"] == "Ed"

        # Next placer should be DA (from penalty queue)
        assert data["next_placer"]["nickname"] == "DA"

        # Queue should be: DA(penalty), Kev, Nialler, Nug, Pawn, DA, Ed
        queue_names = [(q["formal_name"], q["reason"]) for q in data["queue"]]
        assert queue_names[0] == ("Mr Declan", "3 consecutive losses")  # DA penalty
        assert queue_names[1] == ("Mr Kevin", None)    # standard continues from Kev
        assert queue_names[2] == ("Mr Niall", None)
        assert queue_names[3] == ("Mr Ronan", None)
        assert queue_names[4] == ("Mr Aidan", None)
        assert queue_names[5] == ("Mr Declan", None)   # DA's normal slot
        assert queue_names[6] == ("Mr Edmund", None)

    def test_closed_week_placer_visible(self):
        """A placer recorded on a 'closed' week should be found by get_next_placer."""
        from src.db import get_db
        players = get_all_players()
        kev = next(p for p in players if p["nickname"] == "Kev")

        week = get_or_create_current_week()
        advance_rotation(week["id"], kev["id"])

        # Only close the week — do NOT set to 'completed'
        conn = get_db()
        conn.execute("UPDATE weeks SET status = 'closed' WHERE id = ?", (week["id"],))
        conn.commit()
        conn.close()

        placer = get_next_placer()
        assert placer["nickname"] == "Nialler"


class TestRotationDisplay:
    def test_display_returns_data(self):
        data = get_rotation_display()
        assert data["next_placer"] is not None
        assert isinstance(data["queue"], list)
        assert len(data["queue"]) > 0

    def test_display_has_all_players_in_queue(self):
        data = get_rotation_display()
        players = get_all_players()
        assert len(data["queue"]) == len(players)

    def test_display_queue_with_penalty_has_extra_entry(self):
        """Queue with a penalty entry should have len(players) + 1 entries."""
        players = get_all_players()
        nug = next(p for p in players if p["nickname"] == "Nug")
        add_to_penalty_queue(nug["id"], "penalty test")

        data = get_rotation_display()
        assert len(data["queue"]) == len(players) + 1
        # First entry should be the penalty
        assert data["queue"][0]["reason"] == "penalty test"
