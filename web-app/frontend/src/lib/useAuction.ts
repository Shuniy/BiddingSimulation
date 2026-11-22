"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL, ApiError, apiJson } from "./api";
import { decodeEvent, isGameConfig, isGameStatus } from "./events";
import type { GameConfig, GameEvent } from "./types";

type Status = "idle" | "starting" | "connecting" | "running" | "reconnecting"
  | "cancelling" | "completed" | "cancelled" | "failed" | "error";

type Session = {
  gameId: string;
  cursor: number;
  source: EventSource | null;
  terminal: boolean;
  configuration?: GameConfig;
};

const isCreated = (value: unknown): value is { gameId: string; configuration: GameConfig } =>
  typeof value === "object" && value !== null && "gameId" in value
  && typeof value.gameId === "string" && "configuration" in value && isGameConfig(value.configuration);

function setGameInUrl(gameId?: string) {
  const url = new URL(window.location.href);
  if (gameId) url.searchParams.set("game", gameId);
  else url.searchParams.delete("game");
  window.history.replaceState(window.history.state, "", url);
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong.";
}

export function useAuction() {
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState("");
  const [events, setEvents] = useState<GameEvent[]>([]);
  const [gameId, setGameId] = useState<string>();
  const [configuration, setConfiguration] = useState<GameConfig>();
  const session = useRef<Session | null>(null);
  const generation = useRef(0);
  const pending = useRef(false);
  const cancelling = useRef(false);

  const connect = useCallback((active: Session) => {
    active.source?.close();
    const path = `/api/games/${encodeURIComponent(active.gameId)}`;
    const source = new EventSource(`${API_BASE_URL}${path}/events?after=${active.cursor}`);
    active.source = source;
    const isCurrent = () => session.current === active && active.source === source && !active.terminal;

    source.onopen = () => {
      if (!isCurrent() || cancelling.current) return;
      setStatus("running");
      setMessage("");
    };
    source.onmessage = ({ data, lastEventId }: MessageEvent<string>) => {
      if (!isCurrent()) return;
      try {
        const id = Number(lastEventId);
        if (Number.isSafeInteger(id) && id > 0 && id <= active.cursor) return;
        if (id !== active.cursor + 1) throw new Error("Missing auction event.");
        const event = decodeEvent(data);
        active.cursor = id;
        setEvents((previous) => [...previous, event]);
        if (event.type === "game_started") {
          active.configuration = event.configuration;
          setConfiguration(event.configuration);
        }
        if (
          event.type === "game_finished" || event.type === "game_cancelled" || event.type === "game_failed"
        ) {
          active.terminal = true;
          source.close();
          setStatus(event.type === "game_finished" ? "completed"
            : event.type === "game_cancelled" ? "cancelled" : "failed");
          setMessage(event.type === "game_failed" ? event.message : "");
          if (!active.configuration) {
            void apiJson(path, {}, isGameStatus).then((record) => {
              if (session.current === active) setConfiguration(record.configuration);
            }).catch(() => undefined);
          }
        }
      } catch {
        source.close();
        setStatus("error");
        setMessage("An auction update was unreadable. Reconnect to retry from the last update.");
      }
    };
    source.onerror = () => {
      if (!isCurrent()) return;
      if (source.readyState === EventSource.CONNECTING) {
        if (!cancelling.current) setStatus("reconnecting");
        setMessage("Connection interrupted. Waiting for the next update.");
        return;
      }
      setStatus("error");
      setMessage("The stream could not connect. Try reconnecting.");
      void apiJson(path, {}, isGameStatus).catch((error: unknown) => {
        if (!isCurrent()) return;
        if (error instanceof ApiError && (error.status === 404 || error.status === 410)) {
          active.terminal = true;
          setMessage(error.message);
        }
      });
    };
  }, []);

  const open = useCallback((id: string, config?: GameConfig) => {
    const active: Session = { gameId: id, cursor: 0, source: null, terminal: false, configuration: config };
    session.current?.source?.close();
    session.current = active;
    setEvents([]);
    setGameId(id);
    setConfiguration(config);
    setStatus("connecting");
    setMessage("");
    connect(active);
  }, [connect]);

  useEffect(() => {
    const previous = new URLSearchParams(window.location.search).get("game");
    if (previous) open(previous);
    return () => {
      generation.current += 1;
      pending.current = false;
      cancelling.current = false;
      session.current?.source?.close();
      session.current = null;
    };
  }, [open]);

  async function start(config: Omit<GameConfig, "seed"> & { seed: string }) {
    if (pending.current || cancelling.current) return;
    pending.current = true;
    const request = ++generation.current;
    session.current?.source?.close();
    session.current = null;
    setStatus("starting");
    setMessage("");
    setGameId(undefined);
    setConfiguration(undefined);
    setEvents([]);
    setGameInUrl();
    try {
      const result = await apiJson("/api/games", { method: "POST", body: config }, isCreated);
      if (request !== generation.current) {
        void apiJson(`/api/games/${encodeURIComponent(result.gameId)}/reset`, { method: "POST", keepalive: true })
          .catch(() => undefined);
        return;
      }
      setGameInUrl(result.gameId);
      open(result.gameId, result.configuration);
    } catch (error) {
      if (request === generation.current) {
        setStatus("error");
        setMessage(errorText(error));
      }
    } finally {
      if (request === generation.current) pending.current = false;
    }
  }

  async function cancel() {
    const active = session.current;
    if (!active || active.terminal || cancelling.current) return;
    cancelling.current = true;
    setStatus("cancelling");
    setMessage("");
    try {
      await apiJson(`/api/games/${encodeURIComponent(active.gameId)}/reset`, { method: "POST" });
      if (session.current === active && !active.terminal && active.source?.readyState === EventSource.CLOSED) {
        connect(active);
      }
    } catch (error) {
      if (session.current === active && !active.terminal) {
        setStatus("error");
        setMessage(errorText(error));
      }
    } finally {
      if (session.current === active) cancelling.current = false;
    }
  }

  function reconnect() {
    const active = session.current;
    if (!active || active.terminal || pending.current || cancelling.current) return;
    setStatus("connecting");
    setMessage("");
    connect(active);
  }

  function reset() {
    if (pending.current || cancelling.current) return;
    session.current?.source?.close();
    session.current = null;
    setStatus("idle");
    setMessage("");
    setGameId(undefined);
    setConfiguration(undefined);
    setEvents([]);
    setGameInUrl();
  }

  return {
    status, message, events, gameId, configuration, start, cancel, reconnect, reset,
    canReconnect: Boolean(session.current && !session.current.terminal),
  };
}
