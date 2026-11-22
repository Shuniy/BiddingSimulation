"""Bounded game storage with a single producer and independent event cursors."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import dataclass, field
from threading import Condition, Lock, Thread
from typing import Any

from .simulator import DynamicAuctionGame, GameEvent

TERMINAL_EVENTS = {
    "game_finished": "completed",
    "game_cancelled": "cancelled",
    "game_failed": "failed",
}


class GameUnavailable(Exception):
    def __init__(self, message: str, code: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass
class GameRecord:
    game_id: str
    configuration: dict[str, Any]
    game: DynamicAuctionGame | None
    state: str = "created"
    updated_at: float = field(default_factory=time.monotonic)
    events: list[GameEvent] = field(default_factory=list)
    changed: Condition = field(default_factory=Condition)
    subscribers: int = 0

    def publish(self, event: GameEvent) -> None:
        with self.changed:
            self.events.append(event)
            terminal_state = TERMINAL_EVENTS.get(event["type"])
            if terminal_state:
                self.state = terminal_state
                self.updated_at = time.monotonic()
                self.game = None
            self.changed.notify_all()

    def subscribe(self, after: int, heartbeat: float) -> Iterator[tuple[int, GameEvent] | None]:
        while True:
            with self.changed:
                self.changed.wait_for(
                    lambda: after < len(self.events) or self.game is None,
                    timeout=heartbeat,
                )
                if after < len(self.events):
                    event = self.events[after]
                    after += 1
                    item = (after, event)
                elif self.game is None:
                    return
                else:
                    item = None
            yield item

    def export(self, *, include_events: bool) -> dict[str, Any]:
        with self.changed:
            payload = {
                "schemaVersion": 1,
                "gameId": self.game_id,
                "status": self.state,
                "configuration": self.configuration,
                "lastEventId": len(self.events),
            }
            if include_events:
                payload["events"] = self.events.copy()
            return payload


class GameStore:
    def __init__(
        self,
        *,
        capacity: int,
        max_running: int,
        created_ttl: float,
        result_ttl: float,
        max_subscribers: int,
        logger: logging.Logger,
    ) -> None:
        self.capacity = capacity
        self.max_running = max_running
        self.created_ttl = created_ttl
        self.result_ttl = result_ttl
        self.max_subscribers = max_subscribers
        self.logger = logger
        self._lock = Lock()
        self._records: dict[str, GameRecord] = {}
        self._expired: OrderedDict[str, None] = OrderedDict()

    def _prune(self) -> None:
        now = time.monotonic()
        for game_id, record in list(self._records.items()):
            with record.changed:
                ttl = self.created_ttl if record.state == "created" else self.result_ttl
                if record.state != "running" and now - record.updated_at >= ttl:
                    del self._records[game_id]
                    self._expired[game_id] = None
        while len(self._expired) > self.capacity:
            self._expired.popitem(last=False)

    def _lookup(self, game_id: str) -> GameRecord:
        self._prune()
        if game_id in self._records:
            return self._records[game_id]
        if game_id in self._expired:
            raise GameUnavailable("Game has expired", "game_expired", 410)
        raise GameUnavailable("Unknown game", "unknown_game", 404)

    def create(self, game: DynamicAuctionGame) -> None:
        with self._lock:
            self._prune()
            if len(self._records) >= self.capacity:
                raise GameUnavailable("Game storage is full", "games_at_capacity", 429)
            self._records[game.game_id] = GameRecord(game.game_id, game.configuration(), game)

    def get(self, game_id: str) -> GameRecord:
        with self._lock:
            return self._lookup(game_id)

    def open_stream(self, game_id: str, after: int) -> GameRecord:
        with self._lock:
            record = self._lookup(game_id)
            with record.changed:
                if after > len(record.events):
                    raise GameUnavailable(
                        "Event cursor is ahead of the stream", "invalid_cursor", 400
                    )
                if record.subscribers >= self.max_subscribers:
                    raise GameUnavailable("Too many subscribers", "too_many_subscribers", 429)
                if record.state == "created":
                    if (
                        sum(item.state == "running" for item in self._records.values())
                        >= self.max_running
                    ):
                        raise GameUnavailable(
                            "All simulation workers are busy", "workers_busy", 429
                        )
                    record.state = "running"
                    thread = Thread(target=self._run, args=(record,), daemon=True)
                    try:
                        thread.start()
                    except RuntimeError:
                        record.state = "created"
                        raise
                record.subscribers += 1
            return record

    def close_stream(self, record: GameRecord) -> None:
        with record.changed:
            record.subscribers -= 1

    def cancel(self, game_id: str) -> None:
        with self._lock:
            record = self._lookup(game_id)
            with record.changed:
                game = record.game
                if game is None:
                    return
                game.cancel()
                if record.state == "created":
                    record.publish(
                        {
                            "type": "game_cancelled",
                            "gameId": game_id,
                            "players": game.snapshots(),
                        }
                    )

    def _run(self, record: GameRecord) -> None:
        game = record.game
        if game is None:
            return
        try:
            for event in game.event_stream():
                record.publish(event)
        except Exception:
            self.logger.exception("auction_failed game_id=%s", record.game_id)
            record.publish(
                {
                    "type": "game_failed",
                    "gameId": record.game_id,
                    "players": game.snapshots(),
                    "message": "The simulation failed. See the server log for details.",
                }
            )
        self.logger.info("auction_ended game_id=%s status=%s", record.game_id, record.state)
