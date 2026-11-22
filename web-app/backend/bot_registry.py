from __future__ import annotations

import importlib
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType


# bot_registry.py lives in simulation/backend, while the auction bots live at
# the repository root in bots/.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BOTS_DIR = PROJECT_ROOT / "bots"


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


def _is_candidate(path: Path) -> bool:
    return (
        path.is_file()
        and path.suffix == ".py"
        and not path.name.startswith("_")
        and path.parent.name != "__pycache__"
    )


def load_bot_module(module_name: str) -> ModuleType:
    ensure_project_on_path()
    if not module_name.startswith("bots."):
        raise ValueError("Bot module must be inside the bots package")

    available = {bot.module for bot in discover_bots()}
    if module_name not in available:
        raise ValueError(f"Unknown bot module: {module_name}")

    return importlib.import_module(module_name)


def inspect_bot(module_name: str) -> BotInfo | None:
    ensure_project_on_path()
    try:
        module = importlib.import_module(module_name)
        bot_cls = getattr(module, "Bot")
        bot = bot_cls()
    except Exception:
        return None

    get_bid = getattr(bot, "get_bid", None)
    if not callable(get_bid):
        return None

    signature = inspect.signature(get_bid)
    required_names = {
        "current_round",
        "bots",
        "winner_pays",
        "artists_and_values",
        "round_limit",
        "starting_budget",
        "painting_order",
        "target_collection",
        "my_bot_details",
        "current_painting",
        "winner_ids",
        "amounts_paid",
    }
    if not required_names.issubset(signature.parameters):
        return None

    display_name = str(getattr(bot, "name", module_name.rsplit(".", 1)[-1]))
    return BotInfo(module=module_name, display_name=display_name)


def discover_bots() -> list[BotInfo]:
    ensure_project_on_path()
    if not BOTS_DIR.exists():
        return []

    bots: list[BotInfo] = []
    for path in sorted(BOTS_DIR.iterdir()):
        if not _is_candidate(path):
            continue
        module_name = f"bots.{path.stem}"
        info = inspect_bot(module_name)
        if info is not None:
            bots.append(info)

    return bots
