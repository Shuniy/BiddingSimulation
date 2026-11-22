import { ARTISTS, type RoundFinishedEvent, type PlayerSnapshot } from "./types";

export function roundCsv(rounds: RoundFinishedEvent[]) {
  const rows: (string | number)[][] = [[
    "round", "artist", "player_id", "player_name", "bot_module", "bid", "won_round",
    "amount_paid", "budget_remaining", "score", ...ARTISTS,
  ]];
  for (const round of rounds) {
    for (const player of round.players) {
      const won = player.id === round.winnerId;
      rows.push([
        round.round, round.painting, player.id, player.playerName, player.botModule,
        round.bids[player.id], Number(won), won ? round.amountPaid : 0, player.budget,
        player.score, ...ARTISTS.map((artist) => player.paintings[artist]),
      ]);
    }
  }
  return rows.map((row) => row.map((value) => {
    if (typeof value === "number") return String(value);
    // Prevent a player-supplied name from becoming a spreadsheet formula.
    const safe = /^[\s]*[=+\-@]/.test(value) ? `'${value}` : value;
    return `"${safe.replace(/"/g, '""')}"`;
  }).join(",")).join("\r\n") + "\r\n";
}

export function rankings(players: PlayerSnapshot[]) {
  const ordered = [...players].sort((a, b) => b.score - a.score);
  let rank = 1;
  return ordered.map((player, index) => {
    if (index && player.score !== ordered[index - 1].score) rank = index + 1;
    return { ...player, rank, paintingsAcquired: ARTISTS.reduce((sum, artist) => sum + player.paintings[artist], 0) };
  });
}

export function download(filename: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}
