"use client";

import {
  Moon,
  Play,
  RefreshCcw,
  SlidersHorizontal,
  Sun,
  Trophy,
} from "lucide-react";
import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";

import { API_BASE_URL, apiJson } from "@/lib/api";
import type {
  Artist,
  BotErrorEvent,
  BotInfo,
  GameEvent,
  PlayerConfig,
  PlayerSnapshot,
  RoundFinishedEvent,
} from "@/lib/types";

const ARTISTS: Artist[] = ["Da Vinci", "Picasso", "Rembrandt", "Van Gogh"];
const DEFAULT_BUDGET = 1001;

type ThemeMode = "system" | "light" | "dark";
type Status = "idle" | "running" | "complete" | "error";

const createPlayer = (index: number, botModule = ""): PlayerConfig => ({
  playerName: `Player ${index}`,
  botModule,
  startingBudget: DEFAULT_BUDGET,
});

const formatPlayerName = (players: PlayerSnapshot[], id: string) => {
  const player = players.find((candidate) => candidate.id === id);
  return player ? `${player.playerName} (${player.botName})` : id;
};

export default function Home() {
  const [bots, setBots] = useState<BotInfo[]>([]);
  const [players, setPlayers] = useState<PlayerConfig[]>([
    createPlayer(1),
    createPlayer(2),
  ]);
  const [roundLimit, setRoundLimit] = useState(200);
  const [seed, setSeed] = useState("");
  const [tickMs, setTickMs] = useState(150);
  const [status, setStatus] = useState<Status>("idle");
  const [gameId, setGameId] = useState<string | null>(null);
  const [snapshots, setSnapshots] = useState<PlayerSnapshot[]>([]);
  const [roundLog, setRoundLog] = useState<RoundFinishedEvent[]>([]);
  const [errors, setErrors] = useState<BotErrorEvent[]>([]);
  const [currentRound, setCurrentRound] = useState(0);
  const [currentPainting, setCurrentPainting] = useState<Artist | null>(null);
  const [winners, setWinners] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [theme, setTheme] = useState<ThemeMode>("system");
  const sourceRef = useRef<EventSource | null>(null);

  const firstBotModule = bots[0]?.module ?? "";
  const latestRound = roundLog[0];

  const winnerText = useMemo(() => {
    if (winners.length === 0) {
      return "No winner. Every final score is zero.";
    }
    return winners.map((winner) => formatPlayerName(snapshots, winner)).join(", ");
  }, [snapshots, winners]);

  useEffect(() => {
    const storedTheme = window.localStorage.getItem("auction-theme") as ThemeMode | null;
    if (storedTheme === "light" || storedTheme === "dark" || storedTheme === "system") {
      setTheme(storedTheme);
    }
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const shouldUseDark = theme === "dark" || (theme === "system" && prefersDark);
    root.classList.toggle("dark", shouldUseDark);
    window.localStorage.setItem("auction-theme", theme);
  }, [theme]);

  useEffect(() => {
    let cancelled = false;

    apiJson<{ bots: BotInfo[] }>("/api/bots")
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setBots(payload.bots);
        const defaultModule = payload.bots[0]?.module ?? "";
        setPlayers((current) =>
          current.map((player) => ({
            ...player,
            botModule: player.botModule || defaultModule,
          })),
        );
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setStatus("error");
          setMessage(error.message);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    return () => {
      sourceRef.current?.close();
    };
  }, []);

  const updatePlayerCount = (value: number) => {
    const count = Math.max(2, value || 2);
    setPlayers((current) => {
      if (count <= current.length) {
        return current.slice(0, count);
      }
      const next = [...current];
      for (let index = current.length + 1; index <= count; index += 1) {
        next.push(createPlayer(index, firstBotModule));
      }
      return next;
    });
  };

  const updatePlayer = (
    index: number,
    field: keyof PlayerConfig,
    event: ChangeEvent<HTMLInputElement | HTMLSelectElement>,
  ) => {
    const value =
      field === "startingBudget" ? Number(event.target.value) : event.target.value;
    setPlayers((current) =>
      current.map((player, playerIndex) =>
        playerIndex === index ? { ...player, [field]: value } : player,
      ),
    );
  };

  const clearGameState = () => {
    setSnapshots([]);
    setRoundLog([]);
    setErrors([]);
    setCurrentRound(0);
    setCurrentPainting(null);
    setWinners([]);
    setMessage("");
  };

  const handleEvent = (event: GameEvent) => {
    if (event.type === "game_started") {
      setSnapshots(event.players);
      setStatus("running");
      setMessage("");
      return;
    }

    if (event.type === "round_finished") {
      setSnapshots(event.players);
      setCurrentRound(event.round);
      setCurrentPainting(event.painting);
      setRoundLog((current) => [event, ...current].slice(0, 80));
      return;
    }

    if (event.type === "bot_error") {
      setErrors((current) => [event, ...current].slice(0, 20));
      return;
    }

    if (event.type === "game_finished") {
      setSnapshots(event.players);
      setWinners(event.winners);
      setStatus("complete");
      sourceRef.current?.close();
      sourceRef.current = null;
      return;
    }

    if (event.type === "game_cancelled") {
      setSnapshots(event.players);
      setStatus("idle");
      sourceRef.current?.close();
      sourceRef.current = null;
    }
  };

  const runGame = async () => {
    sourceRef.current?.close();
    clearGameState();
    setStatus("running");

    try {
      const payload = await apiJson<{ gameId: string }>("/api/games", {
        method: "POST",
        body: JSON.stringify({
          players,
          roundLimit,
          seed: seed.trim() === "" ? null : Number(seed),
          tickMs,
        }),
      });

      setGameId(payload.gameId);
      const source = new EventSource(`${API_BASE_URL}/api/games/${payload.gameId}/events`);
      sourceRef.current = source;
      source.onmessage = (messageEvent) => {
        handleEvent(JSON.parse(messageEvent.data) as GameEvent);
      };
      source.onerror = () => {
        if (sourceRef.current) {
          setStatus("error");
          setMessage("The event stream closed unexpectedly.");
          source.close();
          sourceRef.current = null;
        }
      };
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Could not start the game.");
    }
  };

  const resetGame = async () => {
    sourceRef.current?.close();
    sourceRef.current = null;
    if (gameId) {
      await apiJson(`/api/games/${gameId}/reset`, {
        method: "POST",
        body: JSON.stringify({}),
      }).catch(() => undefined);
    }
    setGameId(null);
    setStatus("idle");
    clearGameState();
  };

  return (
    <main className="min-h-screen px-4 py-5 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-5">
        <header className="flex flex-col gap-3 border-b border-line pb-4 dark:border-zinc-800 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal">Dynamic Auction Arena</h1>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              Configure Python bots, run the painting auction, and watch each round resolve.
            </p>
          </div>
          <label className="flex items-center gap-2 text-sm">
            {theme === "dark" ? <Moon size={18} /> : <Sun size={18} />}
            <span className="sr-only">Theme</span>
            <select
              value={theme}
              onChange={(event) => setTheme(event.target.value as ThemeMode)}
              className="h-10 rounded-md border border-line bg-white px-3 dark:border-zinc-700 dark:bg-zinc-900"
            >
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </label>
        </header>

        <section className="rounded-md border border-line bg-white p-4 shadow-panel dark:border-zinc-800 dark:bg-zinc-900">
          <div className="mb-4 flex items-center gap-2">
            <SlidersHorizontal size={19} />
            <h2 className="text-base font-semibold">Game Setup</h2>
          </div>

          <div className="grid gap-3 md:grid-cols-5">
            <label className="flex flex-col gap-1 text-sm">
              Players
              <input
                type="number"
                min={2}
                value={players.length}
                onChange={(event) => updatePlayerCount(Number(event.target.value))}
                className="h-10 rounded-md border border-line bg-white px-3 dark:border-zinc-700 dark:bg-zinc-950"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Rounds
              <input
                type="number"
                min={1}
                value={roundLimit}
                onChange={(event) => setRoundLimit(Math.max(1, Number(event.target.value)))}
                className="h-10 rounded-md border border-line bg-white px-3 dark:border-zinc-700 dark:bg-zinc-950"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Seed
              <input
                type="number"
                value={seed}
                placeholder="Optional"
                onChange={(event) => setSeed(event.target.value)}
                className="h-10 rounded-md border border-line bg-white px-3 dark:border-zinc-700 dark:bg-zinc-950"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm md:col-span-2">
              Round Delay: {tickMs}ms
              <input
                type="range"
                min={0}
                max={1000}
                step={50}
                value={tickMs}
                onChange={(event) => setTickMs(Number(event.target.value))}
                className="h-10"
              />
            </label>
          </div>

          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full border-separate border-spacing-0 text-sm">
              <thead>
                <tr className="text-left text-zinc-500 dark:text-zinc-400">
                  <th className="border-b border-line py-2 pr-3 dark:border-zinc-800">Player</th>
                  <th className="border-b border-line px-3 py-2 dark:border-zinc-800">Bot</th>
                  <th className="border-b border-line px-3 py-2 dark:border-zinc-800">Budget</th>
                </tr>
              </thead>
              <tbody>
                {players.map((player, index) => (
                  <tr key={index}>
                    <td className="py-2 pr-3">
                      <input
                        value={player.playerName}
                        onChange={(event) => updatePlayer(index, "playerName", event)}
                        className="h-10 w-full min-w-36 rounded-md border border-line bg-white px-3 dark:border-zinc-700 dark:bg-zinc-950"
                      />
                    </td>
                    <td className="px-3 py-2">
                      <select
                        value={player.botModule}
                        onChange={(event) => updatePlayer(index, "botModule", event)}
                        className="h-10 w-full min-w-48 rounded-md border border-line bg-white px-3 dark:border-zinc-700 dark:bg-zinc-950"
                      >
                        {bots.map((bot) => (
                          <option key={bot.module} value={bot.module}>
                            {bot.displayName}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2">
                      <input
                        type="number"
                        min={1}
                        value={player.startingBudget}
                        onChange={(event) => updatePlayer(index, "startingBudget", event)}
                        className="h-10 w-full min-w-28 rounded-md border border-line bg-white px-3 dark:border-zinc-700 dark:bg-zinc-950"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={runGame}
              disabled={status === "running" || bots.length === 0}
              className="inline-flex h-10 items-center gap-2 rounded-md bg-accent px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Play size={17} />
              Run Game
            </button>
            <button
              type="button"
              onClick={resetGame}
              className="inline-flex h-10 items-center gap-2 rounded-md border border-line px-4 text-sm font-medium dark:border-zinc-700"
            >
              <RefreshCcw size={17} />
              Reset Game
            </button>
            <span className="text-sm text-zinc-600 dark:text-zinc-400">
              Status: <strong className="capitalize">{status}</strong>
              {message ? ` - ${message}` : ""}
            </span>
          </div>
        </section>

        <section className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="rounded-md border border-line bg-white p-4 shadow-panel dark:border-zinc-800 dark:bg-zinc-900">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold">Live Arena</h2>
                <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                  Round {currentRound || 0} / {roundLimit}
                  {currentPainting ? ` - ${currentPainting}` : ""}
                </p>
              </div>
              {latestRound ? (
                <div className="rounded-md bg-zinc-100 px-3 py-2 text-sm dark:bg-zinc-800">
                  Latest winner:{" "}
                  <strong>{formatPlayerName(latestRound.players, latestRound.winnerId)}</strong>{" "}
                  paid {latestRound.amountPaid}
                </div>
              ) : null}
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full border-separate border-spacing-0 text-sm">
                <thead>
                  <tr className="text-left text-zinc-500 dark:text-zinc-400">
                    <th className="border-b border-line py-2 pr-3 dark:border-zinc-800">Player</th>
                    <th className="border-b border-line px-3 py-2 dark:border-zinc-800">Bot</th>
                    <th className="border-b border-line px-3 py-2 dark:border-zinc-800">Bid</th>
                    <th className="border-b border-line px-3 py-2 dark:border-zinc-800">Budget</th>
                    <th className="border-b border-line px-3 py-2 dark:border-zinc-800">Score</th>
                    {ARTISTS.map((artist) => (
                      <th
                        key={artist}
                        className="border-b border-line px-3 py-2 dark:border-zinc-800"
                      >
                        {artist}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(snapshots.length > 0 ? snapshots : []).map((player) => (
                    <tr key={player.id}>
                      <td className="border-b border-line py-3 pr-3 dark:border-zinc-800">
                        <div className="font-medium">{player.playerName}</div>
                        <div className="text-xs text-zinc-500">{player.id}</div>
                      </td>
                      <td className="border-b border-line px-3 py-3 dark:border-zinc-800">
                        {player.botName}
                      </td>
                      <td className="border-b border-line px-3 py-3 dark:border-zinc-800">
                        {player.currentBid}
                      </td>
                      <td className="border-b border-line px-3 py-3 dark:border-zinc-800">
                        {player.budget}
                      </td>
                      <td className="border-b border-line px-3 py-3 font-semibold dark:border-zinc-800">
                        {player.score}
                      </td>
                      {ARTISTS.map((artist) => (
                        <td
                          key={artist}
                          className="border-b border-line px-3 py-3 dark:border-zinc-800"
                        >
                          {player.paintings[artist]}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {snapshots.length === 0 ? (
                <div className="py-12 text-center text-sm text-zinc-500">
                  Configure players and run a game to see the arena table.
                </div>
              ) : null}
            </div>

            {status === "complete" ? (
              <div className="mt-4 rounded-md border border-accent/40 bg-accent/10 p-4">
                <div className="flex items-center gap-2 font-semibold">
                  <Trophy size={19} />
                  Winner
                </div>
                <p className="mt-2 text-sm">{winnerText}</p>
              </div>
            ) : null}
          </div>

          <aside className="rounded-md border border-line bg-white p-4 shadow-panel dark:border-zinc-800 dark:bg-zinc-900">
            <h2 className="text-base font-semibold">Round Results</h2>
            <div className="mt-3 max-h-[540px] space-y-3 overflow-y-auto pr-1">
              {roundLog.map((round) => (
                <div
                  key={round.round}
                  className="rounded-md border border-line p-3 text-sm dark:border-zinc-800"
                >
                  <div className="flex items-center justify-between gap-3">
                    <strong>Round {round.round}</strong>
                    <span>{round.painting}</span>
                  </div>
                  <div className="mt-1 text-zinc-600 dark:text-zinc-400">
                    {formatPlayerName(round.players, round.winnerId)} paid{" "}
                    {round.amountPaid}
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-1 text-xs text-zinc-500">
                    {Object.entries(round.bids).map(([id, bid]) => (
                      <span key={id}>
                        {formatPlayerName(round.players, id)}: {bid}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
              {roundLog.length === 0 ? (
                <p className="text-sm text-zinc-500">Round results will appear here.</p>
              ) : null}
            </div>

            {errors.length > 0 ? (
              <div className="mt-4 border-t border-line pt-4 dark:border-zinc-800">
                <h3 className="text-sm font-semibold text-ember">Bot Issues</h3>
                <div className="mt-2 space-y-2">
                  {errors.map((error, index) => (
                    <div key={`${error.round}-${error.playerId}-${index}`} className="text-xs">
                      Round {error.round}: {error.playerId} - {error.message}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </aside>
        </section>
      </div>
    </main>
  );
}

