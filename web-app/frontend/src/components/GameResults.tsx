import { Download, Trophy } from "lucide-react";
import { download, rankings, roundCsv } from "@/lib/exports";
import type { GameConfig, GameEvent, GameFinishedEvent, RoundFinishedEvent } from "@/lib/types";
import { playerName } from "./AuctionArena";

export function GameResults({ result, rounds, configuration, gameId, events }: {
  result?: GameFinishedEvent;
  rounds: RoundFinishedEvent[];
  configuration?: GameConfig;
  gameId: string;
  events: GameEvent[];
}) {
  const ordered = result ? rankings(result.players) : [];
  const summary = result && { gameId, configuration, winners: result.winners, rankings: ordered };
  const status = result ? "completed" : events.at(-1)?.type === "game_cancelled" ? "cancelled" : "failed";

  return (
    <section className="panel" aria-labelledby="results-title">
      <h2 id="results-title" className="flex items-center gap-2 font-semibold">
        <Trophy size={17} aria-hidden /> {result ? "Final results" : "Partial results"}
      </h2>
      {result && <>
        <p className="mt-2 text-sm">{result.winners.length
          ? `${result.winners.length > 1 ? "Shared winners" : "Winner"} · ${result.winners.map((id) => playerName(result.players, id)).join(", ")}`
          : "No winner. Every final score is zero."}</p>
        <div className="mt-3 overflow-x-auto" tabIndex={0} role="region" aria-label="Final rankings">
          <table className="data-table">
            <thead><tr>
              <th scope="col">Rank</th><th scope="col">Player</th><th scope="col">Strategy</th>
              <th scope="col">Score</th><th scope="col">Final budget</th><th scope="col">Paintings</th>
            </tr></thead>
            <tbody>{ordered.map((player) => <tr key={player.id}>
              <td>{player.rank}</td><td>{player.playerName}</td><td>{player.botName}</td>
              <td>{player.score.toLocaleString()}</td><td>{player.budget.toLocaleString()}</td><td>{player.paintingsAcquired}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </>}
      <div className="mt-4 flex flex-wrap gap-2">
        <button className="action" disabled={!rounds.length} onClick={() =>
          download(`auction-${gameId}-rounds.csv`, roundCsv(rounds), "text/csv;charset=utf-8")}>
          <Download size={15} aria-hidden /> Round CSV
        </button>
        <button className="action" onClick={() => download(`auction-${gameId}.json`, JSON.stringify({
          schemaVersion: 1, gameId, configuration, status, lastEventId: events.length, events,
        }, null, 2), "application/json")}>Game JSON</button>
        {summary && <button className="action" onClick={() => download(
          `auction-${gameId}-summary.json`, JSON.stringify(summary, null, 2), "application/json",
        )}>Summary JSON</button>}
      </div>
    </section>
  );
}
