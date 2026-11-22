# Local web arena

The project runs locally with Flask and Next.js. Python 3.10+ and Node.js 22 LTS are recommended.

## Run the backend

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r web-app/backend/requirements-dev.txt
cd web-app
python -m flask --app backend.app:create_app run --host 127.0.0.1 --port 5000
```

On Windows PowerShell, activate the environment with `.\.venv\Scripts\Activate.ps1`. The API is available at `http://127.0.0.1:5000/api/bots`.

## Run the frontend

From the repository root in a second terminal:

```bash
cd web-app/frontend
npm ci
npm run dev
```

Open `http://localhost:3000`. The browser connects to `http://127.0.0.1:5000` by default. Set `NEXT_PUBLIC_API_BASE_URL` in `web-app/frontend/.env.local` to change the API address. Restart the development server or rebuild the production frontend after changing it.

## Run tests and build

Run Python checks from the repository root with the virtual environment active:

```bash
python -m pytest -q
ruff check
ruff format --check
```

Then run the frontend checks from `web-app/frontend` in the same environment:

```bash
npm ci
npm run check
npm run lint
npx playwright install chromium
npm test
npm run build
npm run start
```

The browser suite launches its own Flask and Next.js servers on ports 5101 and 3100. Linux may need `npx playwright install --with-deps chromium`. [Playwright CI installation](https://playwright.dev/docs/ci) To use an existing Chromium or Chrome installation, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to its executable path.

Run the original coursework auction from the root with `python auctioneer.py`. Run the seeded comparison with `python benchmark.py --trials 5`. See the [project README](README.md) for rule differences and benchmark options.

## Run, replay, and export a game

Select Coursework reference for 200 rounds and 1,001 starting credits per player. Select Custom simulation to edit these settings. Give each seat a name and strategy. Several seats can use the same strategy. Set a seed to reproduce the auction or leave it empty and record the generated seed shown in the controls. Round delay affects playback speed during a live run.

Select a past round in Round history, use the slider to jump, or play a completed game's stored history. The game URL can reopen a live or recently completed auction. Disconnecting leaves the worker running. Cancelling keeps committed rounds and marks the results as partial. The round CSV contains one row per player per round. Game JSON includes the configuration and ordered events. Summary JSON includes winners and final rankings.

### API

| Method and path | Behavior |
| --- | --- |
| `GET /api/bots` | Registered strategies and configured form limits |
| `POST /api/games` | Validates configuration and creates a game. Returns `gameId` and the effective configuration. |
| `GET /api/games/<id>` | State, configuration, and latest event ID |
| `GET /api/games/<id>/events` | Starts the worker once and streams ordered events. Use `Last-Event-ID` or `?after=N` to resume. |
| `GET /api/games/<id>/results` | Versioned configuration, state, and event history |
| `POST /api/games/<id>/reset` | Requests cancellation. Returns success for previously reset or missing IDs for legacy clients. |

A creation payload includes two or more `players` with `botModule`, `playerName`, and `startingBudget`. Top-level fields are `mode` (`reference` or `custom`), `roundLimit`, `seed`, and `tickMs`. The server selects reference rules when defaults are used and mode is omitted. Other round or budget values select custom rules. An empty seed generates a new one.

Events have one-based SSE IDs. Event types are `game_started`, `bot_error`, `round_finished`, `game_finished`, `game_cancelled`, and `game_failed`. Bot errors vary in scope. A bid exception becomes a zero for that round. A timed-out or exited bot is disabled for the remainder of the game. Failed simulations emit a distinct terminal event. Request errors have `error` and `code` fields. Unknown games return HTTP 404, recently expired games return 410, and full game or worker capacity returns 429.

## Settings

Use these backend environment variables. The values below are defaults.

| Variable | Default |
| --- | --- |
| `AUCTION_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` |
| `AUCTION_MAX_PLAYERS`, `AUCTION_MAX_ROUNDS`, `AUCTION_MAX_BUDGET` | 16, 500, 100000 |
| `AUCTION_MAX_TICK_MS`, `AUCTION_MAX_CONTENT_LENGTH` | 1000 ms, 16384 bytes |
| `AUCTION_MAX_GAMES`, `AUCTION_MAX_RUNNING`, `AUCTION_MAX_SUBSCRIBERS` | 16 stored games, 3 running games, 12 subscribers per game |
| `AUCTION_CREATED_TTL`, `AUCTION_RESULT_TTL` | 120 seconds to open a created game, 900 seconds to retrieve terminal results |
| `AUCTION_BOT_TIMEOUT`, `AUCTION_SSE_HEARTBEAT` | 0.5 seconds per bid, 10 seconds between idle stream comments |

Games expire on subsequent API lookups or creation attempts. The bounded store lives in the Flask process and a restart clears it. For a deployment using a WSGI server, run a single threaded worker process, allow enough threads for your SSE clients plus ordinary requests, and disable response buffering at the proxy. Bind to loopback for local use. Any deployment beyond localhost needs appropriate access control and trusted bot code.

## Troubleshooting

- If strategies fail to load, open the bots API URL directly and confirm Flask is running. Make sure the configured allowed origin exactly matches the frontend URL including scheme and port.
- If Flask cannot import `backend`, start it from `web-app`. Verify that the Python environment used by Flask has the backend requirements installed.
- If a run stalls behind a proxy, check that SSE responses stream immediately. Resume from the game URL after the connection recovers.
- If no winner is shown after completion, inspect the final rankings. A missing artist gives that player a zero score.
- If build checks fail after switching branches, run `npm ci` in `web-app/frontend` and restart Next.js.
