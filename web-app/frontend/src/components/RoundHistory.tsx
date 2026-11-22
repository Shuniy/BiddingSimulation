import { useEffect, useState } from "react";
import type { BotErrorEvent, RoundFinishedEvent } from "@/lib/types";
import { playerName } from "./AuctionArena";

const PAGE_SIZE = 8;

export function RoundHistory({ rounds, selected, onSelect, completed }: {
  rounds: RoundFinishedEvent[];
  selected: number | null;
  onSelect: (round: number | null) => void;
  completed: boolean;
}) {
  const [page, setPage] = useState(0);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing || selected === null || selected >= rounds.length) return;
    const timer = window.setTimeout(() => {
      onSelect(selected + 1);
      if (selected + 1 >= rounds.length) setPlaying(false);
    }, 220);
    return () => window.clearTimeout(timer);
  }, [playing, selected, rounds.length, onSelect]);

  const pageCount = Math.ceil(rounds.length / PAGE_SIZE);
  const visiblePage = Math.min(page, Math.max(0, pageCount - 1));
  const end = rounds.length - visiblePage * PAGE_SIZE;
  const visible = rounds.slice(Math.max(0, end - PAGE_SIZE), end).reverse();

  return (
    <section className="panel" aria-labelledby="history-title">
      <h2 id="history-title" className="font-semibold">Round history</h2>
      {rounds.length ? <>
        <div className="mt-3 flex flex-wrap gap-2">
          {completed && <button className="action" onClick={() => {
            if (playing) setPlaying(false);
            else {
              if (selected === null || selected >= rounds.length) onSelect(1);
              setPlaying(true);
            }
          }}>{playing ? "Pause replay" : "Play replay"}</button>}
          <button className="action" disabled={selected === null} onClick={() => { setPlaying(false); onSelect(null); }}>
            Latest round
          </button>
          <label className="flex grow items-center gap-2 text-sm">
            Replay round
            <input className="min-w-20 grow accent-accent" type="range" min={1} max={rounds.length}
              value={selected ?? rounds.length} onChange={(event) => { setPlaying(false); onSelect(Number(event.target.value)); }} />
          </label>
        </div>
        <div className="mt-3 overflow-x-auto" tabIndex={0} role="region" aria-label="Round results">
          <table className="data-table">
            <thead><tr><th scope="col">Round</th><th scope="col">Artist</th><th scope="col">Winner</th><th scope="col">Paid</th></tr></thead>
            <tbody>{visible.map((round) => <tr key={round.round}>
              <td><button className="underline decoration-accent underline-offset-4" aria-pressed={selected === round.round}
                onClick={() => { setPlaying(false); onSelect(round.round); }}>Round {round.round}</button></td>
              <td>{round.painting}</td><td>{playerName(round.players, round.winnerId)}</td>
              <td>{round.amountPaid.toLocaleString()}</td>
            </tr>)}</tbody>
          </table>
        </div>
        {pageCount > 1 && <div className="mt-3 flex flex-wrap items-center gap-2">
          <button className="action" disabled={visiblePage === 0} onClick={() => setPage(visiblePage - 1)}>Newer</button>
          <span className="muted">Page {visiblePage + 1} of {pageCount}</span>
          <button className="action" disabled={visiblePage + 1 === pageCount} onClick={() => setPage(visiblePage + 1)}>Older</button>
        </div>}
      </> : <p className="muted mt-3">Round results appear as paintings are awarded.</p>}
    </section>
  );
}

export function BotErrorPanel({ errors }: { errors: BotErrorEvent[] }) {
  if (!errors.length) return null;
  return (
    <details className="panel">
      <summary className="cursor-pointer font-semibold">Bot issues ({errors.length})</summary>
      <ul className="mt-3 max-h-64 space-y-2 overflow-y-auto text-sm">
        {errors.slice(-50).reverse().map((error, index) => (
          <li key={`${error.round}-${error.playerId}-${index}`}>
            Round {error.round} · {error.playerId} · {error.message}
          </li>
        ))}
      </ul>
      {errors.length > 50 && <p className="muted mt-3">Showing the latest 50. The JSON export includes every issue.</p>}
    </details>
  );
}
