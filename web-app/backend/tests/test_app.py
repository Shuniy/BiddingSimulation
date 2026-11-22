from __future__ import annotations

import json

from backend.app import create_app


def test_get_bots_returns_available_bot_modules():
    client = create_app().test_client()

    response = client.get("/api/bots")

    assert response.status_code == 200
    names_by_module = {bot["module"]: bot["displayName"] for bot in response.get_json()["bots"]}
    assert names_by_module["bots.random_budget_bidder"] == "Random Budget Bidder"
    assert names_by_module["bots.fixed_bid_10"] == "Fixed Bid 10"
    assert names_by_module["bots.collection_balancer"] == "Collection Balancer"
    assert names_by_module["bots.price_profile_bidder"] == "Price Profile Bidder"


def test_create_game_rejects_too_few_players():
    client = create_app().test_client()

    response = client.post(
        "/api/games",
        json={
            "players": [
                {
                    "playerName": "Solo",
                    "botModule": "bots.random_budget_bidder",
                    "startingBudget": 1001,
                }
            ]
        },
    )

    assert response.status_code == 400


def test_sse_stream_emits_start_round_and_finish_events():
    client = create_app().test_client()
    create_response = client.post(
        "/api/games",
        json={
            "players": [
                {
                    "playerName": "Random",
                    "botModule": "bots.random_budget_bidder",
                    "startingBudget": 1001,
                },
                {
                    "playerName": "Flat",
                    "botModule": "bots.fixed_bid_10",
                    "startingBudget": 1001,
                },
            ],
            "roundLimit": 2,
            "seed": 4,
            "tickMs": 0,
        },
    )
    game_id = create_response.get_json()["gameId"]

    stream_response = client.get(f"/api/games/{game_id}/events")
    events = [
        json.loads(line[6:])
        for line in stream_response.get_data(as_text=True).splitlines()
        if line.startswith("data: ")
    ]
    stream_response.close()

    assert events[0]["type"] == "game_started"
    assert [event["type"] for event in events].count("round_finished") == 2
    assert events[-1]["type"] == "game_finished"


def test_reset_unknown_game_is_ok():
    client = create_app().test_client()

    response = client.post("/api/games/missing/reset")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
