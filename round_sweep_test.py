"""
Stress-test sweep across multiple auction lengths.

This follows the same seminar-style pattern used in the earlier stress tests:
- repeated runs
- baseline rooms against `random_bot` and `flat_bot_10`
- rooms with multiple flat bots
- mixed rooms combining the coursework bots with each other

The standard auctioneer hardcodes 200 rounds, so this script carries a local
copy of the auction loop with a configurable `round_limit`.
"""

from __future__ import annotations

import copy
import csv
import random
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from bots import flat_bot_10, random_bot, u5726455, u5726455_i, u5726455_q


ROUND_LIMITS = (50, 100, 150, 200, 250)
RUNS_PER_ROOM = 5
OUTPUT_DIR = Path("data")
DETAIL_CSV = OUTPUT_DIR / "round_sweep_results.csv"
SUMMARY_CSV = OUTPUT_DIR / "round_sweep_summary.csv"

BOT_CONFIG = {
    "random_bot": {"module": random_bot},
    "flat_bot_10": {"module": flat_bot_10},
    "u5726455": {"module": u5726455},
    "u5726455_i": {"module": u5726455_i},
    "u5726455_q": {"module": u5726455_q},
}

FOCUS_BOTS = tuple(BOT_CONFIG.keys())


class RoundSweepAuctioneer(object):
    """Minimal local auctioneer clone with configurable round limits."""

    def __init__(self, room, round_limit, painting_order=None):
        self.current_round = 0
        self.bots = []
        self.finished = False

        self.room = room
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

        random.seed()
        if painting_order is None:
            artists = list(self.artists_and_values.keys())
            self.painting_order = [
                artists[random.randint(0, 3)] for _ in range(self.round_limit)
            ]
        else:
            self.painting_order = painting_order

        self._initialise_bots()

    def _initialise_bots(self):
        count = 0
        for bot_module in self.room:
            count += 1
            bot_instance = bot_module.Bot()
            bot_unique_id = "{}-{}".format(bot_instance.name, count)
            self.bots.append(
                {
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
        return self._get_winners()

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

            if bid <= bot["budget"]:
                bot["current_bid"] = bid
            else:
                bot["current_bid"] = 0

    def _pick_winner_of_the_round(self):
        self.bots.sort(key=lambda x: (x["current_bid"], random.random()), reverse=True)
        winner = self.bots[0]
        amount_paid = self.bots[min(self.winner_pays, len(self.bots)) - 1]["current_bid"]
        winner["budget"] -= amount_paid
        self.amounts_paid.append(amount_paid)
        current_painting = self.painting_order[self.current_round]
        winner["paintings"][current_painting] += 1
        self.winner_ids.append(winner["bot_unique_id"])

    def _update_scores(self):
        for bot in self.bots:
            bot_score = 1
            for value in bot["paintings"].values():
                bot_score *= value
            bot["score"] = bot_score

    def _check_end_conditions(self):
        self.current_round += 1
        if self.current_round >= self.round_limit:
            self.finished = True

    def _get_winners(self):
        winning_score = max(bot["score"] for bot in self.bots)
        if winning_score > 0:
            return [bot["bot_name"] for bot in self.bots if bot["score"] == winning_score]
        return []


def unique_rooms(focus_bot: str) -> list[tuple[str, ...]]:
    """Generate a diverse, deduplicated seminar-style set of rooms."""

    others = [name for name in FOCUS_BOTS if name != focus_bot]
    rooms = [
        (focus_bot, "random_bot"),
        (focus_bot, "flat_bot_10"),
        (focus_bot, "flat_bot_10", "flat_bot_10", "flat_bot_10"),
        (focus_bot, "random_bot", "flat_bot_10"),
        (focus_bot, "flat_bot_10", "flat_bot_10", "random_bot", "random_bot"),
    ]

    for other in others:
        rooms.append((focus_bot, other))
        rooms.append((focus_bot, other, "random_bot"))
        rooms.append((focus_bot, other, "flat_bot_10"))
        rooms.append((focus_bot, other, "random_bot", "flat_bot_10"))

    for other_a, other_b in combinations(others, 2):
        rooms.append((focus_bot, other_a, other_b))
        rooms.append((focus_bot, other_a, other_b, "flat_bot_10"))
        rooms.append((focus_bot, other_a, other_b, "random_bot"))

    seen = set()
    deduped_rooms = []
    for room in rooms:
        if room not in seen:
            deduped_rooms.append(room)
            seen.add(room)
    return deduped_rooms


def run_room(room_bot_names: tuple[str, ...], round_limit: int) -> tuple[int, int]:
    room_modules = [BOT_CONFIG[name]["module"] for name in room_bot_names]
    focus_name = room_modules[0].Bot().name
    focus_wins = 0
    shared_wins = 0

    for _ in range(RUNS_PER_ROOM):
        game = RoundSweepAuctioneer(room=room_modules, round_limit=round_limit)
        winners = game.run_auction()
        if focus_name in winners:
            focus_wins += 1
            if len(winners) > 1:
                shared_wins += 1

    return focus_wins, shared_wins


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def main() -> None:
    bot_names = {key: config["module"].Bot().name for key, config in BOT_CONFIG.items()}
    detail_rows: list[list[object]] = []
    summary = defaultdict(lambda: {"rooms": 0, "runs": 0, "wins": 0, "shared": 0})

    for round_limit in ROUND_LIMITS:
        for focus_bot in FOCUS_BOTS:
            for room in unique_rooms(focus_bot):
                focus_wins, shared_wins = run_room(room, round_limit)
                win_rate = round(focus_wins / RUNS_PER_ROOM, 4)
                detail_rows.append(
                    [
                        round_limit,
                        bot_names[focus_bot],
                        " | ".join(bot_names[bot] for bot in room),
                        len(room),
                        RUNS_PER_ROOM,
                        focus_wins,
                        shared_wins,
                        win_rate,
                    ]
                )
                key = (round_limit, focus_bot)
                summary[key]["rooms"] += 1
                summary[key]["runs"] += RUNS_PER_ROOM
                summary[key]["wins"] += focus_wins
                summary[key]["shared"] += shared_wins

    summary_rows = []
    for round_limit in ROUND_LIMITS:
        for focus_bot in FOCUS_BOTS:
            totals = summary[(round_limit, focus_bot)]
            overall = round(totals["wins"] / totals["runs"], 4) if totals["runs"] else 0.0
            summary_rows.append(
                [
                    round_limit,
                    bot_names[focus_bot],
                    totals["rooms"],
                    totals["runs"],
                    totals["wins"],
                    totals["shared"],
                    overall,
                ]
            )

    write_csv(
        DETAIL_CSV,
        [
            "round_limit",
            "focus_bot",
            "room",
            "room_size",
            "runs",
            "focus_wins",
            "shared_wins",
            "win_rate",
        ],
        detail_rows,
    )
    write_csv(
        SUMMARY_CSV,
        [
            "round_limit",
            "focus_bot",
            "rooms_tested",
            "total_runs",
            "total_wins",
            "shared_wins",
            "overall_win_rate",
        ],
        summary_rows,
    )

    print(f"Wrote detailed results to {DETAIL_CSV}")
    print(f"Wrote summary results to {SUMMARY_CSV}")


if __name__ == "__main__":
    main()
