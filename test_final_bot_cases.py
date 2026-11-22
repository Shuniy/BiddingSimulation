from __future__ import annotations

import argparse
import copy
import importlib
import io
import random
from contextlib import redirect_stdout

from bots import flat_bot_10, flat_bot_15, random_bot


ARTISTS = ["Da Vinci", "Picasso", "Rembrandt", "Van Gogh"]
ROUND_LIMIT = 200
STARTING_BUDGET = 1001


class CaseAuctioneer(object):
    def __init__(self, room_modules, seed):
        self.random = random.Random(seed)
        self.current_round = 0
        self.bots = []
        self.winner_ids = []
        self.amounts_paid = []
        self.painting_order = [
            ARTISTS[self.random.randint(0, len(ARTISTS) - 1)] for _ in range(ROUND_LIMIT)
        ]
        self.focus_name = room_modules[0].Bot().name
        self._initialise_bots(room_modules)

    def _initialise_bots(self, room_modules):
        for index, bot_module in enumerate(room_modules, start=1):
            bot_instance = bot_module.Bot()
            self.bots.append(
                {
                    "bot_instance": bot_instance,
                    "bot_name": copy.deepcopy(bot_instance.name),
                    "bot_unique_id": f"{bot_instance.name}-{index}",
                    "paintings": {artist: 0 for artist in ARTISTS},
                    "budget": STARTING_BUDGET,
                    "current_bid": 0,
                    "score": 0,
                }
            )

    def run(self):
        while self.current_round < ROUND_LIMIT:
            self._collect_bids()
            self._pick_winner()
            self._update_scores()
            self.current_round += 1

        best_score = max(bot["score"] for bot in self.bots)
        winners = [bot for bot in self.bots if bot["score"] == best_score]
        focus_bot = next(bot for bot in self.bots if bot["bot_name"] == self.focus_name)
        ranking = sorted(self.bots, key=lambda bot: bot["score"], reverse=True)

        return {
            "winners": winners,
            "focus_score": focus_bot["score"],
            "focus_budget": focus_bot["budget"],
            "focus_paintings": copy.deepcopy(focus_bot["paintings"]),
            "focus_rank": 1 + sum(
                1 for bot in ranking if bot["score"] > focus_bot["score"]
            ),
            "best_score": best_score,
        }

    def _collect_bids(self):
        for bot in self.bots:
            bot["current_bid"] = 0

        info_for_bots = {
            "current_round": self.current_round,
            "bots": self.bots,
            "winner_pays": 1,
            "artists_and_values": {
                "Da Vinci": 7,
                "Rembrandt": 3,
                "Van Gogh": 12,
                "Picasso": 2,
            },
            "round_limit": ROUND_LIMIT,
            "starting_budget": STARTING_BUDGET,
            "painting_order": self.painting_order,
            "target_collection": [10, 3, 2, 1],
            "current_painting": self.painting_order[self.current_round],
            "winner_ids": self.winner_ids,
            "amounts_paid": self.amounts_paid,
        }

        for bot in self.bots:
            info_copy = copy.deepcopy(info_for_bots)
            for bot_copy in info_copy["bots"]:
                del bot_copy["bot_instance"]
                del bot_copy["current_bid"]
            info_copy["my_bot_details"] = copy.deepcopy(bot)

            try:
                sink = io.StringIO()
                with redirect_stdout(sink):
                    bid = int(bot["bot_instance"].get_bid(**info_copy))
            except Exception:
                bid = 0

            bot["current_bid"] = bid if bid <= bot["budget"] else 0

    def _pick_winner(self):
        self.bots.sort(
            key=lambda bot: (bot["current_bid"], self.random.random()),
            reverse=True,
        )
        winner = self.bots[0]
        paid = winner["current_bid"]
        winner["budget"] -= paid
        winner["paintings"][self.painting_order[self.current_round]] += 1
        self.winner_ids.append(winner["bot_unique_id"])
        self.amounts_paid.append(paid)

    def _update_scores(self):
        for bot in self.bots:
            score = 1
            for value in bot["paintings"].values():
                score *= value
            bot["score"] = score


def build_cases(focus_bot_module):
    return [
        ("5 random bots", [focus_bot_module] + [random_bot] * 5),
        ("10 random bots", [focus_bot_module] + [random_bot] * 10),
        ("5 flat bots bidding 10", [focus_bot_module] + [flat_bot_10] * 5),
        ("5 flat bots bidding 15", [focus_bot_module] + [flat_bot_15] * 5),
        (
            "3 flat 10 bots + 3 flat 15 bots",
            [focus_bot_module] + [flat_bot_10] * 3 + [flat_bot_15] * 3,
        ),
        (
            "3 flat 10 bots + 3 flat 15 bots + 3 random bots",
            [focus_bot_module]
            + [flat_bot_10] * 3
            + [flat_bot_15] * 3
            + [random_bot] * 3,
        ),
    ]


def run_case(case_name, room_modules, runs):
    focus_name = room_modules[0].Bot().name
    wins = 0
    ties = 0
    total_score = 0
    total_rank = 0
    total_budget = 0
    last_snapshot = None

    for seed in range(runs):
        result = CaseAuctioneer(room_modules=room_modules, seed=seed).run()
        winner_names = [winner["bot_name"] for winner in result["winners"]]
        won = focus_name in winner_names
        wins += int(won)
        ties += int(won and len(result["winners"]) > 1)
        total_score += result["focus_score"]
        total_rank += result["focus_rank"]
        total_budget += result["focus_budget"]
        last_snapshot = result

    return {
        "case": case_name,
        "wins": wins,
        "runs": runs,
        "ties": ties,
        "avg_score": total_score / runs,
        "avg_rank": total_rank / runs,
        "avg_budget": total_budget / runs,
        "last_snapshot": last_snapshot,
    }


def main():
    parser = argparse.ArgumentParser(description="Run the requested 200-round auction cases.")
    parser.add_argument(
        "--bot-module",
        default="bots.u5726455_final",
        help="Python module path for the focus bot.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=20,
        help="Number of seeded runs per case.",
    )
    args = parser.parse_args()

    focus_bot_module = importlib.import_module(args.bot_module)
    summaries = []

    for case_name, room_modules in build_cases(focus_bot_module):
        summaries.append(run_case(case_name, room_modules, args.runs))

    print(f"Bot module: {args.bot_module}")
    print(f"Runs per case: {args.runs}")
    print("")
    for summary in summaries:
        snapshot = summary["last_snapshot"]
        print(summary["case"])
        print(
            f"  wins: {summary['wins']}/{summary['runs']} | ties: {summary['ties']} | "
            f"avg score: {summary['avg_score']:.1f} | avg rank: {summary['avg_rank']:.2f} | "
            f"avg budget left: {summary['avg_budget']:.1f}"
        )
        print(
            f"  last run paintings: {snapshot['focus_paintings']} | "
            f"last run score: {snapshot['focus_score']} | best score: {snapshot['best_score']}"
        )
        print("")


if __name__ == "__main__":
    main()
