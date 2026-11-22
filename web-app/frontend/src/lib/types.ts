export const ARTISTS = ["Da Vinci", "Picasso", "Rembrandt", "Van Gogh"] as const;
export type Artist = (typeof ARTISTS)[number];

export interface BotInfo {
  module: string;
  displayName: string;
}

export interface PlayerConfig {
  playerName: string;
  botModule: string;
  startingBudget: number;
}

export interface PlayerSnapshot extends PlayerConfig {
  id: string;
  botName: string;
  budget: number;
  currentBid: number;
  score: number;
  paintings: Record<Artist, number>;
}

export interface GameConfig {
  mode: "reference" | "custom";
  roundLimit: number;
  seed: number;
  tickMs: number;
  players: PlayerConfig[];
}

export interface GameStartedEvent {
  type: "game_started";
  gameId: string;
  roundLimit: number;
  configuration: GameConfig;
  players: PlayerSnapshot[];
}

export interface RoundFinishedEvent {
  type: "round_finished";
  round: number;
  painting: Artist;
  bids: Record<string, number>;
  winnerId: string;
  amountPaid: number;
  players: PlayerSnapshot[];
}

export interface BotErrorEvent {
  type: "bot_error";
  round: number;
  playerId: string;
  message: string;
  detail?: string;
}

export interface GameFinishedEvent {
  type: "game_finished";
  winners: string[];
  players: PlayerSnapshot[];
}

export interface GameCancelledEvent {
  type: "game_cancelled";
  gameId: string;
  players: PlayerSnapshot[];
}

export interface GameFailedEvent {
  type: "game_failed";
  gameId: string;
  message: string;
  players: PlayerSnapshot[];
}

export type GameEvent =
  | GameStartedEvent
  | RoundFinishedEvent
  | BotErrorEvent
  | GameFinishedEvent
  | GameCancelledEvent
  | GameFailedEvent;

export interface GameStatus {
  schemaVersion: number;
  gameId: string;
  status: "created" | "running" | "completed" | "cancelled" | "failed";
  configuration: GameConfig;
  lastEventId: number;
}

export interface ArenaLimits {
  maxPlayers: number;
  maxBudget: number;
  maxRounds: number;
  maxTickMs: number;
}
