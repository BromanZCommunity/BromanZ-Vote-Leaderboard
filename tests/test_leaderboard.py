import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from vote_leaderboard import (
    DiscordWebhookError,
    build_previous_embed,
    normalize_players,
    previous_month_key,
    ranking_lines,
    upsert_message,
    validate_webhook_url,
    webhook_url_for,
)


class LeaderboardTests(unittest.TestCase):
    def test_players_response_and_deterministic_sort(self):
        players = normalize_players({
            "players": [
                {"playername": "Bravo", "votes": 4, "position": 2},
                {"playername": "Alpha", "votes": 7, "position": 1},
            ]
        })
        self.assertEqual([player.name for player in players], ["Alpha", "Bravo"])
        self.assertEqual([player.position for player in players], [1, 2])

    def test_supported_api_response_shapes(self):
        direct = normalize_players([{"playername": "One", "votes": 1}])
        nested = normalize_players({"data": [{"playername": "Two", "votes": "2"}]})
        self.assertEqual(direct[0].name, "One")
        self.assertEqual(nested[0].votes, 2)

    def test_ranking_text_escapes_mentions_and_markdown(self):
        players = normalize_players([
            {"playername": "@One_*", "votes": 3},
            {"playername": "Two", "votes": 2},
            {"playername": "Three", "votes": 1},
        ])
        lines = ranking_lines(players, 3)
        self.assertTrue(lines[0].startswith("🥇"))
        self.assertIn("＠One\\_\\*", lines[0])
        self.assertTrue(lines[1].startswith("🥈"))
        self.assertTrue(lines[2].startswith("🥉"))

    def test_previous_month_across_year_boundary(self):
        now = datetime(2027, 1, 2, 12, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
        self.assertEqual(previous_month_key(now), "2026-12")

    def test_previous_board_waiting_state(self):
        embed = build_previous_embed(None, "2026-08", 20)
        self.assertIn("August 2026", embed["description"])

    def test_webhook_url_validation_and_message_url(self):
        webhook = validate_webhook_url("https://discord.com/api/webhooks/123/secret")
        self.assertEqual(
            webhook_url_for(webhook, message_id="456"),
            "https://discord.com/api/webhooks/123/secret/messages/456",
        )
        self.assertEqual(
            webhook_url_for(webhook, wait=True),
            "https://discord.com/api/webhooks/123/secret?wait=true",
        )

    def test_invalid_webhook_is_rejected(self):
        with self.assertRaises(Exception):
            validate_webhook_url("https://example.com/api/webhooks/123/secret")

    @patch("vote_leaderboard.save_state")
    @patch("vote_leaderboard.create_message", return_value="new-id")
    @patch("vote_leaderboard.edit_message", side_effect=DiscordWebhookError(404, "missing"))
    def test_deleted_message_is_recreated(self, _edit, _create, save_state):
        state = {"current_message_id": "old-id"}
        upsert_message(state, "current_message_id", "https://discord.com/api/webhooks/123/secret", {})
        self.assertEqual(state["current_message_id"], "new-id")
        save_state.assert_called_once_with(state)


if __name__ == "__main__":
    unittest.main()
