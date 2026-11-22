"""Auction rules and events shared by the arena and benchmarking tools."""

from __future__ import annotations

import copy
import math
import random
import re
from collections.abc import Generator, Sequence
from dataclasses import dataclass, field
from threading import Event, Lock
from typing import Any, Literal

from .bot_execution import BotProcess, SimulationCancelled, evaluate_bid
from .bot_registry import BOT_NAMES, load_bot_module

Artist = Literal["Da Vinci", "Picasso", "Rembrandt", "Van Gogh"]
RuleMode = Literal["reference", "custom"]
GameEvent = dict[str, Any]

ARTISTS: tuple[Artist, ...] = ("Da Vinci", "Picasso", "Rembrandt", "Van Gogh")
ARTISTS_AND_VALUES: dict[Artist, int] = {
    "Da Vinci": 7,
    "Rembrandt": 3,
    "Van Gogh": 12,
    "Picasso": 2,
}
TARGET_COLLECTION = [10, 3, 2, 1]
DEFAULT_ROUND_LIMIT = 200
DEFAULT_BUDGET = 1001
MAX_SAFE_INTEGER = 2**53 - 1


@dataclass(frozen=True)
class PlayerConfig:
    player_name: str
    bot_module: str
    starting_budget: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "playerName": self.player_name,
            "botModule": self.bot_module,
            "startingBudget": self.starting_budget,
        }


@dataclass
class PlayerState:
    id: str
    player_name: str
    bot_name: str
    bot_module: str
    bot_instance: Any
    starting_budget: int
    budget: int
    current_bid: int = 0
    score: int = 0
    paintings: dict[Artist, int] = field(default_factory=lambda: dict.fromkeys(ARTISTS, 0))

    def public_bot_details(self, *, reference: bool) -> dict[str, Any]:
        details = {
            "bot_name": self.bot_name,
            "bot_unique_id": self.id,
            "paintings": self.paintings.copy(),
            "budget": self.budget,
            "score": self.score,
        }
        if not reference:
            details["player_name"] = self.player_name
        return details

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "playerName": self.player_name,
            "botName": self.bot_name,
            "botModule": self.bot_module,
            "budget": self.budget,
            "startingBudget": self.starting_budget,
            "currentBid": self.current_bid,
            "score": self.score,
            "paintings": self.paintings.copy(),
        }


def parse_integer(value: Any) -> int | None:
    """Read JSON integers and legacy integer strings with the same rules."""
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"[+-]?[0-9]+", value.strip()):
        try:
            return int(value)
        except ValueError:
            return None  # Python limits the conversion of very long strings.
    return None


def normalise_positive_int(value: Any, field_name: str) -> int:
    parsed = parse_integer(value)
    if parsed is None or parsed <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return parsed


def select_mode(
    players: Sequence[PlayerConfig], round_limit: int, mode: str | None = None
) -> RuleMode:
    defaults = round_limit == DEFAULT_ROUND_LIMIT and all(
        player.starting_budget == DEFAULT_BUDGET for player in players
    )
    if mode == "reference" and not defaults:
        raise ValueError("Reference mode requires 200 rounds and a starting budget of 1001")
    if mode == "custom" or (mode is None and not defaults):
        return "custom"
    if mode in (None, "reference"):
        return "reference"
    raise ValueError("mode must be reference or custom")


def build_player_configs(
    raw_players: Sequence[dict[str, Any]],
    *,
    max_players: int = 16,
    max_budget: int = 100_000,
    max_name_length: int = 60,
) -> list[PlayerConfig]:
    if not isinstance(raw_players, (list, tuple)) or not 2 <= len(raw_players) <= max_players:
        raise ValueError(f"players must be a list of 2 to {max_players} players")
    configs = []
    for index, player in enumerate(raw_players, start=1):
        if not isinstance(player, dict):
            raise ValueError(f"Player {index} must be an object")
        module = player.get("botModule")
        if not isinstance(module, str) or module not in BOT_NAMES:
            raise ValueError(f"Player {index} has an unknown bot module")
        name = player.get("playerName", f"Player {index}")
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name) > max_name_length
            or not name.isprintable()
        ):
            raise ValueError(
                f"Player {index} name must be printable and 1–{max_name_length} characters"
            )
        budget = normalise_positive_int(
            player.get("startingBudget", DEFAULT_BUDGET), f"Player {index} startingBudget"
        )
        if budget > max_budget:
            raise ValueError(f"Player {index} startingBudget must be at most {max_budget}")
        configs.append(PlayerConfig(name.strip(), module, budget))
    return configs


class DynamicAuctionGame:
    def __init__(
        self,
        game_id: str,
        players: list[PlayerConfig],
        round_limit: int = DEFAULT_ROUND_LIMIT,
        seed: int | None = None,
        tick_ms: int = 150,
        *,
        mode: RuleMode | None = None,
        painting_order: Sequence[Artist] | None = None,
        bot_timeout: float | None = None,
        cancelled: Event | None = None,
        bot_seeds: Sequence[int] | None = None,
    ) -> None:
        if len(players) < 2:
            raise ValueError("At least two players are required")
        self.game_id = game_id
        self.round_limit = normalise_positive_int(round_limit, "roundLimit")
        self.mode = select_mode(players, self.round_limit, mode)
        self.tick_ms = max(0, int(tick_ms or 0))
        self.seed = seed if seed is not None else random.SystemRandom().randrange(MAX_SAFE_INTEGER)
        self.rng = random.Random(self.seed)
        bot_rng = random.Random(f"bots:{self.seed}")
        self._bot_seeds = (
            list(bot_seeds) if bot_seeds is not None else [bot_rng.getrandbits(64) for _ in players]
        )
        if len(self._bot_seeds) != len(players):
            raise ValueError("bot_seeds must contain one seed per player")
        self.current_round = 0
        self.finished = False
        self._started = False
        self._start_lock = Lock()
        self._cancelled = cancelled if cancelled is not None else Event()
        self.winner_ids: list[str] = []
        self.amounts_paid: list[int] = []
        artists = tuple(ARTISTS_AND_VALUES) if self.mode == "reference" else ARTISTS
        self.painting_order = (
            list(painting_order)
            if painting_order is not None
            else [self.rng.choice(artists) for _ in range(self.round_limit)]
        )
        if len(self.painting_order) != self.round_limit or any(
            artist not in ARTISTS for artist in self.painting_order
        ):
            raise ValueError("painting_order must list one valid artist per round")
        self._bot_timeout = bot_timeout
        self._processes: dict[str, BotProcess] = {}
        self.players = []
        for index, config in enumerate(players):
            bot_name = BOT_NAMES[config.bot_module]
            bot = None
            if bot_timeout is None:
                # The in-process path is reserved for the bundled strategies.
                module = load_bot_module(config.bot_module)
                bot = (
                    module.Bot(rng=random.Random(self._bot_seeds[index]))
                    if config.bot_module == "bots.random_bot"
                    else module.Bot()
                )
                bot_name = bot.name
            self.players.append(
                PlayerState(
                    id=f"{bot_name}-{index + 1}",
                    player_name=config.player_name,
                    bot_name=bot_name,
                    bot_module=config.bot_module,
                    bot_instance=bot,
                    starting_budget=config.starting_budget,
                    budget=config.starting_budget,
                )
            )
        self._bid_order = self.players.copy()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> None:
        self._cancelled.set()

    def snapshots(self) -> list[dict[str, Any]]:
        return [player.snapshot() for player in self.players]

    def configuration(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "roundLimit": self.round_limit,
            "seed": self.seed,
            "tickMs": self.tick_ms,
            "players": [
                PlayerConfig(
                    player.player_name, player.bot_module, player.starting_budget
                ).to_dict()
                for player in self.players
            ],
        }

    def event_stream(self) -> Generator[GameEvent, None, None]:
        with self._start_lock:
            if self._started:
                raise RuntimeError("A simulation may only be executed once")
            self._started = True
        yield {
            "type": "game_started",
            "gameId": self.game_id,
            "roundLimit": self.round_limit,
            "configuration": self.configuration(),
            "players": self.snapshots(),
        }
        try:
            if self._bot_timeout is not None:
                for player, seed in zip(self.players, self._bot_seeds):
                    if self.cancelled:
                        raise SimulationCancelled
                    self._processes[player.id] = BotProcess(
                        player.bot_module, seed, self._bot_timeout, self._cancelled
                    )
            while self.current_round < self.round_limit and not self.cancelled:
                bids, errors = self._collect_bids()
                if self.cancelled:
                    break
                for player, bid in zip(self._bid_order, bids):
                    player.current_bid = bid
                round_event = self._pick_winner_of_round()
                self._update_scores()
                self.current_round += 1
                yield from errors
                yield {**round_event, "players": self.snapshots()}
                if self.current_round < self.round_limit:
                    self._cancelled.wait(self.tick_ms / 1000)
        except SimulationCancelled:
            self.cancel()
        finally:
            for process in self._processes.values():
                process.close()
            self._processes.clear()

        self.finished = self.current_round == self.round_limit
        if not self.finished and self.cancelled:
            yield {
                "type": "game_cancelled",
                "gameId": self.game_id,
                "players": self.snapshots(),
            }
        else:
            yield {
                "type": "game_finished",
                "winners": self._winner_ids(),
                "players": self.snapshots(),
            }

    def _collect_bids(self) -> tuple[list[int], list[GameEvent]]:
        reference = self.mode == "reference"
        public_bots = [player.public_bot_details(reference=reference) for player in self._bid_order]
        common = {
            "current_round": self.current_round,
            "bots": public_bots,
            "winner_pays": 1,
            "artists_and_values": ARTISTS_AND_VALUES,
            "round_limit": self.round_limit,
            "painting_order": self.painting_order,
            "target_collection": TARGET_COLLECTION,
            "current_painting": self.painting_order[self.current_round],
            "winner_ids": self.winner_ids,
            "amounts_paid": self.amounts_paid,
        }
        errors = []
        bids = []
        for player, details in zip(self._bid_order, public_bots):
            if self.cancelled:
                raise SimulationCancelled
            info = copy.deepcopy(common)
            info["starting_budget"] = player.starting_budget
            info["my_bot_details"] = copy.deepcopy(details)
            if reference:
                info["my_bot_details"]["current_bid"] = 0
            if player.id in self._processes:
                bid, error = self._processes[player.id].bid(info, reference)
            else:
                bid, error = evaluate_bid(player.bot_instance, info, reference)
            if error:
                errors.append(
                    {
                        "type": "bot_error",
                        "round": self.current_round + 1,
                        "playerId": player.id,
                        "message": error,
                    }
                )
            bids.append(bid)
        return bids, errors

    def _pick_winner_of_round(self) -> GameEvent:
        ordered = sorted(
            self._bid_order,
            key=lambda player: (player.current_bid, self.rng.random()),
            reverse=True,
        )
        if self.mode == "reference":
            self._bid_order = ordered
        winner = ordered[0]
        amount_paid = winner.current_bid
        winner.budget -= amount_paid
        painting = self.painting_order[self.current_round]
        winner.paintings[painting] += 1
        self.winner_ids.append(winner.id)
        self.amounts_paid.append(amount_paid)
        return {
            "type": "round_finished",
            "round": self.current_round + 1,
            "painting": painting,
            "bids": {player.id: player.current_bid for player in self.players},
            "winnerId": winner.id,
            "amountPaid": amount_paid,
        }

    def _update_scores(self) -> None:
        for player in self.players:
            player.score = math.prod(player.paintings.values())

    def _winner_ids(self) -> list[str]:
        best_score = max(player.score for player in self.players)
        return [
            player.id for player in self._bid_order if player.score == best_score and best_score > 0
        ]
