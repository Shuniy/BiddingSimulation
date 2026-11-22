from __future__ import annotations

import json
import math
import uuid
from typing import Any

from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import HTTPException

from .bot_registry import discover_bots
from .lifecycle import GameStore, GameUnavailable
from .simulator import (
    DEFAULT_ROUND_LIMIT,
    MAX_SAFE_INTEGER,
    DynamicAuctionGame,
    build_player_configs,
    parse_integer,
    select_mode,
)


def bounded_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    parsed = parse_integer(value)
    if parsed is None or not minimum <= parsed <= maximum:
        raise ValueError(f"{field} must be an integer from {minimum} to {maximum}")
    return parsed


def create_app(config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        CORS_ORIGINS="http://localhost:3000,http://127.0.0.1:3000",
        MAX_CONTENT_LENGTH=16_384,
        MAX_PLAYERS=16,
        MAX_ROUNDS=500,
        MAX_BUDGET=100_000,
        MAX_TICK_MS=1000,
        MAX_GAMES=16,
        MAX_RUNNING=3,
        MAX_SUBSCRIBERS=12,
        CREATED_TTL=120,
        RESULT_TTL=900,
        BOT_TIMEOUT=0.5,
        SSE_HEARTBEAT=10,
    )
    app.config.from_prefixed_env(prefix="AUCTION")
    if config:
        app.config.update(config)

    for key in ("BOT_TIMEOUT", "SSE_HEARTBEAT", "CREATED_TTL", "RESULT_TTL"):
        value = app.config[key]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f"AUCTION_{key} must be a finite number of seconds")
        if key in ("BOT_TIMEOUT", "SSE_HEARTBEAT") and value == 0:
            raise ValueError(f"AUCTION_{key} must be greater than zero")

    store = GameStore(
        capacity=app.config["MAX_GAMES"],
        max_running=app.config["MAX_RUNNING"],
        created_ttl=app.config["CREATED_TTL"],
        result_ttl=app.config["RESULT_TTL"],
        max_subscribers=app.config["MAX_SUBSCRIBERS"],
        logger=app.logger,
    )
    app.extensions["auction_games"] = store
    origin_config = app.config["CORS_ORIGINS"]
    if isinstance(origin_config, str):
        origin_config = origin_config.split(",")
    origins = {origin.strip() for origin in origin_config}

    @app.after_request
    def add_cors_headers(response: Response) -> Response:
        origin = request.headers.get("Origin")
        if origin in origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Last-Event-ID"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.vary.add("Origin")
        return response

    @app.errorhandler(GameUnavailable)
    def unavailable(exc: GameUnavailable) -> Any:
        return jsonify(error=str(exc), code=exc.code), exc.status

    @app.errorhandler(HTTPException)
    def http_error(exc: HTTPException) -> Any:
        return jsonify(error=exc.description, code=exc.name.lower().replace(" ", "_")), exc.code

    @app.get("/api/bots")
    def bots() -> Any:
        return jsonify(
            bots=[bot.to_dict() for bot in discover_bots()],
            limits={
                "maxPlayers": app.config["MAX_PLAYERS"],
                "maxBudget": app.config["MAX_BUDGET"],
                "maxRounds": app.config["MAX_ROUNDS"],
                "maxTickMs": app.config["MAX_TICK_MS"],
            },
        )

    @app.post("/api/games")
    def create_game() -> Any:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="Request body must be a JSON object", code="invalid_json"), 400
        try:
            players = build_player_configs(
                payload.get("players"),
                max_players=app.config["MAX_PLAYERS"],
                max_budget=app.config["MAX_BUDGET"],
            )
            round_limit = bounded_int(
                payload.get("roundLimit", DEFAULT_ROUND_LIMIT),
                "roundLimit",
                1,
                app.config["MAX_ROUNDS"],
            )
            seed = payload.get("seed")
            if seed in (None, ""):
                seed = None
            else:
                seed = bounded_int(seed, "seed", -MAX_SAFE_INTEGER, MAX_SAFE_INTEGER)
            tick_ms = bounded_int(
                payload.get("tickMs", 150), "tickMs", 0, app.config["MAX_TICK_MS"]
            )
            mode = select_mode(players, round_limit, payload.get("mode"))
        except ValueError as exc:
            return jsonify(error=str(exc), code="invalid_configuration"), 400

        game = DynamicAuctionGame(
            uuid.uuid4().hex,
            players,
            round_limit,
            seed,
            tick_ms,
            mode=mode,
            bot_timeout=app.config["BOT_TIMEOUT"],
        )
        store.create(game)
        return jsonify(gameId=game.game_id, configuration=game.configuration())

    @app.get("/api/games/<game_id>")
    def game_status(game_id: str) -> Any:
        return jsonify(store.get(game_id).export(include_events=False))

    @app.get("/api/games/<game_id>/results")
    def results(game_id: str) -> Any:
        return jsonify(store.get(game_id).export(include_events=True))

    @app.get("/api/games/<game_id>/events")
    def game_events(game_id: str) -> Response:
        after = request.headers.get("Last-Event-ID") or request.args.get("after", "0")
        try:
            cursor = bounded_int(after, "event cursor", 0, MAX_SAFE_INTEGER)
        except ValueError as exc:
            raise GameUnavailable(str(exc), "invalid_cursor", 400) from exc
        record = store.open_stream(game_id, cursor)

        def generate():
            for item in record.subscribe(cursor, app.config["SSE_HEARTBEAT"]):
                if item is None:
                    yield ": heartbeat\n\n"
                else:
                    index, event = item
                    yield f"id: {index}\ndata: {json.dumps(event)}\n\n"

        response = Response(
            generate(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )
        response.call_on_close(lambda: store.close_stream(record))
        return response

    @app.post("/api/games/<game_id>/reset")
    def reset_game(game_id: str) -> Any:
        # Legacy reset is idempotent, including for an already-expired game.
        try:
            store.cancel(game_id)
        except GameUnavailable as exc:
            if exc.status not in (404, 410):
                raise
        return jsonify(ok=True)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, threaded=True)
