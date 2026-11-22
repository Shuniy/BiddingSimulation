from __future__ import annotations

import json
import uuid
from threading import Lock
from typing import Any

from flask import Flask, Response, jsonify, request, stream_with_context

from .bot_registry import discover_bots
from .simulator import (
    DEFAULT_ROUND_LIMIT,
    DynamicAuctionGame,
    build_player_configs,
    normalise_positive_int,
)


def create_app() -> Flask:
    app = Flask(__name__)
    games: dict[str, DynamicAuctionGame] = {}
    lock = Lock()

    @app.after_request
    def add_cors_headers(response: Response) -> Response:
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        return response

    @app.route("/api/bots", methods=["GET"])
    def bots() -> Any:
        return jsonify({"bots": [bot.to_dict() for bot in discover_bots()]})

    @app.route("/api/games", methods=["OPTIONS"])
    @app.route("/api/games/<game_id>/reset", methods=["OPTIONS"])
    def options(game_id: str | None = None) -> Response:
        return Response(status=204)

    @app.route("/api/games", methods=["POST"])
    def create_game() -> Any:
        payload = request.get_json(silent=True) or {}
        try:
            players = build_player_configs(payload.get("players", []))
            round_limit = normalise_positive_int(
                payload.get("roundLimit", DEFAULT_ROUND_LIMIT), "roundLimit"
            )
            seed = payload.get("seed")
            if seed in ("", None):
                seed = None
            else:
                seed = int(seed)
            tick_ms = max(0, int(payload.get("tickMs", 150) or 0))
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        game_id = uuid.uuid4().hex
        game = DynamicAuctionGame(
            game_id=game_id,
            players=players,
            round_limit=round_limit,
            seed=seed,
            tick_ms=tick_ms,
        )
        with lock:
            games[game_id] = game

        return jsonify({"gameId": game_id})

    @app.route("/api/games/<game_id>/events", methods=["GET"])
    def game_events(game_id: str) -> Any:
        with lock:
            game = games.get(game_id)
        if game is None:
            return jsonify({"error": "Unknown game"}), 404

        def generate():
            try:
                for event in game.event_stream():
                    yield f"data: {json.dumps(event)}\n\n"
            finally:
                with lock:
                    games.pop(game_id, None)

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.route("/api/games/<game_id>/reset", methods=["POST"])
    def reset_game(game_id: str) -> Any:
        with lock:
            game = games.pop(game_id, None)
        if game is not None:
            game.cancel()
        return jsonify({"ok": True})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)

