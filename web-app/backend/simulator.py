from __future__ import annotations

import copy
import importlib
import random
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Generator, Iterable, Literal

from .bot_registry import discover_bots, ensure_project_on_path


Artist = Literal["Da Vinci", "Picasso", "Rembrandt", "Van Gogh"]

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


@dataclass(frozen=True)
class PlayerConfig:
    player_name: str
    bot_module: str
    starting_budget: int


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
    paintings: dict[Artist, int] = field(
        default_factory=lambda: {artist: 0 for artist in ARTISTS}
    )

    def public_bot_details(self) -> dict[str, Any]:
        return {
            "bot_name": self.bot_name,
            "bot_unique_id": self.id,
            "player_name": self.player_name,
            "paintings": copy.deepcopy(self.paintings),
            "budget": self.budget,
            "score": self.score,
        }

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
            "paintings": copy.deepcopy(self.paintings),
        }


def normalise_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return parsed


def build_player_configs(raw_players: Iterable[dict[str, Any]]) -> list[PlayerConfig]:
    available_modules = {bot.module for bot in discover_bots()}
    players = list(raw_players)
    if len(players) < 2:
        raise ValueError("At least two players are required")

    configs: list[PlayerConfig] = []
    for index, player in enumerate(players, start=1):
        bot_module = str(player.get("botModule", "")).strip()
        if bot_module not in available_modules:
            raise ValueError(f"Player {index} has an unknown bot module")

        player_name = str(player.get("playerName") or f"Player {index}").strip()
        if not player_name:
            player_name = f"Player {index}"

        starting_budget = normalise_positive_int(
            player.get("startingBudget", DEFAULT_BUDGET),
            f"Player {index} startingBudget",
        )
        configs.append(
            PlayerConfig(
                player_name=player_name,
                bot_module=bot_module,
                starting_budget=starting_budget,
            )
        )

    return configs


class DynamicAuctionGame:
    def __init__(
        self,
        game_id: str,
        players: list[PlayerConfig],
        round_limit: int = DEFAULT_ROUND_LIMIT,
        seed: int | None = None,
        tick_ms: int = 150,
    ) -> None:
        if len(players) < 2:
            raise ValueError("At least two players are required")

        self.game_id = game_id
        self.round_limit = normalise_positive_int(round_limit, "roundLimit")
        self.tick_ms = max(0, int(tick_ms or 0))
        self.rng = random.Random(seed)
        self.current_round = 0
        self.finished = False
        self.cancelled = False
        self.winner_ids: list[str] = []
        self.amounts_paid: list[int] = []
        self.painting_order = [
            ARTISTS[self.rng.randint(0, len(ARTISTS) - 1)]
            for _ in range(self.round_limit)
        ]
        self.players = self._initialise_players(players)

    def _initialise_players(self, configs: list[PlayerConfig]) -> list[PlayerState]:
        ensure_project_on_path()
        players: list[PlayerState] = []
        for index, config in enumerate(configs, start=1):
            module = importlib.import_module(config.bot_module)
            bot_instance = module.Bot()
            bot_name = str(getattr(bot_instance, "name", config.bot_module))
            player_id = f"{bot_name}-{index}"
            players.append(
                PlayerState(
                    id=player_id,
                    player_name=config.player_name,
                    bot_name=bot_name,
                    bot_module=config.bot_module,
                    bot_instance=bot_instance,
                    starting_budget=config.starting_budget,
                    budget=config.starting_budget,
                )
            )
        return players

    def cancel(self) -> None:
        self.cancelled = True

    def snapshots(self) -> list[dict[str, Any]]:
        return [player.snapshot() for player in self.players]

    def event_stream(self) -> Generator[dict[str, Any], None, None]:
        yield {
            "type": "game_started",
            "gameId": self.game_id,
            "roundLimit": self.round_limit,
            "players": self.snapshots(),
        }

        while not self.finished and not self.cancelled:
            errors = self._collect_bids()
            for error in errors:
                yield error

            round_event = self._pick_winner_of_round()
            self._update_scores()
            round_event["players"] = self.snapshots()
            yield round_event

            self.current_round += 1
            self.finished = self.current_round >= self.round_limit
            if not self.finished and self.tick_ms > 0:
                time.sleep(self.tick_ms / 1000)

        if self.cancelled:
            yield {
                "type": "game_cancelled",
                "gameId": self.game_id,
                "players": self.snapshots(),
            }
            return

        yield {
            "type": "game_finished",
            "winners": self._winner_ids(),
            "players": self.snapshots(),
        }

    def _collect_bids(self) -> list[dict[str, Any]]:
        for player in self.players:
            player.current_bid = 0

        current_painting = self.painting_order[self.current_round]
        public_bots = [player.public_bot_details() for player in self.players]
        errors: list[dict[str, Any]] = []

        for player in self.players:
            info_for_bot = {
                "current_round": self.current_round,
                "bots": copy.deepcopy(public_bots),
                "winner_pays": 1,
                "artists_and_values": copy.deepcopy(ARTISTS_AND_VALUES),
                "round_limit": self.round_limit,
                "starting_budget": player.starting_budget,
                "painting_order": copy.deepcopy(self.painting_order),
                "target_collection": copy.deepcopy(TARGET_COLLECTION),
                "my_bot_details": player.public_bot_details(),
                "current_painting": current_painting,
                "winner_ids": copy.deepcopy(self.winner_ids),
                "amounts_paid": copy.deepcopy(self.amounts_paid),
            }

            try:
                bid = int(player.bot_instance.get_bid(**info_for_bot))
            except Exception as exc:
                bid = 0
                errors.append(
                    self._bot_error(
                        player.id,
                        f"{exc.__class__.__name__}: {exc}",
                        traceback.format_exc(limit=1),
                    )
                )

            if bid < 0:
                errors.append(self._bot_error(player.id, "Negative bid changed to 0"))
                bid = 0

            if bid > player.budget:
                errors.append(self._bot_error(player.id, "Over-budget bid changed to 0"))
                bid = 0

            player.current_bid = bid

        return errors

    def _bot_error(
        self, player_id: str, message: str, detail: str | None = None
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "type": "bot_error",
            "round": self.current_round + 1,
            "playerId": player_id,
            "message": message,
        }
        if detail:
            event["detail"] = detail
        return event

    def _pick_winner_of_round(self) -> dict[str, Any]:
        ordered = sorted(
            self.players,
            key=lambda player: (player.current_bid, self.rng.random()),
            reverse=True,
        )
        winner = ordered[0]
        amount_paid = winner.current_bid
        winner.budget -= amount_paid

        current_painting = self.painting_order[self.current_round]
        winner.paintings[current_painting] += 1
        self.winner_ids.append(winner.id)
        self.amounts_paid.append(amount_paid)

        return {
            "type": "round_finished",
            "round": self.current_round + 1,
            "painting": current_painting,
            "bids": {player.id: player.current_bid for player in self.players},
            "winnerId": winner.id,
            "amountPaid": amount_paid,
        }

    def _update_scores(self) -> None:
        for player in self.players:
            score = 1
            for count in player.paintings.values():
                score *= count
            player.score = score

    def _winner_ids(self) -> list[str]:
        best_score = max(player.score for player in self.players)
        if best_score <= 0:
            return []
        return [player.id for player in self.players if player.score == best_score]

