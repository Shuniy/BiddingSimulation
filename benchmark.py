"""Run reproducible strategy comparisons with the arena's auction rules."""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any

# The existing Flask package resides under web-app.
BACKEND_PARENT = str(Path(__file__).resolve().parent / "web-app")
if BACKEND_PARENT not in sys.path:
    sys.path.insert(0, BACKEND_PARENT)

from backend.bot_registry import BOT_NAMES
from backend.simulator import (
    ARTISTS_AND_VALUES,
    DEFAULT_BUDGET,
    DynamicAuctionGame,
    PlayerConfig,
    RuleMode,
)


@dataclass(frozen=True)
class Scenario:
    label: str
    room: tuple[str, ...]  # The strategy under evaluation is first.
    rounds: int
    budget: int = DEFAULT_BUDGET
    mode: RuleMode | None = None


def module_name(name: str) -> str:
    if not name.startswith("bots."):
        name = f"bots.{name}"
    if name not in BOT_NAMES:
        raise ValueError(f"Unknown bot: {name}")
    return name


def run_trial(scenario: Scenario, seed: int, rotation: int = 0) -> dict[str, Any]:
    # Use the same paintings for a seed and round count across all rooms and
    # strategies. Rotating the room also rotates each logical player's RNG.
    rng = random.Random(seed)
    paintings = [rng.choice(tuple(ARTISTS_AND_VALUES)) for _ in range(scenario.rounds)]
    bot_rng = random.Random(f"benchmark-bots:{seed}")
    bot_seeds = [bot_rng.getrandbits(64) for _ in scenario.room]
    seats = list(range(len(scenario.room)))
    seats = seats[rotation:] + seats[:rotation]
    game = DynamicAuctionGame(
        "benchmark",
        [
            PlayerConfig(BOT_NAMES[scenario.room[index]], scenario.room[index], scenario.budget)
            for index in seats
        ],
        scenario.rounds,
        seed=seed,
        tick_ms=0,
        mode=scenario.mode,
        painting_order=paintings,
        bot_seeds=[bot_seeds[index] for index in seats],
    )
    errors = Counter()
    for event in game.event_stream():
        if event["type"] == "bot_error":
            errors[event["message"]] += 1

    focus = event["players"][seats.index(0)]
    winners = event["winners"]
    if not winners:
        outcome = "no_winner"
    elif focus["id"] not in winners:
        outcome = "loss"
    else:
        outcome = "sole_win" if len(winners) == 1 else "shared_win"

    spent = scenario.budget - focus["budget"]
    return {
        "seed": seed,
        "rotation": rotation,
        "focus_seat": seats.index(0) + 1,
        "seat_order": [scenario.room[index] for index in seats],
        "mode": game.mode,
        "outcome": outcome,
        "score": focus["score"],
        "final_budget": focus["budget"],
        "spent": spent,
        "rank": 1 + sum(player["score"] > focus["score"] for player in event["players"]),
        "paintings": focus["paintings"],
        "winners": winners,
        "bot_errors": dict(errors),
    }


def summarize(trials: Sequence[dict[str, Any]]) -> dict[str, Any]:
    outcomes = Counter(trial["outcome"] for trial in trials)
    by_seed: dict[int, list[bool]] = defaultdict(list)
    for trial in trials:
        by_seed[trial["seed"]].append(trial["outcome"] in {"sole_win", "shared_win"})

    # Rotations are paired within a seed. Resample whole seeds to retain that
    # dependence when estimating the win-rate interval.
    seed_rates = [mean(wins) for wins in by_seed.values()]
    interval = None
    if len(seed_rates) >= 2:
        rng = random.Random(0)
        estimates = sorted(mean(rng.choices(seed_rates, k=len(seed_rates))) for _ in range(1000))
        interval = [estimates[25], estimates[974]]

    spent = sum(trial["spent"] for trial in trials)
    scores = [trial["score"] for trial in trials]
    return {
        "games": len(trials),
        "independent_seeds": len(by_seed),
        "sole_wins": outcomes["sole_win"],
        "shared_wins": outcomes["shared_win"],
        "losses": outcomes["loss"],
        "no_winner": outcomes["no_winner"],
        "win_rate": (outcomes["sole_win"] + outcomes["shared_win"]) / len(trials),
        "win_rate_ci95": interval,
        "mean_score": mean(scores),
        "median_score": median(scores),
        "mean_final_budget": mean(trial["final_budget"] for trial in trials),
        "mean_rank": mean(trial["rank"] for trial in trials),
        "score_per_credit_spent": sum(scores) / spent if spent > 0 else None,
        "bot_error_count": sum(sum(trial["bot_errors"].values()) for trial in trials),
    }


def run_experiment(
    scenarios: Iterable[Scenario], seeds: Sequence[int], *, rotate: bool = True
) -> list[dict[str, Any]]:
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Provide one or more distinct seeds")
    report = []
    for scenario in scenarios:
        rotations = range(len(scenario.room)) if rotate else range(1)
        trials = [run_trial(scenario, seed, rotation) for seed in seeds for rotation in rotations]
        report.append(
            {"scenario": asdict(scenario), "summary": summarize(trials), "trials": trials}
        )
    return report


def baseline_scenarios(focus_modules: Iterable[str], rounds: Iterable[int]) -> Iterable[Scenario]:
    rounds = tuple(rounds)
    baselines = (
        ("Random opponent", ("bots.random_bot",)),
        (
            "Mixed opponents",
            ("bots.random_bot", "bots.flat_bot_10", "bots.flat_bot_15", "bots.flat_bot_20"),
        ),
    )
    for focus in focus_modules:
        for length in rounds:
            for label, opponents in baselines:
                yield Scenario(label, (focus, *opponents), length)


def write_report(report: list[dict[str, Any]], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(
        json.dumps({"schemaVersion": 1, "results": report}, indent=2) + "\n", encoding="utf-8"
    )
    summaries = []
    rows = [
        "# Strategy benchmark",
        "",
        "The win rate includes sole and shared wins. The 95% interval resamples seed blocks.",
        "",
        "| Strategy | Room | Rounds | Rules | Games | Sole / shared / loss / no winner | Win rate (95% CI) | Mean / median score | Mean budget | Mean rank | Score / credit |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case in report:
        scenario, stats = case["scenario"], case["summary"]
        name = BOT_NAMES[scenario["room"][0]]
        mode = case["trials"][0]["mode"]
        summaries.append(
            {
                "strategy": name,
                "room": scenario["label"],
                "modules": " ".join(scenario["room"]),
                "rounds": scenario["rounds"],
                "mode": mode,
                "starting_budget": scenario["budget"],
                **stats,
            }
        )
        interval = stats["win_rate_ci95"]
        interval_text = f" ({interval[0]:.0%}–{interval[1]:.0%})" if interval else ""
        efficiency = stats["score_per_credit_spent"]
        efficiency_text = f"{efficiency:.3f}" if efficiency is not None else "—"
        label = scenario["label"].replace("|", "/")
        rows.append(
            f"| {name} | {label} ({len(scenario['room'])}) | {scenario['rounds']} | {mode} | "
            f"{stats['games']} | {stats['sole_wins']} / {stats['shared_wins']} / "
            f"{stats['losses']} / {stats['no_winner']} | {stats['win_rate']:.0%}{interval_text} | "
            f"{stats['mean_score']:.1f} / {stats['median_score']:.1f} | "
            f"{stats['mean_final_budget']:.1f} | {stats['mean_rank']:.2f} | {efficiency_text} |"
        )
    with (output / "summary.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    (output / "summary.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"Wrote {sum(case['summary']['games'] for case in report)} trials to {output}")


def run_legacy_suite(
    focus_modules: Iterable[str],
    rooms_for: Callable[[str], Iterable[tuple[str, ...]]],
    rounds: Iterable[int],
    runs: int,
    output: str,
) -> None:
    scenarios = [
        Scenario(" + ".join(room), tuple(map(module_name, room)), length)
        for length in rounds
        for focus in focus_modules
        for room in rooms_for(focus)
    ]
    write_report(run_experiment(scenarios, range(runs), rotate=False), Path("data") / output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, nargs="+", default=[50, 200])
    parser.add_argument("--trials", type=int, default=5, help="Number of independent seeds")
    parser.add_argument("--seeds", type=int, nargs="+", help="Explicit seeds instead of --trials")
    parser.add_argument(
        "--focus", nargs="+", help="Strategies to compare against the baseline rooms"
    )
    parser.add_argument("--room", nargs="+", help="Explicit room. List the focus strategy first")
    parser.add_argument(
        "--budget", type=int, default=DEFAULT_BUDGET, help="Starting budget per seat"
    )
    parser.add_argument(
        "--mode", choices=["reference", "custom"], help="Override automatic rule selection"
    )
    parser.add_argument("--fixed-seats", action="store_true", help="Use the listed seat order only")
    parser.add_argument("--output", type=Path, default=Path("data/benchmark"))
    args = parser.parse_args()
    try:
        if args.trials < 1 or args.budget < 1 or min(args.rounds) < 1:
            raise ValueError("Rounds, trials, and budget must be positive")
        if args.room and (len(args.room) < 2 or args.focus):
            raise ValueError(
                "--room needs at least two modules and cannot be combined with --focus"
            )
        if args.room:
            room = tuple(map(module_name, args.room))
            scenarios = [
                Scenario("Custom room", room, length, args.budget, args.mode)
                for length in args.rounds
            ]
        else:
            focus = map(module_name, args.focus) if args.focus else BOT_NAMES
            scenarios = [
                Scenario(case.label, case.room, case.rounds, args.budget, args.mode)
                for case in baseline_scenarios(focus, args.rounds)
            ]
        report = run_experiment(
            scenarios, args.seeds or range(args.trials), rotate=not args.fixed_seats
        )
        write_report(report, args.output)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
