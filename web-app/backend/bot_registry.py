"""Allowlist of trusted, repository-owned strategies exposed to the web API."""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Discovery must remain safe even when bot imports or constructors are slow.
BOT_NAMES = {
    "bots.flat_bot_10": "Fixed Bid 10",
    "bots.flat_bot_15": "Fixed Bid 15",
    "bots.flat_bot_20": "Fixed Bid 20",
    "bots.random_bot": "Random Budget Bidder",
    "bots.u5726455": "Collection Balancer",
    "bots.u5726455_final": "Price Profile Bidder",
    "bots.u5726455_i": "Room-Size Bidder",
    "bots.u5726455_i2": "Adaptive Market Bidder",
    "bots.u5726455_i2_i": "Fixed-Bid Specialist",
    "bots.u5726455_i2_i_i2_i": "Weighted Strategy Blend",
    "bots.u5726455_i_i2": "Budget Reserve Bidder",
    "bots.u5726455_i_i2_min": "Endgame Boost Bidder",
    "bots.u5726455_q": "Q-Learning Bidder",
}


@dataclass(frozen=True)
class BotInfo:
    module: str
    display_name: str

    def to_dict(self) -> dict[str, str]:
        return {"module": self.module, "displayName": self.display_name}


def ensure_project_on_path() -> None:
    project_path = str(PROJECT_ROOT)
    if project_path not in sys.path:
        sys.path.insert(0, project_path)


def load_bot_module(module_name: str) -> ModuleType:
    if module_name not in BOT_NAMES:
        raise ValueError(f"Unknown bot module: {module_name}")
    ensure_project_on_path()
    return importlib.import_module(module_name)


def discover_bots() -> list[BotInfo]:
    return [BotInfo(module, name) for module, name in BOT_NAMES.items()]
