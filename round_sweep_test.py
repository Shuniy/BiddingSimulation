"""Run the original round sweep room matrix with the shared simulator."""

from itertools import combinations

from benchmark import run_legacy_suite

ROUND_LIMITS = (50, 100, 150, 200, 250)
RUNS_PER_ROOM = 5
FOCUS_BOTS = (
    "random_budget_bidder",
    "fixed_bid_10",
    "collection_balancer",
    "room_size_bidder",
    "q_learning_bidder",
)


def unique_rooms(focus_bot: str) -> list[tuple[str, ...]]:
    """Generate a diverse, deduplicated seminar-style set of rooms."""

    others = [name for name in FOCUS_BOTS if name != focus_bot]
    rooms = [
        (focus_bot, "random_budget_bidder"),
        (focus_bot, "fixed_bid_10"),
        (focus_bot, "fixed_bid_10", "fixed_bid_10", "fixed_bid_10"),
        (focus_bot, "random_budget_bidder", "fixed_bid_10"),
        (focus_bot, "fixed_bid_10", "fixed_bid_10", "random_budget_bidder", "random_budget_bidder"),
    ]

    for other in others:
        rooms.append((focus_bot, other))
        rooms.append((focus_bot, other, "random_budget_bidder"))
        rooms.append((focus_bot, other, "fixed_bid_10"))
        rooms.append((focus_bot, other, "random_budget_bidder", "fixed_bid_10"))

    for other_a, other_b in combinations(others, 2):
        rooms.append((focus_bot, other_a, other_b))
        rooms.append((focus_bot, other_a, other_b, "fixed_bid_10"))
        rooms.append((focus_bot, other_a, other_b, "random_budget_bidder"))

    seen = set()
    deduped_rooms = []
    for room in rooms:
        if room not in seen:
            deduped_rooms.append(room)
            seen.add(room)
    return deduped_rooms


def main() -> None:
    run_legacy_suite(FOCUS_BOTS, unique_rooms, ROUND_LIMITS, RUNS_PER_ROOM, "round_sweep")


if __name__ == "__main__":
    main()
