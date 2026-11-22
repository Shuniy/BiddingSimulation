"""Compare a focus strategy against the historical 200-round rooms."""

from __future__ import annotations

import argparse
from pathlib import Path

from benchmark import BOT_NAMES, Scenario, module_name, run_experiment, write_report


def build_cases(focus_bot_module):
    return [
        ("5 random bots", [focus_bot_module] + ["bots.random_bot"] * 5),
        ("10 random bots", [focus_bot_module] + ["bots.random_bot"] * 10),
        ("5 flat bots bidding 10", [focus_bot_module] + ["bots.flat_bot_10"] * 5),
        ("5 flat bots bidding 15", [focus_bot_module] + ["bots.flat_bot_15"] * 5),
        (
            "3 flat 10 bots + 3 flat 15 bots",
            [focus_bot_module] + ["bots.flat_bot_10"] * 3 + ["bots.flat_bot_15"] * 3,
        ),
        (
            "3 flat 10 bots + 3 flat 15 bots + 3 random bots",
            [focus_bot_module]
            + ["bots.flat_bot_10"] * 3
            + ["bots.flat_bot_15"] * 3
            + ["bots.random_bot"] * 3,
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bot-module", default="bots.u5726455_final", choices=BOT_NAMES)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("data/final_bot_cases"))
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    cases = [
        Scenario(label, tuple(room), 200)
        for label, room in build_cases(module_name(args.bot_module))
    ]
    write_report(run_experiment(cases, range(args.runs), rotate=False), args.output)


if __name__ == "__main__":
    main()
