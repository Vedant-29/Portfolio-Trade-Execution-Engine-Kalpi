import { useCallback, useSyncExternalStore } from "react";

const STORAGE_KEY = "kalpi.sessions.v1";
const EVENT_NAME = "kalpi:sessions-changed";

export type SessionMap = Record<string, string>;

let cachedJson = "";
let cachedSnapshot: SessionMap = Object.freeze({}) as SessionMap;

function readFresh(): SessionMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY) ?? "";
    if (raw === cachedJson) return cachedSnapshot;
    const parsed = raw ? JSON.parse(raw) : {};
    const next: SessionMap =
      typeof parsed === "object" && parsed !== null ? parsed : {};
    cachedJson = raw;
    cachedSnapshot = Object.freeze(next) as SessionMap;
    return cachedSnapshot;
  } catch {
    cachedJson = "";
    cachedSnapshot = Object.freeze({}) as SessionMap;
    return cachedSnapshot;
  }
}

function write(next: SessionMap): void {
  const serialized = JSON.stringify(next);
  localStorage.setItem(STORAGE_KEY, serialized);

  cachedJson = serialized;
  cachedSnapshot = Object.freeze({ ...next }) as SessionMap;
  window.dispatchEvent(new Event(EVENT_NAME));
}

function subscribe(listener: () => void): () => void {
  const handler = () => listener();
  window.addEventListener(EVENT_NAME, handler);
  window.addEventListener("storage", handler);
  return () => {
    window.removeEventListener(EVENT_NAME, handler);
    window.removeEventListener("storage", handler);
  };
}

function getSnapshot(): SessionMap {
  return readFresh();
}

const EMPTY: SessionMap = Object.freeze({}) as SessionMap;

function getServerSnapshot(): SessionMap {
  return EMPTY;
}

export function useSessions() {
  const sessions = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerSnapshot,
  );

  const set = useCallback((broker: string, sessionId: string) => {
    const current = readFresh();
    if (current[broker] === sessionId) return;
    write({ ...current, [broker]: sessionId });
  }, []);

  const remove = useCallback((broker: string) => {
    const current = readFresh();
    if (!(broker in current)) return;
    const next = { ...current };
    delete next[broker];
    write(next);
  }, []);

  const clear = useCallback(() => {
    if (Object.keys(readFresh()).length === 0) return;
    write({});
  }, []);

  return { sessions, set, remove, clear };
}
