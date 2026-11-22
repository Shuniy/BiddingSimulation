"use client";

import { useMemo, useState } from "react";
import { AuctionArena } from "@/components/AuctionArena";
import { AuctionCharts } from "@/components/AuctionCharts";
import { GameResults } from "@/components/GameResults";
import { GameSetup } from "@/components/GameSetup";
import { BotErrorPanel, RoundHistory } from "@/components/RoundHistory";
import { ThemeSelector } from "@/components/ThemeSelector";
import { useAuction } from "@/lib/useAuction";

export default function Home() {
  const auction = useAuction();
  const [selectedRound, setSelectedRound] = useState<number | null>(null);
  const { status, events, configuration, gameId } = auction;
  const busy = ["starting", "connecting", "running", "reconnecting", "cancelling"].includes(status);
  const rounds = useMemo(() => events.filter((event) => event.type === "round_finished"), [events]);
  const issues = useMemo(() => events.filter((event) => event.type === "bot_error"), [events]);
  const lastEvent = events.at(-1);
  const round = selectedRound === null ? rounds.at(-1) : rounds[selectedRound - 1];
  const players = selectedRound !== null && round ? round.players
    : lastEvent && "players" in lastEvent ? lastEvent.players
      : round?.players ?? (events[0] && "players" in events[0] ? events[0].players : []);
  const terminal = status === "completed" || status === "cancelled" || status === "failed";

  return (
    <main className="mx-auto grid max-w-7xl gap-5 px-4 py-7 md:px-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="muted">BiddingSimulation</p>
          <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">Auction arena</h1>
        </div>
        <ThemeSelector />
      </header>

      <GameSetup disabled={busy || auction.canReconnect} onStart={(draft) => {
        setSelectedRound(null);
        void auction.start(draft);
      }} />

      {status !== "idle" && <section className="panel flex flex-wrap items-center justify-between gap-3" aria-label="Game controls">
        <div>
          <p role="status" className="text-sm font-semibold capitalize">{status}</p>
          {configuration && <p className="muted">{configuration.mode === "reference" ? "Coursework reference" : "Custom simulation"} · Seed {configuration.seed}</p>}
          {auction.message && <p role={status === "error" || status === "failed" ? "alert" : undefined}
            className="muted mt-1">{auction.message}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          {auction.canReconnect && status !== "starting" && <button className="action" disabled={status === "cancelling"}
            onClick={() => void auction.cancel()}>Cancel game</button>}
          {auction.canReconnect && (status === "error" || status === "reconnecting") &&
            <button className="action" onClick={auction.reconnect}>Reconnect</button>}
          {!busy && <button className="action" onClick={() => { setSelectedRound(null); auction.reset(); }}>Reset view</button>}
        </div>
      </section>}

      <AuctionArena round={round} players={players} roundLimit={configuration?.roundLimit} />
      {gameId && terminal && <GameResults gameId={gameId} rounds={rounds} events={events}
        configuration={configuration} result={lastEvent?.type === "game_finished" ? lastEvent : undefined} />}
      <div className="grid items-start gap-5 lg:grid-cols-2">
        <RoundHistory key={gameId} rounds={rounds} selected={selectedRound} onSelect={setSelectedRound} completed={status === "completed"} />
        <AuctionCharts rounds={rounds} />
      </div>
      <BotErrorPanel errors={issues} />
    </main>
  );
}
