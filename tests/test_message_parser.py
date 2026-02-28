import os

from src.parsers.message_parser import (
    parse_message, extract_test_prefix, parse_cumulative_picks, detect_sport,
    gaa_needs_clarification,
)


class TestCommandParsing:
    def test_help_command(self):
        result = parse_message("!help", "Kev")
        assert result["type"] == "command"
        assert result["parsed_data"]["command"] == "help"

    def test_stats_command(self):
        result = parse_message("!stats", "Ed")
        assert result["type"] == "command"
        assert result["parsed_data"]["command"] == "stats"

    def test_command_with_args(self):
        result = parse_message("!confirm penalty Nialler", "Ed")
        assert result["type"] == "command"
        assert result["parsed_data"]["command"] == "confirm"
        assert result["parsed_data"]["args"] == ["penalty", "Nialler"]

    def test_rotation_command(self):
        result = parse_message("!rotation", "Nug")
        assert result["type"] == "command"
        assert result["parsed_data"]["command"] == "rotation"


class TestPickParsing:
    def test_fractional_odds(self):
        result = parse_message("Manchester United 2/1", "Kev")
        assert result["type"] == "pick"
        assert result["parsed_data"]["odds_original"] == "2/1"
        assert result["parsed_data"]["odds_decimal"] == 3.0
        assert result["parsed_data"]["bet_type"] == "win"

    def test_fractional_odds_complex(self):
        result = parse_message("Arsenal 11/4", "DA")
        assert result["type"] == "pick"
        assert result["parsed_data"]["odds_original"] == "11/4"
        assert result["parsed_data"]["odds_decimal"] == 3.75

    def test_decimal_odds(self):
        result = parse_message("Liverpool 2.50", "Nug")
        assert result["type"] == "pick"
        assert result["parsed_data"]["odds_original"] == "2.50"
        assert result["parsed_data"]["odds_decimal"] == 2.50

    def test_evens(self):
        result = parse_message("Chelsea evens", "Pawn")
        assert result["type"] == "pick"
        assert result["parsed_data"]["odds_original"] == "evens"
        assert result["parsed_data"]["odds_decimal"] == 2.0

    def test_btts_detection(self):
        result = parse_message("Man City Brentford BTTS 8/11", "Ed")
        assert result["type"] == "pick"
        assert result["parsed_data"]["bet_type"] == "btts"

    def test_over_under_detection(self):
        result = parse_message("Ireland v England under 2.5 goals 6/4", "Kev")
        assert result["type"] == "pick"
        assert result["parsed_data"]["bet_type"] == "over_under"

    def test_handicap_detection(self):
        result = parse_message("Munster -13 at 4/5", "Nialler")
        assert result["type"] == "pick"
        assert result["parsed_data"]["bet_type"] == "handicap"

    def test_ht_ft_detection(self):
        result = parse_message("Liverpool HT/FT 3/1", "Pawn")
        assert result["type"] == "pick"
        assert result["parsed_data"]["bet_type"] == "ht_ft"

    def test_pick_with_emoji(self):
        result = parse_message("\u26bd Manchester United 2/1", "Kev")
        assert result["type"] == "pick"
        assert result["parsed_data"]["odds_original"] == "2/1"

    def test_pick_without_odds_handicap(self):
        """Handicap-style pick without explicit odds (placer confirms at bookie)."""
        result = parse_message("Scotland + 8", "DA")
        assert result["type"] == "pick"
        assert result["parsed_data"]["odds_original"] == "placer"
        assert result["parsed_data"]["odds_decimal"] == 2.0
        assert result["parsed_data"]["bet_type"] == "handicap"

    def test_pick_without_odds_to_beat(self):
        """Win bet without odds."""
        result = parse_message("Dortmund to beat Mainz", "Pawn")
        assert result["type"] == "pick"
        assert result["parsed_data"]["odds_original"] == "placer"

    def test_general_chat_not_parsed_as_pick(self):
        """Short casual messages should not be parsed as picks."""
        result = parse_message("nice one", "Kev")
        assert result["type"] == "general"

    def test_pick_without_odds_btts(self):
        """BTTS pick without odds."""
        result = parse_message("Leicester Southampton BTTS", "Ed")
        assert result["type"] == "pick"
        assert result["parsed_data"]["odds_original"] == "placer"
        assert result["parsed_data"]["bet_type"] == "btts"


class TestResultParsing:
    def test_win_result(self):
        result = parse_message("Kev \u2705", "Ed")
        assert result["type"] == "result"
        assert result["parsed_data"]["player_nickname"] == "kev"
        assert result["parsed_data"]["outcome"] == "win"

    def test_loss_result(self):
        result = parse_message("DA \u274c", "Ed")
        assert result["type"] == "result"
        assert result["parsed_data"]["player_nickname"] == "da"
        assert result["parsed_data"]["outcome"] == "loss"

    def test_nug_result(self):
        result = parse_message("Nug \u2705", "Ed")
        assert result["type"] == "result"
        assert result["parsed_data"]["player_nickname"] == "nug"

    def test_pawn_result(self):
        result = parse_message("Pawn \u274c", "Ed")
        assert result["type"] == "result"
        assert result["parsed_data"]["player_nickname"] == "pawn"

    def test_nialler_result(self):
        result = parse_message("Nialler \u2705", "Ed")
        assert result["type"] == "result"
        assert result["parsed_data"]["player_nickname"] == "nialler"

    def test_aidan_result_not_da(self):
        """Aidan must match Aidan, not DA (da is substring of aidan)."""
        result = parse_message("Aidan \u274c", "Ed")
        assert result["type"] == "result"
        assert result["parsed_data"]["player_nickname"] == "aidan"
        assert result["parsed_data"]["outcome"] == "loss"


class TestGeneralMessages:
    def test_regular_chat(self):
        result = parse_message("hey lads, what's the story", "Kev")
        assert result["type"] == "general"

    def test_empty_message(self):
        result = parse_message("", "Kev")
        assert result["type"] == "general"

    def test_whitespace_only(self):
        result = parse_message("   ", "Kev")
        assert result["type"] == "general"

    def test_sender_preserved(self):
        result = parse_message("hello", "Nialler")
        assert result["sender"] == "Nialler"

    def test_raw_text_preserved(self):
        result = parse_message("!stats", "Ed")
        assert result["raw_text"] == "!stats"

    def test_sender_phone_preserved(self):
        result = parse_message("hello", "Kev", "353861234567@c.us")
        assert result["sender_phone"] == "353861234567@c.us"

    def test_sender_phone_default_empty(self):
        result = parse_message("hello", "Kev")
        assert result["sender_phone"] == ""


class TestTestMode:
    def test_prefix_extraction_when_enabled(self):
        os.environ["TEST_MODE"] = "true"
        from src.config import Config
        Config.TEST_MODE = True

        sender_override, body = extract_test_prefix("Kev: Manchester United 2/1")
        assert sender_override.lower() == "kev"
        assert body == "Manchester United 2/1"

    def test_prefix_extraction_with_command(self):
        from src.config import Config
        Config.TEST_MODE = True

        sender_override, body = extract_test_prefix("Ed: !confirm penalty Nialler")
        assert sender_override.lower() == "ed"
        assert body == "!confirm penalty Nialler"

    def test_prefix_extraction_result(self):
        from src.config import Config
        Config.TEST_MODE = True

        sender_override, body = extract_test_prefix("Ed: Kev \u2705")
        assert sender_override.lower() == "ed"
        assert body == "Kev \u2705"

    def test_no_prefix_when_disabled(self):
        from src.config import Config
        Config.TEST_MODE = False

        sender_override, body = extract_test_prefix("Kev: Manchester United 2/1")
        assert sender_override is None
        assert body == "Kev: Manchester United 2/1"

    def test_non_player_prefix_ignored(self):
        from src.config import Config
        Config.TEST_MODE = True

        sender_override, body = extract_test_prefix("John: Manchester United 2/1")
        assert sender_override is None
        assert body == "John: Manchester United 2/1"

    def test_full_parse_with_prefix(self):
        from src.config import Config
        Config.TEST_MODE = True

        result = parse_message("Kev: Manchester United 2/1", "Aidan")
        assert result["type"] == "pick"
        assert result["sender"].lower() == "kev"
        assert result["parsed_data"]["odds_original"] == "2/1"

        Config.TEST_MODE = False


class TestCumulativePicks:
    """Cumulative format: emoji + pick per line."""

    def test_single_line_with_emoji(self):
        emoji_map = {"\u265f\ufe0f": {"id": 1, "nickname": "Pawn", "formal_name": "Mr Aidan"}}
        results = parse_cumulative_picks("\u265f\ufe0f Dortmund to beat Mainz 6/10", emoji_map)
        assert len(results) == 1
        player, data = results[0]
        assert player["nickname"] == "Pawn"
        assert data["odds_original"] == "6/10"
        assert "Dortmund" in data["description"]

    def test_multiple_lines(self):
        emoji_map = {
            "\u265f\ufe0f": {"id": 1, "nickname": "Pawn", "formal_name": "Mr Aidan"},
            "\U0001f0cf": {"id": 2, "nickname": "Kev", "formal_name": "Mr Kevin"},
        }
        text = "\u265f\ufe0f Dortmund 6/10\n\U0001f0cf Liverpool 2/1"
        results = parse_cumulative_picks(text, emoji_map)
        assert len(results) == 2
        assert results[0][0]["nickname"] == "Pawn"
        assert results[0][1]["odds_original"] == "6/10"
        assert results[1][0]["nickname"] == "Kev"
        assert results[1][1]["odds_original"] == "2/1"

    def test_empty_emoji_map_returns_nothing(self):
        results = parse_cumulative_picks("\u265f\ufe0f Dortmund 6/10", {})
        assert results == []

    def test_lines_without_matching_emoji_skipped(self):
        emoji_map = {"\u265f\ufe0f": {"id": 1, "nickname": "Pawn", "formal_name": "Mr Aidan"}}
        results = parse_cumulative_picks(
            "\u265f\ufe0f Dortmund 6/10\nRandom text without emoji\n\U0001f0cf Liverpool 2/1",
            emoji_map,
        )
        assert len(results) == 1


class TestSportDetection:
    """Sport detection from pick text."""

    def test_default_football(self):
        assert detect_sport("Liverpool 2/1") == "football"

    def test_default_football_to_beat(self):
        assert detect_sport("Arsenal to beat Chelsea") == "football"

    def test_rugby_keyword(self):
        assert detect_sport("Munster -13 at 4/5") == "rugby"

    def test_rugby_six_nations(self):
        assert detect_sport("Ireland Six Nations 2/1") == "rugby"

    def test_rugby_province(self):
        assert detect_sport("Leinster to beat Ulster") == "rugby"

    def test_nfl_team(self):
        assert detect_sport("Chiefs to beat Eagles 3/1") == "nfl"

    def test_nfl_keyword(self):
        assert detect_sport("NFL Super Bowl over 45.5") == "nfl"

    def test_nba_team(self):
        assert detect_sport("Lakers 2/1") == "nba"

    def test_nba_keyword(self):
        assert detect_sport("NBA Celtics -5.5") == "nba"

    def test_nhl_team(self):
        assert detect_sport("Maple Leafs to win 6/4") == "nhl"

    def test_mma_keyword(self):
        assert detect_sport("UFC 300 main event by KO 3/1") == "mma"

    def test_mma_weight_class(self):
        assert detect_sport("Heavyweight bout by decision 5/2") == "mma"

    def test_tennis_keyword(self):
        assert detect_sport("Wimbledon Djokovic 4/6") == "tennis"

    def test_golf_keyword(self):
        assert detect_sport("Masters Tiger Woods top 10 finish") == "golf"

    def test_golf_pga(self):
        assert detect_sport("Rory McIlroy top 5 finish PGA") == "golf"

    def test_boxing_keyword(self):
        assert detect_sport("Boxing Fury by stoppage 5/4") == "boxing"

    def test_darts_keyword(self):
        assert detect_sport("PDC World Darts 6/1") == "darts"

    def test_gaa_keyword_defaults_football(self):
        assert detect_sport("GAA All-Ireland Dublin 2/1") == "gaa_football"

    def test_gaa_hurling_keyword(self):
        assert detect_sport("Dublin hurling 3/1") == "gaa_hurling"

    def test_gaa_camogie(self):
        assert detect_sport("Camogie final 5/2") == "gaa_hurling"

    def test_gaa_liam_maccarthy(self):
        assert detect_sport("Liam MacCarthy Cup 4/1") == "gaa_hurling"

    def test_gaa_sam_maguire(self):
        assert detect_sport("Sam Maguire final 3/1") == "gaa_football"

    def test_gaa_football_county_cavan(self):
        assert detect_sport("Cavan evens") == "gaa_football"

    def test_gaa_football_county_tyrone(self):
        assert detect_sport("Tyrone +2 11/10") == "gaa_football"

    def test_gaa_hurling_county_kilkenny(self):
        assert detect_sport("Kilkenny 2/1") == "gaa_hurling"

    def test_gaa_hurling_county_wexford(self):
        assert detect_sport("Wexford 5/2") == "gaa_hurling"

    def test_gaa_dual_county_defaults_football(self):
        assert detect_sport("Dublin +2 11/10") == "gaa_football"

    def test_gaa_dual_county_with_hurling_keyword(self):
        assert detect_sport("Dublin hurling 3/1") == "gaa_hurling"

    def test_gaa_dual_county_cork(self):
        assert detect_sport("Cork 6/4") == "gaa_football"

    def test_gaa_dual_county_cork_hurling(self):
        assert detect_sport("Cork hurling 6/4") == "gaa_hurling"

    def test_football_not_affected(self):
        """Soccer picks must still detect as football, not GAA."""
        assert detect_sport("Arsenal 6/4") == "football"

    def test_liverpool_still_football(self):
        assert detect_sport("Liverpool 2/1") == "football"

    def test_gaa_generic_keyword(self):
        assert detect_sport("GAA this weekend 3/1") == "gaa_football"

    def test_all_ireland_defaults_football(self):
        assert detect_sport("All-Ireland semi-final 5/1") == "gaa_football"

    def test_gaa_needs_clarification_dual_county(self):
        assert gaa_needs_clarification("Dublin +2 11/10") is True

    def test_gaa_needs_clarification_explicit_hurling(self):
        assert gaa_needs_clarification("Dublin hurling 3/1") is False

    def test_gaa_needs_clarification_football_county(self):
        assert gaa_needs_clarification("Cavan evens") is False

    def test_gaa_needs_clarification_hurling_county(self):
        assert gaa_needs_clarification("Kilkenny 2/1") is False

    def test_gaa_needs_clarification_gaa_keyword(self):
        assert gaa_needs_clarification("GAA Dublin 2/1") is False

    def test_gaa_sport_in_parsed_pick(self):
        """GAA county picks should have gaa_football/gaa_hurling sport."""
        result = parse_message("Dublin +2 11/10", "Kev")
        assert result["type"] == "pick"
        assert result["parsed_data"]["sport"] == "gaa_football"

    def test_horse_racing_keyword(self):
        assert detect_sport("Cheltenham Gold Cup 8/1") == "horse_racing"

    def test_horse_racing_grand_national(self):
        assert detect_sport("Grand National each way 10/1") == "horse_racing"

    def test_empty_string_defaults_football(self):
        assert detect_sport("") == "football"

    def test_none_defaults_football(self):
        assert detect_sport(None) == "football"

    def test_sport_in_parsed_pick(self):
        """Sport field should be included in parsed pick data."""
        result = parse_message("Munster -13 at 4/5", "Nialler")
        assert result["type"] == "pick"
        assert result["parsed_data"]["sport"] == "rugby"

    def test_football_pick_sport_field(self):
        result = parse_message("Liverpool 2/1", "Kev")
        assert result["type"] == "pick"
        assert result["parsed_data"]["sport"] == "football"

    def test_nfl_pick_sport_field(self):
        result = parse_message("Chiefs -3.5 evens", "DA")
        assert result["type"] == "pick"
        assert result["parsed_data"]["sport"] == "nfl"
