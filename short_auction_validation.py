"""
Short-auction validation sweep focused on stronger baseline-heavy rooms.

This script tests whether `u5726455_i2` really outperforms the other bots in
shorter auctions by repeatedly running rooms built around:
- `random_bot`
- `flat_bot_10`
- `flat_bot_15`
- mixed combinations with the coursework bots
"""

from __future__ import annotations

import copy
import csv
import random
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from bots import flat_bot_10, flat_bot_15, random_bot, u5726455, u5726455_i, u5726455_i2, u5726455_q


ROUND_LIMITS = (50, 75, 100, 150)
RUNS_PER_ROOM = 5
OUTPUT_DIR = Path("data")
DETAIL_CSV = OUTPUT_DIR / "short_auction_validation_results.csv"
SUMMARY_CSV = OUTPUT_DIR / "short_auction_validation_summary.csv"

BOT_CONFIG = {
    "random_bot": {"module": random_bot},
    "flat_bot_10": {"module": flat_bot_10},
    "flat_bot_15": {"module": flat_bot_15},
    "u5726455": {"module": u5726455},
    "u5726455_i": {"module": u5726455_i},
    "u5726455_i2": {"module": u5726455_i2},
    "u5726455_q": {"module": u5726455_q},
}

FOCUS_BOTS = tuple(BOT_CONFIG.keys())
CUSTOM_BOTS = ("u5726455", "u5726455_i", "u5726455_i2", "u5726455_q")


class FixedAuctioneer(object):
    """Local auctioneer clone with configurable round limits and fixed seeds."""

    def __init__(self, room_entries, round_limit, painting_order, seed):
        self.current_round = 0
        self.bots = []
        self.finished = False

        self.room_entries = room_entries
        self.round_limit = round_limit
        self.starting_budget = 1001
        self.winner_pays = 1
        self.artists_and_values = {
            "Da Vinci": 7,
            "Rembrandt": 3,
            "Van Gogh": 12,
            "Picasso": 2,
        }
        self.target_collection = [10, 3, 2, 1]
        self.winner_ids = []
        self.amounts_paid = []
        self.painting_order = list(painting_order)
        self.random = random.Random(seed)

        self._initialise_bots()

    def _initialise_bots(self):
        count = 0
        for label, bot_module in self.room_entries:
            count += 1
            bot_instance = bot_module.Bot()
            bot_unique_id = "{}-{}".format(bot_instance.name, count)
            self.bots.append(
                {
                    "label": label,
                    "bot_instance": bot_instance,
                    "bot_name": copy.deepcopy(bot_instance.name),
                    "bot_unique_id": bot_unique_id,
                    "paintings": {
                        "Da Vinci": 0,
                        "Picasso": 0,
                        "Rembrandt": 0,
                        "Van Gogh": 0,
                    },
                    "budget": self.starting_budget,
                    "current_bid": 0,
                    "score": 0,
                }
            )

    def run_auction(self):
        while not self.finished:
            self._start_round()
            self._collect_bids()
            self._pick_winner_of_the_round()
            self._update_scores()
            self._check_end_conditions()
        return self._summarise_result()

    def _start_round(self):
        for bot in self.bots:
            bot["current_bid"] = 0

    def _collect_bids(self):
        info_for_bots = {
            "current_round": self.current_round,
            "bots": self.bots,
            "winner_pays": self.winner_pays,
            "artists_and_values": self.artists_and_values,
            "round_limit": self.round_limit,
            "starting_budget": self.starting_budget,
            "painting_order": self.painting_order,
            "target_collection": self.target_collection,
            "current_painting": self.painting_order[self.current_round],
            "winner_ids": self.winner_ids,
            "amounts_paid": self.amounts_paid,
        }

        for bot in self.bots:
            info_for_bots_deep_copy = copy.deepcopy(info_for_bots)
            for bot_copy in info_for_bots_deep_copy["bots"]:
                del bot_copy["bot_instance"]
                del bot_copy["current_bid"]
            info_for_bots_deep_copy["my_bot_details"] = copy.deepcopy(bot)

            try:
                bid = int(bot["bot_instance"].get_bid(**info_for_bots_deep_copy))
            except Exception:
                bid = 0

            bot["current_bid"] = bid if bid <= bot["budget"] else 0

    def _pick_winner_of_the_round(self):
        self.bots.sort(
            key=lambda x: (x["current_bid"], self.random.random()),
            reverse=True,
        )
        winner = self.bots[0]
        amount_paid = self.bots[min(self.winner_pays, len(self.bots)) - 1]["current_bid"]
        winner["budget"] -= amount_paid
        self.amounts_paid.append(amount_paid)
        current_painting = self.painting_order[self.current_round]
        winner["paintings"][current_painting] += 1
        self.winner_ids.append(winner["bot_unique_id"])

    def _update_scores(self):
        for bot in self.bots:
            score = 1
            for value in bot["paintings"].values():
                score *= value
            bot["score"] = score

    def _check_end_conditions(self):
        self.current_round += 1
        if self.current_round >= self.round_limit:
            self.finished = True

    def _summarise_result(self):
        best_score = max(bot["score"] for bot in self.bots)
        winners = {bot["label"] for bot in self.bots if bot["score"] == best_score}
        return {
            "winners": winners,
            "scores": {bot["label"]: bot["score"] for bot in self.bots},
            "budgets": {bot["label"]: bot["budget"] for bot in self.bots},
        }


def build_painting_order(round_limit, seed):
    rng = random.Random(seed)
    artists = ["Da Vinci", "Rembrandt", "Van Gogh", "Picasso"]
    return [artists[rng.randint(0, 3)] for _ in range(round_limit)]


def unique_rooms(focus_bot: str) -> list[tuple[str, ...]]:
    """Generate stronger short-auction rooms with baseline-heavy mixes."""

    rooms = [
        (focus_bot, "random_bot", "flat_bot_10", "flat_bot_15"),
        (focus_bot, "random_bot", "random_bot", "flat_bot_10", "flat_bot_15"),
        (focus_bot, "flat_bot_10", "flat_bot_10", "flat_bot_15"),
        (focus_bot, "flat_bot_10", "flat_bot_15", "flat_bot_15"),
        (
            focus_bot,
            "random_bot",
            "flat_bot_10",
            "flat_bot_10",
            "flat_bot_15",
            "flat_bot_15",
        ),
    ]

    others = [bot for bot in CUSTOM_BOTS if bot != focus_bot]
    for other in others:
        rooms.append((focus_bot, other, "random_bot", "flat_bot_10", "flat_bot_15"))

    for other_a, other_b in combinations(others, 2):
        rooms.append(
            (focus_bot, other_a, other_b, "random_bot", "flat_bot_10", "flat_bot_15")
        )

    if focus_bot in CUSTOM_BOTS:
        rooms.append(
            (focus_bot, "u5726455", "u5726455_i", "u5726455_i2", "u5726455_q", "flat_bot_15")
        )

    seen = set()
    deduped = []
    for room in rooms:
        if room not in seen:
            deduped.append(room)
            seen.add(room)
    return deduped


def run_suite():
    bot_names = {key: config["module"].Bot().name for key, config in BOT_CONFIG.items()}
    detail_rows = []
    summary = defaultdict(
        lambda: {
            "games": 0,
            "wins": 0,
            "ties": 0,
            "score_sum": 0,
            "budget_sum": 0,
            "rooms": set(),
        }
    )

    for round_limit in ROUND_LIMITS:
        for focus_bot in FOCUS_BOTS:
            for room in unique_rooms(focus_bot):
                room_entries = [
                    ("{}_slot{}".format(name, index), BOT_CONFIG[name]["module"])
                    for index, name in enumerate(room)
                ]
                focus_label = "{}_slot0".format(focus_bot)
                room_name = " | ".join(bot_names[bot] for bot in room)

                for run_index in range(RUNS_PER_ROOM):
                    seed = round_limit * 10000 + len(room) * 1000 + run_index
                    painting_order = build_painting_order(round_limit, seed)
                    game = FixedAuctioneer(
                        room_entries=room_entries,
                        round_limit=round_limit,
                        painting_order=painting_order,
                        seed=seed + 17,
                    )
                    result = game.run_auction()

                    won = focus_label in result["winners"]
                    key = (round_limit, focus_bot)
                    summary[key]["games"] += 1
                    summary[key]["wins"] += int(won)
                    summary[key]["ties"] += int(won and len(result["winners"]) > 1)
                    summary[key]["score_sum"] += result["scores"][focus_label]
                    summary[key]["budget_sum"] += result["budgets"][focus_label]
                    summary[key]["rooms"].add(room_name)

                    detail_rows.append(
                        [
                            round_limit,
                            bot_names[focus_bot],
                            room_name,
                            len(room),
                            run_index,
                            int(won),
                            int(won and len(result["winners"]) > 1),
                            result["scores"][focus_label],
                            result["budgets"][focus_label],
                        ]
                    )

    summary_rows = []
    for round_limit in ROUND_LIMITS:
        for focus_bot in FOCUS_BOTS:
            stats = summary[(round_limit, focus_bot)]
            games = stats["games"]
            summary_rows.append(
                [
                    round_limit,
                    bot_names[focus_bot],
                    len(stats["rooms"]),
                    games,
                    stats["wins"],
                    stats["ties"],
                    round(stats["wins"] / games, 4) if games else 0.0,
                    round(stats["score_sum"] / games, 2) if games else 0.0,
                    round(stats["budget_sum"] / games, 2) if games else 0.0,
                ]
            )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with DETAIL_CSV.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "round_limit",
                "focus_bot",
                "room",
                "room_size",
                "run_index",
                "won",
                "shared_win",
                "score",
                "budget_left",
            ]
        )
        writer.writerows(detail_rows)

    with SUMMARY_CSV.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "round_limit",
                "focus_bot",
                "rooms_tested",
                "total_games",
                "wins",
                "shared_wins",
                "win_rate",
                "average_score",
                "average_budget_left",
            ]
        )
        writer.writerows(summary_rows)

    print(f"Wrote detailed results to {DETAIL_CSV}")
    print(f"Wrote summary results to {SUMMARY_CSV}")


if __name__ == "__main__":
    run_suite()
