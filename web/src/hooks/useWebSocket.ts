import { useEffect, useRef, useState } from "react";

import type { WsMessage } from "../types/aircraft";

export type WebSocketStatus = "connecting" | "connected" | "disconnected";

const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;

export function useWebSocket(
  url: string,
  onMessage: (msg: WsMessage) => void,
): { status: WebSocketStatus } {
  const [status, setStatus] = useState<WebSocketStatus>("connecting");

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const onMessageRef = useRef(onMessage);
  const shouldReconnectRef = useRef(true);
  const backoffMsRef = useRef(INITIAL_BACKOFF_MS);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    shouldReconnectRef.current = true;
    setStatus("connecting");

    const clearReconnectTimer = () => {
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };

    const scheduleReconnect = () => {
      if (!shouldReconnectRef.current) {
        return;
      }
      setStatus("connecting");

      const delay = backoffMsRef.current;
      backoffMsRef.current = Math.min(backoffMsRef.current * 2, MAX_BACKOFF_MS);

      clearReconnectTimer();
      reconnectTimerRef.current = window.setTimeout(connect, delay);
    };

    const connect = () => {
      if (!shouldReconnectRef.current) {
        return;
      }

      setStatus("connecting");
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        backoffMsRef.current = INITIAL_BACKOFF_MS;
        setStatus("connected");
      };

      ws.onmessage = (event: MessageEvent<string>) => {
        let parsed: unknown;
        try {
          parsed = JSON.parse(event.data);
        } catch (err) {
          console.warn("Discarding non-JSON WebSocket message", err);
          return;
        }

        onMessageRef.current(parsed as WsMessage);
      };

      ws.onerror = () => {
        ws.close();
      };

      ws.onclose = () => {
        wsRef.current = null;
        if (!shouldReconnectRef.current) {
          setStatus("disconnected");
          return;
        }
        scheduleReconnect();
      };
    };

    connect();

    return () => {
      shouldReconnectRef.current = false;
      clearReconnectTimer();
      setStatus("disconnected");

      if (wsRef.current !== null) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [url]);

  return { status };
}
