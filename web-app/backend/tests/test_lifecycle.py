from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from backend.app import create_app
from backend.bot_registry import BOT_NAMES
from backend.simulator import DynamicAuctionGame

PLAYERS = [
    {"playerName": "A", "botModule": "bots.random_bot", "startingBudget": 1001},
    {"playerName": "B", "botModule": "bots.random_bot", "startingBudget": 1001},
]


@pytest.fixture
def app():
    return create_app({"TESTING": True, "SSE_HEARTBEAT": 0.05})


def new_game(client, **fields):
    response = client.post(
        "/api/games", json={"players": PLAYERS, "roundLimit": 8, "tickMs": 0, "seed": 42, **fields}
    )
    assert response.status_code == 200, response.get_json()
    return "/api/games/" + response.get_json()["gameId"]


def stream(client, path, **kwargs):
    with client.get(path + "/events", buffered=True, **kwargs) as response:
        assert response.status_code == 200
        events = []
        for frame in response.get_data(as_text=True).strip().split("\n\n"):
            if frame.startswith("id: "):
                identifier, payload = frame.split("\n", 1)
                events.append((int(identifier[4:]), json.loads(payload[6:])))
        return events


@pytest.mark.parametrize(
    "patch",
    [
        {"players": None},
        {"players": {"a": 1, "b": 2}},
        {"players": PLAYERS * 9},
        {"players": [None, PLAYERS[0]]},
        {"players": [{**PLAYERS[0], "botModule": "os"}, PLAYERS[1]]},
        {"players": [{**PLAYERS[0], "botModule": []}, PLAYERS[1]]},
        {"players": [{**PLAYERS[0], "startingBudget": 1.5}, PLAYERS[1]]},
        {"players": [{**PLAYERS[0], "startingBudget": True}, PLAYERS[1]]},
        {"players": [{**PLAYERS[0], "startingBudget": 0}, PLAYERS[1]]},
        {"players": [{**PLAYERS[0], "startingBudget": 100001}, PLAYERS[1]]},
        {"players": [{**PLAYERS[0], "playerName": "  "}, PLAYERS[1]]},
        {"players": [{**PLAYERS[0], "playerName": "A\nB"}, PLAYERS[1]]},
        {"players": [{**PLAYERS[0], "playerName": "a" * 61}, PLAYERS[1]]},
        {"players": [{**PLAYERS[0], "playerName": 10}, PLAYERS[1]]},
        {"roundLimit": 0},
        {"roundLimit": 501},
        {"roundLimit": True},
        {"roundLimit": "4.5"},
        {"seed": 2**53},
        {"seed": []},
        {"seed": False},
        {"tickMs": -1},
        {"tickMs": 1001},
        {"tickMs": None},
        {"tickMs": 1.5},
        {"mode": "reference", "roundLimit": 8},
        {"mode": "target"},
    ],
)
def test_validation_errors_are_structured(app, patch):
    client = app.test_client()
    response = client.post("/api/games", json={"players": PLAYERS, **patch})
    assert response.status_code == 400
    assert response.json["code"] == "invalid_configuration"
    assert response.json["error"]


@pytest.mark.parametrize("body", ["{", "null", "[]", '"wrong"'])
def test_requires_json_object(app, body):
    response = app.test_client().post("/api/games", data=body, content_type="application/json")
    assert response.status_code == 400
    assert response.json["code"] == "invalid_json"


def test_max_request_size_and_cors(app):
    client = app.test_client()
    response = client.post("/api/games", data="a" * 16400, content_type="application/json")
    assert response.status_code == 413
    assert response.json["code"] == "request_entity_too_large"
    trusted = "http://localhost:3000"
    response = client.options("/api/games", headers={"Origin": trusted})
    assert response.headers["Access-Control-Allow-Origin"] == trusted
    assert "Last-Event-ID" in response.headers["Access-Control-Allow-Headers"]
    response = client.get("/api/bots", headers={"Origin": "https://example.invalid"})
    assert "Access-Control-Allow-Origin" not in response.headers
    assert client.get("/api/games/unknown/events").json["code"] == "unknown_game"


def test_two_concurrent_subscribers_see_one_identical_run(app):
    game = new_game(app.test_client(), tickMs=5)
    ready = Barrier(2)

    def subscribe():
        ready.wait(timeout=3)
        return stream(app.test_client(), game)

    with ThreadPoolExecutor(max_workers=2) as pool:
        subscribers = [pool.submit(subscribe) for _ in range(2)]
        first, second = [subscriber.result(timeout=10) for subscriber in subscribers]
    assert first == second
    assert [index for index, _ in first] == list(range(1, 11))
    events = [event for _, event in first]
    assert [event["round"] for event in events[1:-1]] == list(range(1, 9))
    assert events[-1]["type"] == "game_finished"
    record = app.test_client().get(game + "/results").json
    assert record["status"] == "completed"
    assert record["events"] == events


def test_disconnect_resumes_after_cursor_and_completed_replay(app):
    client = app.test_client()
    game = new_game(client, tickMs=10)
    with client.get(game + "/events") as response:
        assert next(iter(response.response)).startswith(b"id: 1\n")
    resumed = stream(client, game, headers={"Last-Event-ID": "1"}, query_string={"after": 0})
    assert resumed[0][0] == 2
    assert resumed[-1][1]["type"] == "game_finished"
    assert stream(client, game)[1:] == resumed
    assert stream(client, game, query_string={"after": resumed[-1][0]}) == []
    assert client.get(game + "/events?after=999").json["code"] == "invalid_cursor"


def test_cancel_interrupts_delay_and_preserves_completed_rounds(app):
    client = app.test_client()
    game = new_game(client, roundLimit=50, tickMs=1000)
    with client.get(game + "/events") as response:
        identifier = 0
        for frame in response.response:
            if frame.startswith(b"id: 2\n"):
                identifier = 2
                break
        assert identifier == 2
    assert client.post(game + "/reset").json == {"ok": True}
    events = stream(client, game)
    assert [event["type"] for _, event in events] == [
        "game_started",
        "round_finished",
        "game_cancelled",
    ]
    assert stream(client, game) == events
    assert client.get(game).json["status"] == "cancelled"


def test_cancel_created_game_never_starts_worker(app):
    client = app.test_client()
    game = new_game(client)
    assert client.get(game).json["status"] == "created"
    client.post(game + "/reset")
    assert [event["type"] for _, event in stream(client, game)] == ["game_cancelled"]


def test_failed_game_has_terminal_event_and_results(app, monkeypatch):
    def fail(_self):
        raise RuntimeError("internal exception")

    monkeypatch.setattr(DynamicAuctionGame, "_collect_bids", fail)
    client = app.test_client()
    game = new_game(client)
    events = stream(client, game)
    assert [event["type"] for _, event in events] == ["game_started", "game_failed"]
    assert "internal exception" not in events[-1][1]["message"]
    assert client.get(game + "/results").json["status"] == "failed"


def test_storage_limits_and_ttl():
    client = create_app({"TESTING": True, "RESULT_TTL": 0, "MAX_GAMES": 1}).test_client()
    game = new_game(client)
    response = client.post("/api/games", json={"players": PLAYERS})
    assert response.status_code == 429
    assert stream(client, game)[-1][1]["type"] == "game_finished"
    assert client.get(game + "/results").status_code == 410
    assert new_game(client) != game

    client = create_app({"TESTING": True, "CREATED_TTL": 0}).test_client()
    assert client.get(new_game(client)).json["code"] == "game_expired"


def test_worker_timeout_disables_only_that_bot(app, monkeypatch):
    module = "backend.tests.worker_fixtures"
    monkeypatch.setitem(BOT_NAMES, module, "Worker test bot")
    players = [
        {**PLAYERS[0], "botModule": module, "startingBudget": 500},
        {**PLAYERS[1], "botModule": module, "startingBudget": 600},
        {**PLAYERS[1], "botModule": module, "startingBudget": 700},
    ]
    client = app.test_client()
    game = new_game(client, players=players, roundLimit=3)
    start = time.monotonic()
    events = [event for _, event in stream(client, game)]
    assert time.monotonic() - start < 10
    errors = [event for event in events if event["type"] == "bot_error"]
    assert [error["playerId"] for error in errors] == [
        "Worker test bot-1",
        "Worker test bot-2",
        "Worker test bot-3",
    ]
    assert "timed out" in errors[0]["message"]
    assert "test crash" in errors[1]["message"]
    assert "exited" in errors[2]["message"]
    rounds = [event for event in events if event["type"] == "round_finished"]
    assert [event["bids"]["Worker test bot-1"] for event in rounds] == [0, 0, 0]
    assert rounds[1]["bids"]["Worker test bot-2"] > 0
    assert events[-1]["type"] == "game_finished"


def test_seeded_web_games_have_identical_results_in_parallel(app):
    def run():
        client = app.test_client()
        game = new_game(client, players=[*PLAYERS, {**PLAYERS[0], "botModule": "bots.u5726455_i2"}])
        return [event for _, event in stream(client, game)][1:]

    with ThreadPoolExecutor(max_workers=2) as pool:
        games = [pool.submit(run) for _ in range(2)]
        assert games[0].result(timeout=10) == games[1].result(timeout=10)


def test_running_and_subscriber_limits_does_not_start_queued_game():
    app = create_app({"TESTING": True, "MAX_RUNNING": 1, "MAX_SUBSCRIBERS": 1})
    client = app.test_client()
    game = new_game(client, tickMs=1000)
    queued = new_game(client)
    with client.get(game + "/events"):
        assert app.test_client().get(game + "/events").json["code"] == "too_many_subscribers"
        assert app.test_client().get(queued + "/events").json["code"] == "workers_busy"
        assert client.get(queued).json["status"] == "created"
        client.post(game + "/reset")
