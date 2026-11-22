from __future__ import annotations

import csv
import random
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

import auctioneer
from backend.bot_registry import BOT_NAMES, load_bot_module
from backend.simulator import ARTISTS, DynamicAuctionGame, PlayerConfig
from benchmark import Scenario, run_experiment, run_trial, summarize
from utilities import export_to_csv


class ControlledBot:
    name = "Controlled bot"

    def __init__(self, calls=None, bid=None):
        self._calls = calls
        self._bid = bid

    def __deepcopy__(self, _memo):
        return ControlledBot(bid=self._bid)

    def get_bid(self, **info):
        if self._calls is not None:
            own = info["my_bot_details"]
            assert isinstance(own.pop("bot_instance"), ControlledBot)
            self._calls.append(info)
        return self._bid


@pytest.mark.parametrize("explicit_order", [False, True])
def test_coursework_parity_for_inputs_order_and_outcomes(tmp_path, monkeypatch, explicit_order):
    seed = 33
    rng = random.Random(seed)
    monkeypatch.setattr(
        auctioneer,
        "random",
        SimpleNamespace(seed=lambda: None, randint=rng.randint, random=rng.random),
    )
    bid_values = [-10, 10, 10, 0, "non-numeric", 10**500, 2.9]
    original_calls = []
    simulator_calls = []
    room = [
        SimpleNamespace(Bot=lambda bid=bid: ControlledBot(original_calls, bid))
        for bid in bid_values
    ]
    log = tmp_path / "fresh" / "reference.csv"
    order = list(ARTISTS) * 50 if explicit_order else None
    original = auctioneer.Auctioneer(
        room=room, painting_order=order, output_csv_file=log, verbose=False, slowdown=0
    )
    original.error_log_csv_file = tmp_path / "errors.csv"
    game = DynamicAuctionGame(
        "test",
        [PlayerConfig(str(seat), "bots.flat_bot_10", 1001) for seat in range(len(room))],
        seed=seed,
        tick_ms=0,
        mode="reference",
        painting_order=order,
    )
    # Sentinel strategy retains the same public ID and bidding behavior in both engines.
    for index, (player, bid) in enumerate(zip(game.players, bid_values), start=1):
        player.id = f"Controlled bot-{index}"
        player.bot_name = ControlledBot.name
        player.bot_instance = ControlledBot(simulator_calls, bid)

    winners = original.run_auction()
    events = list(game.event_stream())
    assert game.painting_order == original.painting_order
    assert simulator_calls == original_calls
    assert game.amounts_paid == original.amounts_paid
    assert game.winner_ids == original.winner_ids
    assert events[-1]["winners"] == winners
    assert game.current_round == original.current_round == 200
    original_players = {player["bot_unique_id"]: player for player in original.bots}
    for player in game.players:
        assert player.budget == original_players[player.id]["budget"]
        assert player.paintings == original_players[player.id]["paintings"]
        assert player.score == original_players[player.id]["score"]
    with log.open() as file:
        assert len(list(csv.reader(file, delimiter=";"))) == 200


def test_reference_negative_payment_versus_custom_rejection():
    modules = [PlayerConfig(str(seat), "bots.flat_bot_10", 1001) for seat in range(2)]
    for mode in ("reference", "custom"):
        game = DynamicAuctionGame("test", modules, tick_ms=0, seed=1, mode=mode)
        for player, bid in zip(game.players, [-9, -3]):
            player.bot_instance = ControlledBot(bid=bid)
        stream = game.event_stream()
        payment = next(event["amountPaid"] for event in stream if event["type"] == "round_finished")
        stream.close()
        assert payment == (-3 if mode == "reference" else 0)
        assert game.players[1].budget == (1004 if mode == "reference" else 1001)


def test_collection_hint_does_not_end_game_and_top_score_can_be_shared():
    game = DynamicAuctionGame(
        "test",
        [PlayerConfig(str(seat), "bots.flat_bot_10", 1001) for seat in range(2)],
        round_limit=80,
        tick_ms=0,
        seed=1,
        painting_order=[ARTISTS[index // 2 % 4] for index in range(80)],
    )
    for seat, player in enumerate(game.players):
        player.bot_instance = SimpleNamespace(
            get_bid=lambda current_round, seat=seat, **_: int(current_round % 2 == seat)
        )
    events = list(game.event_stream())
    assert game.current_round == 80
    assert [player.score for player in game.players] == [10_000, 10_000]
    assert events[-1]["winners"] == [player.id for player in game.players]


def test_zero_bid_assigns_art_and_exhausted_bot_cannot_overspend():
    game = DynamicAuctionGame(
        "test",
        [PlayerConfig(str(seat), "bots.flat_bot_10", 1) for seat in range(3)],
        round_limit=4,
        seed=91,
        tick_ms=0,
    )
    for player in game.players:
        player.bot_instance = ControlledBot(bid=1.9)
    events = list(game.event_stream())
    rounds = [event for event in events if event["type"] == "round_finished"]
    assert game.amounts_paid == [1, 1, 1, 0]
    assert all(bid == 0 for bid in rounds[-1]["bids"].values())
    assert sum(sum(player.paintings.values()) for player in game.players) == 4
    assert all(player.budget == 0 for player in game.players)


@pytest.mark.parametrize("bid", ["8.5", float("nan"), float("inf"), 10**500])
def test_nonconvertible_or_overbudget_bids_become_zero(bid):
    game = DynamicAuctionGame(
        "test",
        [PlayerConfig(str(seat), "bots.flat_bot_10", 12) for seat in range(2)],
        round_limit=1,
        seed=1,
        tick_ms=0,
    )
    game.players[0].bot_instance = ControlledBot(bid=bid)
    events = list(game.event_stream())
    assert events[1]["type"] == "bot_error"
    assert events[2]["bids"][game.players[0].id] == 0


@pytest.mark.parametrize(
    "room",
    [
        ("random_bot", "random_bot", "random_bot"),
        ("random_bot", "u5726455_i2", "u5726455_final", "flat_bot_15"),
    ],
)
def test_seeded_local_simulations_and_global_rng_isolation(room):
    configurations = [PlayerConfig(name, f"bots.{name}", 1001) for name in room]

    def run(seed):
        game = DynamicAuctionGame("same-id", configurations, 32, seed, 0)
        return list(game.event_stream())

    original = random.getstate()
    with ThreadPoolExecutor(max_workers=3) as pool:
        first, second, third = pool.map(run, [3, 3, 6])
    assert first == second
    assert first != third
    assert random.getstate() == original


@pytest.mark.parametrize("module", list(BOT_NAMES))
def test_duplicate_strategy_uses_own_budget_when_seat_order_changes(module):
    game = DynamicAuctionGame(
        "test",
        [PlayerConfig("Same name", module, 1001) for _ in range(2)],
        round_limit=12,
        seed=5,
        tick_ms=0,
    )
    first, second = game.players
    first.budget = 0
    second.budget = 1001
    first.paintings = dict.fromkeys(ARTISTS, 1)
    first.score = 1
    second.paintings = dict.fromkeys(ARTISTS, 2)
    second.score = 16
    game.current_round = 3
    game.winner_ids = [first.id, second.id, first.id]
    game.amounts_paid = [12, 26, 9]
    game._bid_order.reverse()
    bids, errors = game._collect_bids()
    if "flat_bot" in module:
        assert [(error["playerId"], error["message"]) for error in errors] == [
            (first.id, "Over-budget bid changed to 0")
        ]
    else:
        assert not errors
    assert bids[0] > 0
    assert bids[1] == 0
    assert first.id != second.id


@pytest.mark.parametrize(
    "module", ["bots.u5726455_i2", "bots.u5726455_final", "bots.u5726455_i_i2"]
)
def test_duplicate_state_uses_expected_collection_score_and_history(module, monkeypatch):
    game = DynamicAuctionGame(
        "test", [PlayerConfig("Same name", module, 1001) for _ in range(2)], 8, 2, 0
    )
    one, two = game.players
    for seat, player in enumerate(game.players, start=1):
        player.budget = 500 * seat
        player.paintings = dict.fromkeys(ARTISTS, seat)
        player.score = seat**4
        original = player.bot_instance.build_state

        def verify_state(*args, player=player, original=original, **kwargs):
            state = original(*args, **kwargs)
            assert state["my_id"] == player.id
            assert state["my_budget"] == player.budget
            assert state["my_score"] == player.score
            assert state["my_paintings"] == player.paintings
            assert state["winner_ids"] == [one.id, two.id]
            assert [opponent["bot_unique_id"] for opponent in state["opponents"]] != [player.id]
            return state

        monkeypatch.setattr(player.bot_instance, "build_state", verify_state)
    game.current_round = 2
    game.winner_ids = [one.id, two.id]
    game.amounts_paid = [9, 19]
    _, errors = game._collect_bids()
    assert not errors


def test_discovered_strategies_have_valid_class_and_names():
    for module, name in BOT_NAMES.items():
        bot = load_bot_module(module).Bot()
        assert bot.name == name
        assert callable(bot.get_bid)


def test_benchmark_zero_score_never_counts_as_win_and_is_reproducible():
    case = Scenario("Two duplicates", ("bots.flat_bot_10", "bots.flat_bot_10"), 1)
    report = run_experiment([case], [1, 2])
    assert report == run_experiment([case], [1, 2])
    assert report[0]["summary"]["no_winner"] == 4
    assert report[0]["summary"]["win_rate"] == 0
    assert {trial["focus_seat"] for trial in report[0]["trials"]} == {1, 2}
    assert run_trial(case, 3)["outcome"] == "no_winner"


def test_benchmark_tracks_shared_wins_and_budget_efficiency():
    trials = [
        {
            "seed": seed,
            "outcome": outcome,
            "spent": 100,
            "score": score,
            "final_budget": 901,
            "rank": rank,
            "bot_errors": {},
        }
        for seed, outcome, score, rank in (
            (1, "sole_win", 25, 1),
            (2, "shared_win", 20, 1),
            (3, "loss", 10, 2),
            (4, "no_winner", 0, 1),
        )
    ]
    report = summarize(trials)
    assert (
        report["sole_wins"] == report["shared_wins"] == report["losses"] == report["no_winner"] == 1
    )
    assert report["win_rate"] == 0.5
    assert report["median_score"] == 15
    assert report["mean_rank"] == 1.25
    assert report["score_per_credit_spent"] == 55 / 400


def test_csv_relative_and_absolute_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    absolute = tmp_path / "absolute" / "logs" / "example.csv"
    export_to_csv("relative/logs/example.csv", ["x;y", 2])
    export_to_csv(absolute, ["x;y", 2])
    export_to_csv(absolute, ["next", 3])
    assert (tmp_path / "relative/logs/example.csv").read_text() == '"x;y";2\n'
    assert absolute.read_text() == '"x;y";2\nnext;3\n'
