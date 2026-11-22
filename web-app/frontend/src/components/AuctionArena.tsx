import { ARTISTS, type PlayerSnapshot, type RoundFinishedEvent } from "@/lib/types";

export function playerName(players: PlayerSnapshot[], id: string) {
  return players.find((player) => player.id === id)?.playerName ?? id;
}

export function AuctionArena({ round, players, roundLimit }: {
  round?: RoundFinishedEvent;
  players: PlayerSnapshot[];
  roundLimit?: number;
}) {
  return (
    <section className="panel" aria-labelledby="arena-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="arena-title" className="font-semibold">Auction arena</h2>
          {roundLimit && <p className="muted mt-1">Round {round?.round ?? 0} of {roundLimit}
            {round && ` · ${round.painting}`}</p>}
        </div>
        {round && <p className="rounded-md bg-teal-50 px-3 py-2 text-sm text-teal-950 dark:bg-teal-950 dark:text-teal-100">
          <strong>{playerName(players, round.winnerId)}</strong> won for {round.amountPaid.toLocaleString()} credits
        </p>}
      </div>
      {players.length > 0 ? (
        <div className="mt-4 overflow-x-auto" tabIndex={0} role="region" aria-label="Player scoreboard">
          <table className="data-table">
            <thead><tr>
              <th scope="col">Player</th><th scope="col">Bid</th><th scope="col">Budget</th><th scope="col">Score</th>
              {ARTISTS.map((artist) => <th scope="col" key={artist}>{artist}</th>)}
            </tr></thead>
            <tbody>
              {players.map((player) => <tr key={player.id} className={player.id === round?.winnerId ? "bg-teal-50/60 dark:bg-teal-950/40" : ""}>
                <td><div className="font-medium">{player.playerName}</div><div className="muted">{player.botName}</div></td>
                <td>{player.currentBid.toLocaleString()}</td>
                <td>{player.budget.toLocaleString()}</td>
                <td className="font-semibold">{player.score.toLocaleString()}</td>
                {ARTISTS.map((artist) => <td key={artist}>{player.paintings[artist]}</td>)}
              </tr>)}
            </tbody>
          </table>
        </div>
      ) : <p className="muted mt-3">Run a game to see bids, budgets, scores, and collections.</p>}
    </section>
  );
}
