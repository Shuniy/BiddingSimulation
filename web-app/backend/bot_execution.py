"""Persistent, time-bounded processes for the web arena's trusted strategies."""

from __future__ import annotations

import copy
import importlib
import json
import multiprocessing
import random
import time
from multiprocessing.connection import Connection
from threading import Event
from typing import Any

from .bot_registry import ensure_project_on_path


class SimulationCancelled(Exception):
    """Stop at the current round boundary without committing a partial round."""


def evaluate_bid(bot: Any, info: dict[str, Any], allow_negative: bool) -> tuple[int, str | None]:
    my_details = info["my_bot_details"]
    budget = my_details["budget"]
    if allow_negative:
        # The coursework gives the bot its own (copied) instance and zeroed bid.
        my_details["bot_instance"] = copy.deepcopy(bot)
    try:
        bid = int(bot.get_bid(**info))
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"[:240]

    if bid < 0 and not allow_negative:
        return 0, "Negative bid changed to 0"
    if bid > budget:
        return 0, "Over-budget bid changed to 0"
    return bid, None


def _bot_main(connection: Connection, module_name: str, seed: int) -> None:
    with connection:
        try:
            ensure_project_on_path()
            random.seed(seed)
            bot = importlib.import_module(module_name).Bot()
            connection.send_bytes(json.dumps([str(bot.name)[:120], None]).encode())
        except Exception as exc:
            connection.send_bytes(
                json.dumps([None, f"Bot initialization failed ({type(exc).__name__})"]).encode()
            )
            return

        try:
            while True:
                info, allow_negative = json.loads(connection.recv_bytes())
                budget = info["my_bot_details"]["budget"]
                bid, error = evaluate_bid(bot, info, allow_negative)
                # The browser must represent every bid exactly. Tested strategies
                # stay well inside this envelope, including reference negative bids.
                if bid < budget - (2**53 - 1):
                    bid, error = 0, "Bid outside the web safe integer range changed to 0"
                connection.send_bytes(json.dumps([bid, error]).encode())
        except (EOFError, BrokenPipeError):
            return


class BotProcess:
    def __init__(
        self,
        module: str,
        seed: int,
        timeout: float,
        cancelled: Event,
    ) -> None:
        self.timeout = timeout
        self.cancelled = cancelled
        self.failure: str | None = None
        self._reported = False
        self._closed = False
        context = multiprocessing.get_context("spawn")
        self.connection, child = context.Pipe()
        self.process = context.Process(target=_bot_main, args=(child, module, seed), daemon=True)
        try:
            self.process.start()
            child.close()
            _, self.failure = self._receive(max(3.0, timeout))
            if self.failure:
                self.close()
        except SimulationCancelled:
            self.close()
            raise
        except TimeoutError:
            self.failure = "Bot initialization timed out and the bot was disabled"
            self.close()
        except (OSError, EOFError, RuntimeError, ValueError):
            self.failure = "Bot process failed to start and the bot was disabled"
            self.close()
        finally:
            child.close()

    def _receive(self, timeout: float) -> Any:
        deadline = time.monotonic() + timeout
        while not self.cancelled.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            if self.connection.poll(min(remaining, 0.05)):
                return json.loads(self.connection.recv_bytes(4096))
        raise SimulationCancelled

    def bid(self, info: dict[str, Any], allow_negative: bool) -> tuple[int, str | None]:
        if self.cancelled.is_set():
            raise SimulationCancelled
        if self.failure is None:
            try:
                self.connection.send_bytes(json.dumps([info, allow_negative]).encode())
                bid, error = self._receive(self.timeout)
                return int(bid), error
            except TimeoutError:
                self.failure = "Bot bid timed out and the bot was disabled"
            except (OSError, EOFError, ValueError, TypeError):
                self.failure = "Bot process exited and the bot was disabled"
            self.close()
        error = self.failure if not self._reported else None
        self._reported = True
        return 0, error

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.connection.close()
        if self.process.pid is not None:
            if self.process.is_alive():
                self.process.kill()
            self.process.join(timeout=1)
        if not self.process.is_alive():
            self.process.close()
