"""
The all-picks-in announcement names the next placer — it should also
mention the !slip delegation route, since players otherwise invent
workarounds (sending the slip to the placer to forward) to avoid
"messing with the bot's rota".
"""

import src.butler as butler

PLACER = {"formal_name": "Mr Kevin", "emoji": "🧌"}


class TestSlipHint:
    def test_all_picks_in_mentions_slip_delegation(self):
        text = butler.all_picks_in(PLACER)
        assert "!slip" in text

    def test_all_picks_in_still_names_placer(self):
        text = butler.all_picks_in(PLACER)
        assert "Mr Kevin" in text
        assert "place the wager" in text
