"""Run the original bot validation room matrix with the shared simulator."""

from benchmark import run_legacy_suite

ROUND_LIMITS = (50, 75, 100, 150, 200, 300)
RUNS_PER_ROOM = 10
FOCUS_BOTS = ("u5726455_i", "u5726455_i2", "u5726455_i2_i")
COMPARISON_BOTS = (
    "u5726455_i",
    "u5726455_i2",
    "u5726455_i2_i",
    "u5726455",
    "u5726455_q",
)


def build_rooms(focus_bot):
    rooms = [
        (focus_bot, "random_bot"),
        (focus_bot, "flat_bot_10"),
        (focus_bot, "flat_bot_15"),
        (focus_bot, "random_bot", "flat_bot_10", "flat_bot_15"),
        (focus_bot, "u5726455", "u5726455_q"),
        (
            focus_bot,
            "u5726455",
            "u5726455_q",
            "random_bot",
            "flat_bot_10",
            "flat_bot_15",
        ),
    ]

    for other in COMPARISON_BOTS:
        if other != focus_bot:
            rooms.append((focus_bot, other))

    comparison_room = [focus_bot]
    for other in COMPARISON_BOTS:
        if other != focus_bot:
            comparison_room.append(other)
    rooms.append(tuple(comparison_room))

    full_room = [focus_bot]
    for other in (
        "u5726455_i",
        "u5726455_i2",
        "u5726455_i2_i",
        "u5726455",
        "u5726455_q",
        "random_bot",
        "flat_bot_10",
        "flat_bot_15",
    ):
        if other != focus_bot:
            full_room.append(other)
    rooms.append(tuple(full_room))

    seen = set()
    unique_rooms = []
    for room in rooms:
        if room not in seen:
            unique_rooms.append(room)
            seen.add(room)
    return unique_rooms


def run_suite() -> None:
    run_legacy_suite(FOCUS_BOTS, build_rooms, ROUND_LIMITS, RUNS_PER_ROOM, "bot_validation")


if __name__ == "__main__":
    run_suite()
