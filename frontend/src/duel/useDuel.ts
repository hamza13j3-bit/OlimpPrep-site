import { useCallback, useEffect, useRef, useState } from "react";

import { duelState, getToken } from "../api/client";
import type { DuelState } from "../api/types";

/**
 * Live duel state. Primary channel: the WebSocket (server pushes every change). If it cannot be
 * opened or drops, the hook falls back to polling GET /duel/me every 2 s and keeps retrying.
 * The socket being open is what tells the server the player is present, so keep the duel page open.
 */
export function useDuel(enabled: boolean) {
  const [state, setState] = useState<DuelState | null>(null);
  const [live, setLive] = useState(false);
  const [failed, setFailed] = useState(false);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const s = await duelState();
      if (alive.current) {
        setState(s);
        setFailed(false);
      }
    } catch {
      if (alive.current) setFailed(true);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    if (!enabled) return;
    let ws: WebSocket | null = null;
    let poll: ReturnType<typeof setInterval> | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let ping: ReturnType<typeof setInterval> | null = null;

    const stopPolling = () => {
      if (poll) clearInterval(poll);
      poll = null;
    };
    const startPolling = () => {
      if (!poll) poll = setInterval(() => void refresh(), 2000);
    };

    function connect() {
      const token = getToken();
      if (!token || !alive.current) return;
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      const socket = new WebSocket(`${scheme}://${window.location.host}/api/duel/ws`);
      ws = socket;
      socket.onopen = () => socket.send(JSON.stringify({ type: "auth", token }));
      socket.onmessage = (ev: MessageEvent<string>) => {
        let msg: { type?: string } & Partial<DuelState>;
        try {
          msg = JSON.parse(ev.data) as typeof msg;
        } catch {
          return;
        }
        if (msg.type === "auth_ok") {
          setLive(true);
          stopPolling();
        } else if (msg.type === "state") {
          const { type: _type, ...rest } = msg;
          void _type;
          if (alive.current) setState(rest as DuelState);
        }
      };
      socket.onclose = () => {
        setLive(false);
        if (!alive.current) return;
        startPolling();
        retry = setTimeout(connect, 3000);
      };
      socket.onerror = () => socket.close();
    }

    void refresh();
    startPolling();
    connect();
    ping = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "ping" }));
    }, 20000);

    return () => {
      alive.current = false;
      stopPolling();
      if (retry) clearTimeout(retry);
      if (ping) clearInterval(ping);
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
    };
  }, [enabled, refresh]);

  return { state, setState, refresh, live, failed };
}
