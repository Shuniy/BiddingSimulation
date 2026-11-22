import { ARTISTS, type GameConfig, type GameEvent, type GameStatus, type PlayerConfig, type PlayerSnapshot } from "./types";

const object = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const text = (value: unknown): value is string => typeof value === "string";
const integer = (value: unknown): value is number => Number.isSafeInteger(value);
const artist = (value: unknown) => ARTISTS.some((candidate) => candidate === value);

function playerConfig(value: unknown): value is PlayerConfig {
  return object(value) && text(value.playerName) && text(value.botModule) && integer(value.startingBudget);
}

export function isGameConfig(value: unknown): value is GameConfig {
  return object(value) && (value.mode === "reference" || value.mode === "custom")
    && integer(value.roundLimit) && integer(value.seed) && integer(value.tickMs)
    && Array.isArray(value.players) && value.players.every(playerConfig);
}

export function isGameStatus(value: unknown): value is GameStatus {
  return object(value) && integer(value.schemaVersion) && text(value.gameId)
    && ["created", "running", "completed", "cancelled", "failed"].some((status) => status === value.status)
    && integer(value.lastEventId) && isGameConfig(value.configuration);
}

function snapshot(value: unknown): value is PlayerSnapshot {
  if (!object(value) || !playerConfig(value)) return false;
  const paintings = value.paintings;
  return text(value.id) && text(value.botName) && integer(value.budget)
    && integer(value.currentBid) && integer(value.score) && object(paintings)
    && ARTISTS.every((name) => integer(paintings[name]));
}

function isGameEvent(value: unknown): value is GameEvent {
  if (!object(value)) return false;
  if (value.type === "bot_error") {
    return integer(value.round) && text(value.playerId) && text(value.message)
      && (value.detail === undefined || text(value.detail));
  }
  if (!Array.isArray(value.players) || value.players.length < 2 || !value.players.every(snapshot)) return false;
  switch (value.type) {
    case "game_started":
      return text(value.gameId) && integer(value.roundLimit) && isGameConfig(value.configuration);
    case "round_finished": {
      const bids = value.bids;
      return integer(value.round) && value.round > 0 && artist(value.painting) && text(value.winnerId)
        && value.players.some((player) => player.id === value.winnerId)
        && integer(value.amountPaid) && object(bids) && value.players.every((player) => integer(bids[player.id]));
    }
    case "game_finished":
      return Array.isArray(value.winners) && value.winners.every(text);
    case "game_failed":
      return text(value.gameId) && text(value.message);
    case "game_cancelled":
      return text(value.gameId);
    default:
      return false;
  }
}

export function decodeEvent(data: string): GameEvent {
  const event: unknown = JSON.parse(data);
  if (!isGameEvent(event)) throw new Error("Unexpected auction event.");
  return event;
}
