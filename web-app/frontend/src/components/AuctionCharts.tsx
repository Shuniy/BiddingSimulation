import { useEffect, useRef, useState } from "react";
import { ARTISTS, type RoundFinishedEvent } from "@/lib/types";

const METRICS = {
  budget: "Remaining budget",
  score: "Score progression",
  price: "Winning bids",
} as const;

type Metric = keyof typeof METRICS;

const PALETTE = ["#258c73", "#356ab3", "#a35f1c", "#9f5193", "#b9494d", "#527835", "#6570b6", "#a25c6e"];

function color(seat: number) {
  return PALETTE[seat % PALETTE.length];
}

export function AuctionCharts({ rounds }: { rounds: RoundFinishedEvent[] }) {
  const [metric, setMetric] = useState<Metric>("budget");
  const [seat, setSeat] = useState(0);
  const [compare, setCompare] = useState(false);
  const canvas = useRef<HTMLCanvasElement>(null);
  const last = rounds.at(-1);
  const validSeat = Math.min(seat, Math.max(0, (last?.players.length ?? 1) - 1));
  const player = last?.players[validSeat];

  useEffect(() => {
    if (!rounds.length || !canvas.current) return;
    const { width, height } = canvas.current;
    const ctx = canvas.current.getContext("2d");
    if (!ctx) return;
    const seats = compare && metric !== "price" ? rounds[0].players.map((_, index) => index) : [validSeat];
    const series = seats.map((index) =>
      rounds.map((round) => metric === "price" ? round.amountPaid : round.players[index][metric]));
    const values = series.flat();
    const max = Math.max(1, ...values);
    const min = Math.min(0, ...values);
    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = "#7c8985";
    ctx.fillStyle = "#7c8985";
    ctx.font = "13px sans-serif";
    for (let i = 0; i <= 4; i += 1) {
      const y = 14 + i * (height - 35) / 4;
      ctx.fillText(Math.round(max - i * (max - min) / 4).toLocaleString(), 0, y + 4);
      ctx.beginPath();
      ctx.moveTo(78, y);
      ctx.lineTo(width - 12, y);
      ctx.stroke();
    }
    ctx.fillText("1", 78, height - 2);
    ctx.fillText(String(rounds.length), width - 32, height - 2);
    for (const [line, points] of series.entries()) {
      ctx.strokeStyle = metric === "price" ? PALETTE[0] : color(seats[line]);
      ctx.setLineDash(seats[line] >= PALETTE.length ? [5, 4] : []);
      ctx.lineWidth = 2;
      ctx.beginPath();
      for (const [index, value] of points.entries()) {
        const x = 78 + index * (width - 90) / Math.max(1, points.length - 1);
        const y = 14 + (max - value) / (max - min) * (height - 35);
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
        if (points.length === 1) ctx.lineTo(x + 3, y);
      }
      ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.lineWidth = 1;
  }, [rounds, metric, validSeat, compare]);

  if (!last) return null;
  return (
    <section className="panel" aria-labelledby="charts-title">
      <h2 id="charts-title" className="font-semibold">Auction trends</h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="text-sm">Measure
          <select className="field mt-1" value={metric} onChange={(event) => setMetric(event.target.value as Metric)}>
            {Object.entries(METRICS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="text-sm">Chart player
          <select className="field mt-1" disabled={metric === "price" || compare} value={validSeat}
            onChange={(event) => setSeat(Number(event.target.value))}>
            {last.players.map((entry, index) => <option key={entry.id} value={index}>{entry.playerName} · {entry.botName}</option>)}
          </select>
        </label>
      </div>
      {metric !== "price" && <label className="mt-3 inline-flex items-center gap-2 text-sm">
        <input type="checkbox" checked={compare} onChange={(event) => setCompare(event.target.checked)}
          className="accent-accent" /> Compare all players
      </label>}
      {compare && metric !== "price" && <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {last.players.map((entry, index) => <li key={entry.id} className="flex items-center gap-1">
          <span className="inline-block w-3 border-t-2" aria-hidden
            style={{ borderColor: color(index), borderTopStyle: index < PALETTE.length ? "solid" : "dashed" }} />
          {entry.playerName} · {entry.botName}
        </li>)}
      </ul>}
      <canvas ref={canvas} width={700} height={210} className="mt-4 w-full"
        role="img" aria-label={`${METRICS[metric]} across ${rounds.length} rounds`} />
      {(!compare || metric === "price") && <p className="muted mt-1">Round {last.round} · {METRICS[metric]} {metric === "price"
        ? last.amountPaid.toLocaleString() : player?.[metric].toLocaleString()}</p>}
      <h3 className="mb-2 mt-5 text-sm font-semibold">Paintings acquired by player</h3>
      <ul className="grid gap-2 text-sm">
        {last.players.map((entry) => {
          const count = ARTISTS.reduce((sum, artist) => sum + entry.paintings[artist], 0);
          return <li key={entry.id} className="grid grid-cols-[minmax(6rem,1fr)_2fr_2rem] items-center gap-2">
            <span className="truncate" title={entry.playerName}>{entry.playerName}</span>
            <meter className="h-3 w-full accent-accent" aria-label={`${entry.playerName} paintings`}
              min={0} max={last.round} value={count} />
            <span className="text-right tabular-nums">{count}</span>
          </li>;
        })}
      </ul>
    </section>
  );
}
