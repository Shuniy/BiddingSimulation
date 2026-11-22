# BiddingSimulation engineering report

## A. Executive summary

The web frontend was missing its API and event modules. The original CLI could fail on its first CSV write, the SSE route allowed readers to advance and discard shared game state, random bots escaped the game seed, and Adaptive Market Bidder could use another instance's state. The legacy benchmarks also ran divergent copies of the rules and could count an all-zero score tie as a win.

The repository now has a shared simulator, explicit reference and custom rules, bounded bot execution, replayable events, a working Next.js arena, and reproducible strategy comparisons. The original `auctioneer.py` is byte-for-byte unchanged. The remaining operational limits are local, in-memory game storage and trusted strategy code. The GitHub Actions jobs are configured and their substantive commands were exercised locally. A hosted run still depends on a push or pull request.

## B. File-by-file changes

| Files | Change |
| --- | --- |
| `utilities.py`, `arena.py`, `.gitignore` | Create CSV parent directories and preserve the legacy delimiter. Clean up the sample launcher and exclude generated logs and reports. |
| `bots/u5726455_i2.py`, `bots/random_bot.py` | Key Adaptive Market Bidder state by seat ID. Let the direct Python simulator inject a private RNG into the random strategy. |
| `bots/u5726455_final.py`, `bots/u5726455_i2_i.py`, `bots/u5726455_i2_i_i2_i.py`, `bots/u5726455_i_i2.py` | Remove a dormant name lookup and unused code. The strategy policies stay intact, including the weighted blend's corrected Adaptive Market advisor. |
| `web-app/backend/simulator.py` | Centralize rules, bid validation, scoring, accounting, snapshots, and deterministic randomness. |
| `web-app/backend/bot_execution.py`, `bot_registry.py` | Run each web bot in a persistent process with its own seed and deadline. Use allowlisted strategy metadata without importing bot code during API discovery. |
| `web-app/backend/lifecycle.py`, `app.py` | Give each game one producer and independent SSE cursors. Add cancellation, terminal failure, expiry, configurable limits, status and results endpoints, structured errors, and origin allowlisting. |
| `web-app/frontend/src/lib/api.ts`, `types.ts`, `events.ts`, `useAuction.ts`, `exports.ts` | Restore the typed API client and handle validated stream events, stale requests, reconnect, and downloads. |
| `web-app/frontend/src/app/page.tsx`, `globals.css`, `src/components/` | Preserve light and dark themes while extracting setup, controls, standings, paginated history, playback, errors, charts, and exports. |
| `benchmark.py` and the four existing validation entry points | Replace duplicate auction engines with one scenario runner. Track seed and seat, positive shared wins, no-winner games, score, rank, and spending. |
| `web-app/backend/tests/`, `web-app/frontend/tests/` | Preserve the existing tests and add reference parity, edge cases, process deadlines, seeded rooms, concurrent event streams, and browser coverage. |
| `pyproject.toml`, `requirements-dev.txt`, `package.json`, `package-lock.json`, `eslint.config.mjs`, `playwright.config.ts`, `.github/workflows/ci.yml` | Configure style, testing, clean installs, and CI. Update Next.js within version 15 and override its nested PostCSS to the patched project version. |
| `README.md`, `WEB_APP.md` | Document reproducible setup, rules, architecture, strategy inputs, experiments, API, and troubleshooting. |

## C. Verification

Local verification used macOS, Python 3.10.19, Flask 3.1.3 in a fresh virtual environment, Node.js 26.9.0, and installed Chrome. The hosted workflow targets Python 3.12 and Node.js 22 on Ubuntu.

| Command or check | Result |
| --- | --- |
| `python -m pip install -r web-app/backend/requirements-dev.txt` | Installed successfully in a fresh virtual environment. |
| `python -m compileall -q auctioneer.py arena.py benchmark.py utilities.py bot_validation_test.py round_sweep_test.py short_auction_validation.py test_final_bot_cases.py bots web-app/backend` | Passed. |
| `ruff check` and `ruff format --check` | Passed. All 19 files in the format scope were already formatted. |
| `python -m pytest -q` | 85 passed. |
| `python auctioneer.py` in a temporary copy without `data/` | Completed all 200 rounds and wrote 200 semicolon-delimited rows. |
| `python /tmp/bidding-api-smoke.py` | Started the documented Flask application, discovered 13 bots, completed two parallel seeded 200-round auctions, and verified an independent subscriber and replay after event 100. |
| `npm ci --cache /tmp/bidding-npm-cache` | Passed. npm reported zero known dependency vulnerabilities. The isolated source copy also installed from the warmed cache. |
| `npm run check` and `npm run lint` | Passed in the workspace and isolated source copy. |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" npm test` | 5 passed against live Flask and Next.js servers. Covered strategy loading, form validation, a completed auction, comparison chart, early rounds, replay, exports, reconnect, cancellation, bot errors, and a zero-score finish. |
| `NEXT_TELEMETRY_DISABLED=1 npm run build` | Passed in the workspace and isolated source copy. Next.js 15.5.29 generated four static pages. The arena route was 9.6 kB and its first-load JavaScript was 112 kB. |
| `python benchmark.py --room random_bot u5726455_i2 random_bot --rounds 12 --seeds 13 37` twice, with separate output directories | Passed. `diff -r` reported identical JSON, CSV, and Markdown. |
| `python test_final_bot_cases.py --runs 1 --output /tmp/bidding-legacy-cases` | Produced reports for all six historical cases. |
| `git diff --check` and `git diff --exit-code HEAD -- auctioneer.py` | Passed. The reference blob hash is `3001d9778612d6a07fbd087613d7e4b5cce8c0b4`. |

Local network permissions had to allow package downloads and loopback server startup. Initial browser assertions used ambiguous selectors. The final browser suite used scoped accessibility queries and passed. The CI workflow parsed locally with both jobs and both triggers present. Its hosted Ubuntu run and browser installation remain unverified.

## D. Simulation validation

- Reference parity tests use controlled bids and match the original painting sequence, bot arguments, round ordering, tie outcomes, payments, budgets, collections, scores, and winner ordering. They cover generated and explicitly supplied painting orders.
- Reference mode preserves affordable negative bids. Custom mode converts negative bids to zero and keeps bot inputs in seat order. The web worker also applies a deadline and protects the browser's exact integer credit range.
- Starting conditions are 200 rounds and 1,001 credits in reference mode. Changing either selects custom rules by default. The collection target remains a bot input. Positive top scores can share a win and all-zero scores produce no winner.
- Both local and process-isolated web runs reproduced same-seed results. The HTTP smoke included two Adaptive Market Bidder seats. Per-strategy tests checked distinct seat and budget handling across all 13 strategies, with additional state and history assertions for the strategies that build a normalized state.
- The lifecycle tests cover two concurrent subscribers, an interrupted stream, replay after a cursor, cancellation of created and running games, worker exceptions and deadlines, expiry, and capacity limits.

## E. Performance and benchmarking

The HTTP smoke finished two parallel 200-round, four-player reference games in 0.81 seconds with the round delay set to zero. A profile of one five-player, 200-round reference benchmark attributed about 1.57 of 1.68 cumulative seconds to deep copying. Copying isolates strategy inputs and supplies each bot its own copied state in reference mode. That cost grows with the round history and with large bot state.

`python benchmark.py --trials 5 --output data/benchmark-validation` evaluated all 13 strategies in 52 scenarios and 910 games in 82 seconds. It used five independent seeds, two and five seats, 50 and 200 rounds, and every seat rotation. The only bidding issues in this matrix were over-budget bids converted to zero.

| Strategy in five-player mixed room | Rounds and mode | Wins | Mean score | Mean budget left | Score per credit |
| --- | --- | ---: | ---: | ---: | ---: |
| Fixed-Bid Specialist | 50 custom | 25/25 | 1,320 | 11.0 | 1.33 |
| Price Profile Bidder | 50 custom | 20/25 | 2,776 | 147.2 | 3.25 |
| Fixed Bid 15 | 200 reference | 11/25 | 67,874 | 11.0 | 68.56 |
| Q-Learning Bidder | 200 reference | 0/25 | 42,070 | 49.8 | 44.23 |

The short-room win leader had a lower mean score and score per credit than Price Profile Bidder against the same roster. Fixed Bid 15 led the focus strategies in the 200-round mixed room, with a 44% win rate and a 28%–56% seed-bootstrap interval. The Q-Learning Bidder's fallback and lookup policies were evaluated within this matrix, which provides no basis for a general superiority claim. The 50- and 200-round rows also use different rule modes. Five seeds limit the precision of the intervals, and constant samples give degenerate intervals.

Full results are in the [readable summary](data/benchmark-validation/summary.md), [CSV](data/benchmark-validation/summary.csv), and [JSON trial data](data/benchmark-validation/results.json).

## F. Remaining recommendations

- Use more independent seeds and stronger opponent rosters before changing bidding policies. Several existing heuristics have absolute phase thresholds at rounds 80 or 150. Those thresholds remain part of the published strategies and can affect short-auction results.
- Keep the single-process, in-memory store for local use. If deployment later requires several backend processes or replay across restarts, move game ownership and events to durable storage.
- For user-supplied bot code, use operating-system isolation with CPU, memory, filesystem, and network controls. The current processes enforce deadlines for trusted repository strategies.
- Reproducing Q-table training requires the missing training code and data. The frozen table and heuristic fallbacks are reproducible for inference.
