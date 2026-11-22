"""Painting auction strategies and import aliases for the coursework auctioneer."""

from importlib import import_module


_COURSEWORK_MODULES = {
    "flat_bot_10": "fixed_bid_10",
    "flat_bot_15": "fixed_bid_15",
    "flat_bot_20": "fixed_bid_20",
    "random_bot": "random_budget_bidder",
    "u5726455": "collection_balancer",
    "u5726455_final": "price_profile_bidder",
    "u5726455_i": "room_size_bidder",
    "u5726455_i2": "adaptive_market_bidder",
    "u5726455_i2_i": "fixed_bid_specialist",
    "u5726455_i2_i_i2_i": "weighted_strategy_blend",
    "u5726455_i_i2": "budget_reserve_bidder",
    "u5726455_i_i2_min": "endgame_boost_bidder",
    "u5726455_q": "q_learning_bidder",
}


def __getattr__(name):
    # auctioneer.py still uses the original `from bots import ...` statements.
    module = _COURSEWORK_MODULES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return import_module(f".{module}", __name__)
