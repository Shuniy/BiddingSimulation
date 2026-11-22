"""Run the original short auction validation room matrix with the shared simulator."""

from itertools import combinations

from benchmark import run_legacy_suite

ROUND_LIMITS = (50, 75, 100, 150)
RUNS_PER_ROOM = 5
CUSTOM_BOTS = (
    "collection_balancer",
    "room_size_bidder",
    "adaptive_market_bidder",
    "q_learning_bidder",
)
FOCUS_BOTS = ("random_budget_bidder", "fixed_bid_10", "fixed_bid_15", *CUSTOM_BOTS)


def unique_rooms(focus_bot: str) -> list[tuple[str, ...]]:
    """Generate stronger short-auction rooms with baseline-heavy mixes."""

    rooms = [
        (focus_bot, "random_budget_bidder", "fixed_bid_10", "fixed_bid_15"),
        (focus_bot, "random_budget_bidder", "random_budget_bidder", "fixed_bid_10", "fixed_bid_15"),
        (focus_bot, "fixed_bid_10", "fixed_bid_10", "fixed_bid_15"),
        (focus_bot, "fixed_bid_10", "fixed_bid_15", "fixed_bid_15"),
        (
            focus_bot,
            "random_budget_bidder",
            "fixed_bid_10",
            "fixed_bid_10",
            "fixed_bid_15",
            "fixed_bid_15",
        ),
    ]

    others = [bot for bot in CUSTOM_BOTS if bot != focus_bot]
    for other in others:
        rooms.append((focus_bot, other, "random_budget_bidder", "fixed_bid_10", "fixed_bid_15"))

    for other_a, other_b in combinations(others, 2):
        rooms.append(
            (focus_bot, other_a, other_b, "random_budget_bidder", "fixed_bid_10", "fixed_bid_15")
        )

    if focus_bot in CUSTOM_BOTS:
        rooms.append(
            (
                focus_bot,
                "collection_balancer",
                "room_size_bidder",
                "adaptive_market_bidder",
                "q_learning_bidder",
                "fixed_bid_15",
            )
        )

    seen = set()
    deduped = []
    for room in rooms:
        if room not in seen:
            deduped.append(room)
            seen.add(room)
    return deduped


def run_suite() -> None:
    run_legacy_suite(
        FOCUS_BOTS, unique_rooms, ROUND_LIMITS, RUNS_PER_ROOM, "short_auction_validation"
    )


if __name__ == "__main__":
    run_suite()
