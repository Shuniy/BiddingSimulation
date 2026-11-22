from __future__ import annotations

import types

import pytest

from backend.simulator import DynamicAuctionGame, PlayerConfig


class FixedBidBot:
    name = "fixed"

    def __init__(self, bid):
        self.bid = bid

    def get_bid(self, **kwargs):
        return self.bid


def make_game(players, round_limit=1, seed=1):
    game = DynamicAuctionGame(
        game_id="test",
        players=[
            PlayerConfig("A", "bots.flat_bot_10", 100),
            PlayerConfig("B", "bots.flat_bot_15", 100),
        ],
        round_limit=round_limit,
        seed=seed,
        tick_ms=0,
    )
    for player, bot in zip(game.players, players):
        player.bot_instance = bot
        player.bot_name = bot.name
    return game


def test_product_scoring_uses_all_artists():
    game = make_game([FixedBidBot(0), FixedBidBot(0)])
    player = game.players[0]
    player.paintings = {
        "Da Vinci": 3,
        "Picasso": 2,
        "Rembrandt": 4,
        "Van Gogh": 5,
    }

    game._update_scores()

    assert player.score == 120


def test_highest_bid_wins_and_pays_own_bid():
    game = make_game([FixedBidBot(10), FixedBidBot(15)], seed=4)
    events = list(game.event_stream())
    round_event = next(event for event in events if event["type"] == "round_finished")

    assert round_event["winnerId"] == game.players[1].id
    assert round_event["amountPaid"] == 15
    assert game.players[1].budget == 85


def test_round_limit_stops_exactly_on_selected_round():
    game = make_game([FixedBidBot(1), FixedBidBot(2)], round_limit=3)
    events = list(game.event_stream())
    rounds = [event for event in events if event["type"] == "round_finished"]

    assert [event["round"] for event in rounds] == [1, 2, 3]
    assert events[-1]["type"] == "game_finished"


def test_custom_budgets_initialise_per_player():
    game = DynamicAuctionGame(
        game_id="budget",
        players=[
            PlayerConfig("A", "bots.flat_bot_10", 40),
            PlayerConfig("B", "bots.flat_bot_15", 90),
        ],
        round_limit=1,
        seed=1,
        tick_ms=0,
    )

    assert [player.budget for player in game.players] == [40, 90]
    assert [player.starting_budget for player in game.players] == [40, 90]


@pytest.mark.parametrize("bad_bid", [500, -1, "bad"])
def test_invalid_bids_become_zero(bad_bid):
    class BadBot:
        name = "bad"

        def get_bid(self, **kwargs):
            return bad_bid

    game = make_game([BadBot(), FixedBidBot(1)])
    events = list(game.event_stream())
    round_event = next(event for event in events if event["type"] == "round_finished")

    assert round_event["bids"][game.players[0].id] == 0


def test_crashing_bot_emits_error_and_bids_zero():
    class CrashBot:
        name = "crash"

        def get_bid(self, **kwargs):
            raise RuntimeError("boom")

    game = make_game([CrashBot(), FixedBidBot(1)])
    events = list(game.event_stream())
    error = next(event for event in events if event["type"] == "bot_error")
    round_event = next(event for event in events if event["type"] == "round_finished")

    assert error["playerId"] == game.players[0].id
    assert round_event["bids"][game.players[0].id] == 0


def test_seeded_tie_break_is_deterministic():
    first = make_game([FixedBidBot(5), FixedBidBot(5)], seed=7)
    second = make_game([FixedBidBot(5), FixedBidBot(5)], seed=7)

    first_winner = next(
        event for event in first.event_stream() if event["type"] == "round_finished"
    )["winnerId"]
    second_winner = next(
        event for event in second.event_stream() if event["type"] == "round_finished"
    )["winnerId"]

    assert first_winner == second_winner

