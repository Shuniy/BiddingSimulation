import { Play } from "lucide-react";
import { useEffect, useState } from "react";
import { apiJson } from "@/lib/api";
import type { ArenaLimits, BotInfo, GameConfig, PlayerConfig } from "@/lib/types";

type Draft = Omit<GameConfig, "seed"> & { seed: string };
const defaultLimits: ArenaLimits = { maxPlayers: 16, maxRounds: 500, maxBudget: 100_000, maxTickMs: 1000 };
const makePlayer = (seat: number, bots: BotInfo[], budget = 1001): PlayerConfig => ({
  playerName: `Player ${seat + 1}`,
  botModule: bots[seat % bots.length]?.module ?? "",
  startingBudget: budget,
});

function isBotList(value: unknown): value is { bots: BotInfo[]; limits?: ArenaLimits } {
  if (typeof value !== "object" || value === null || !("bots" in value) || !Array.isArray(value.bots)) {
    return false;
  }
  const validBots = value.bots.every((bot: unknown) =>
    typeof bot === "object" && bot !== null && "module" in bot && typeof bot.module === "string"
    && "displayName" in bot && typeof bot.displayName === "string");
  if (!("limits" in value)) return validBots;
  const limits = value.limits;
  return validBots && typeof limits === "object" && limits !== null
    && ["maxPlayers", "maxRounds", "maxBudget", "maxTickMs"].every((key) =>
      Number.isSafeInteger(Reflect.get(limits, key)));
}

export function GameSetup({ disabled, onStart }: { disabled: boolean; onStart: (draft: Draft) => void }) {
  const [bots, setBots] = useState<BotInfo[]>([]);
  const [limits, setLimits] = useState(defaultLimits);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [retry, setRetry] = useState(0);
  const [players, setPlayers] = useState<PlayerConfig[]>([makePlayer(0, []), makePlayer(1, [])]);
  const [mode, setMode] = useState<Draft["mode"]>("reference");
  const [roundLimit, setRoundLimit] = useState(200);
  const [seed, setSeed] = useState("");
  const [tickMs, setTickMs] = useState(150);

  useEffect(() => {
    const controller = new AbortController();
    apiJson("/api/bots", { signal: controller.signal }, isBotList)
      .then((payload) => {
        if (controller.signal.aborted) return;
        setBots(payload.bots);
        const availableLimits = payload.limits ?? defaultLimits;
        setLimits(availableLimits);
        setTickMs((current) => Math.min(current, availableLimits.maxTickMs));
        if (availableLimits.maxBudget < 1001 || availableLimits.maxRounds < 200) {
          setMode("custom");
          setRoundLimit((current) => Math.min(current, availableLimits.maxRounds));
        }
        setPlayers((current) => current.map((player, seat) => ({
          ...player,
          startingBudget: Math.min(player.startingBudget, availableLimits.maxBudget),
          botModule: payload.bots.some((bot) => bot.module === player.botModule)
            ? player.botModule : makePlayer(seat, payload.bots).botModule,
        })));
        setMessage(payload.bots.length ? "" : "No strategies are available.");
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) setMessage(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [retry]);

  function updatePlayer(seat: number, patch: Partial<PlayerConfig>) {
    setPlayers((current) => current.map((player, index) => index === seat ? { ...player, ...patch } : player));
  }

  const reference = mode === "reference";
  const referenceAvailable = limits.maxBudget >= 1001 && limits.maxRounds >= 200;

  return (
    <section className="panel" aria-labelledby="setup-title">
      <h2 id="setup-title" className="font-semibold">Game setup</h2>
      <form className="mt-4" onSubmit={(event) => {
        event.preventDefault();
        onStart({
          mode, roundLimit: reference ? 200 : roundLimit, seed, tickMs,
          players: players.map((player) => ({ ...player, startingBudget: reference ? 1001 : player.startingBudget })),
        });
      }}>
        <fieldset disabled={disabled || loading || !bots.length} className="space-y-4 disabled:opacity-60">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="text-sm">Rules
              <select className="field mt-1" value={mode}
                onChange={(event) => setMode(event.target.value === "custom" ? "custom" : "reference")}>
                <option value="reference" disabled={!referenceAvailable}>Coursework reference</option>
                <option value="custom">Custom simulation</option>
              </select>
            </label>
            <label className="text-sm">Rounds
              <input className="field mt-1" type="number" min={1} max={limits.maxRounds} required
                disabled={reference} value={reference ? 200 : roundLimit || ""}
                onChange={(event) => setRoundLimit(Number(event.target.value))} />
            </label>
            <label className="text-sm">Seed
              <input className="field mt-1" inputMode="numeric" pattern="-?[0-9]+" placeholder="Optional"
                value={seed} onChange={(event) => setSeed(event.target.value)} />
            </label>
            <label className="text-sm">Round delay · {tickMs} ms
              <input className="mt-1 h-10 w-full accent-accent" type="range" min={0}
                max={limits.maxTickMs} step={1} value={tickMs}
                onChange={(event) => setTickMs(Number(event.target.value))} />
            </label>
          </div>
          <p className="muted">{reference
            ? "200 rounds and 1,001 starting credits per player."
            : "Set the round count and each player’s starting budget. Negative bids are rejected."}</p>
          <div className="grid gap-3">
            {players.map((player, seat) => (
              <div key={seat} className="grid grid-cols-2 gap-3 rounded-md border border-line p-3 dark:border-zinc-800 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_9rem_auto]">
                <label className="text-sm">Player {seat + 1} name
                  <input className="field mt-1" required pattern=".*\S.*" maxLength={60} value={player.playerName}
                    onChange={(event) => updatePlayer(seat, { playerName: event.target.value })} />
                </label>
                <label className="text-sm">Player {seat + 1} strategy
                  <select className="field mt-1" value={player.botModule} required
                    onChange={(event) => updatePlayer(seat, { botModule: event.target.value })}>
                    {bots.map((bot) => <option key={bot.module} value={bot.module}>{bot.displayName}</option>)}
                  </select>
                </label>
                <label className="text-sm">Player {seat + 1} budget
                  <input className="field mt-1" type="number" min={1} max={limits.maxBudget} required
                    disabled={reference} value={reference ? 1001 : player.startingBudget || ""}
                    onChange={(event) => updatePlayer(seat, { startingBudget: Number(event.target.value) })} />
                </label>
                <button type="button" className="action self-end" disabled={players.length <= 2}
                  aria-label={`Remove player ${seat + 1}`}
                  onClick={() => setPlayers((current) => current.filter((_, index) => index !== seat))}>
                  Remove
                </button>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="action" disabled={players.length >= limits.maxPlayers}
              onClick={() => setPlayers((current) => [...current, makePlayer(current.length, bots, Math.min(1001, limits.maxBudget))])}>
              Add player
            </button>
            <button type="submit" className="primary-action" disabled={reference && !referenceAvailable}>
              <Play size={16} aria-hidden /> Run game
            </button>
          </div>
        </fieldset>
      </form>
      {loading && <p role="status" className="muted mt-3">Loading strategies…</p>}
      {message && <div className="mt-3 flex items-center gap-3">
        <p role="alert" className="text-sm">{message}</p>
        <button className="action" onClick={() => { setLoading(true); setMessage(""); setRetry(retry + 1); }}>
          Retry strategies
        </button>
      </div>}
    </section>
  );
}
