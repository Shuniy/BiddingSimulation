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
    "bots.fixed_bid_10": "Fixed Bid 10",
    "bots.fixed_bid_15": "Fixed Bid 15",
    "bots.fixed_bid_20": "Fixed Bid 20",
    "bots.random_budget_bidder": "Random Budget Bidder",
    "bots.collection_balancer": "Collection Balancer",
    "bots.price_profile_bidder": "Price Profile Bidder",
    "bots.room_size_bidder": "Room-Size Bidder",
    "bots.adaptive_market_bidder": "Adaptive Market Bidder",
    "bots.fixed_bid_specialist": "Fixed-Bid Specialist",
    "bots.weighted_strategy_blend": "Weighted Strategy Blend",
    "bots.budget_reserve_bidder": "Budget Reserve Bidder",
    "bots.endgame_boost_bidder": "Endgame Boost Bidder",
    "bots.q_learning_bidder": "Q-Learning Bidder",
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
