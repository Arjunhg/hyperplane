import { useCallback, useEffect, useMemo, useState } from "react";

import type { AircraftState, PositionFix, WsMessage } from "../types/aircraft";

const STALE_AFTER_MS = Number(import.meta.env.VITE_AIRCRAFT_STALE_MS ?? "30000");
const STALE_SCAN_INTERVAL_MS = 5000;

function toAircraftState(fix: PositionFix, now: number): AircraftState {
  return {
    ...fix,
    lastUpdated: now,
    isStale: false,
  };
}

function isRemovePayload(data: WsMessage["data"]): data is { icao: string } {
  return typeof data === "object" && data !== null && "icao" in data;
}

function isPositionFix(data: WsMessage["data"]): data is PositionFix {
  return (
    typeof data === "object" &&
    data !== null &&
    "icao" in data &&
    "lat" in data &&
    "lon" in data &&
    "alt_ft" in data &&
    "method" in data
  );
}

export function useAircraftStore(): {
  aircraft: AircraftState[];
  dispatchWsMessage: (msg: WsMessage) => void;
} {
  const [aircraftMap, setAircraftMap] = useState<Map<string, AircraftState>>(
    () => new Map(),
  );

  const dispatchWsMessage = useCallback((msg: WsMessage) => {
    if (msg.type === "snapshot") {
      if (!Array.isArray(msg.data)) {
        return;
      }

      const now = Date.now();
      const next = new Map<string, AircraftState>();
      for (const fix of msg.data) {
        next.set(fix.icao.toUpperCase(), toAircraftState(fix, now));
      }
      setAircraftMap(next);
      return;
    }

    if (msg.type === "fix") {
      if (Array.isArray(msg.data) || !isPositionFix(msg.data)) {
        return;
      }

      const fix = msg.data;
      const now = Date.now();
      const icao = fix.icao.toUpperCase();
      const updatedAircraft = toAircraftState(fix, now);

      setAircraftMap((prev) => {
        const next = new Map(prev);
        next.set(icao, updatedAircraft);
        return next;
      });
      return;
    }

    if (msg.type === "remove") {
      if (Array.isArray(msg.data) || !isRemovePayload(msg.data)) {
        return;
      }
      const icao = msg.data.icao.toUpperCase();

      setAircraftMap((prev) => {
        const next = new Map(prev);
        next.delete(icao);
        return next;
      });
    }
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const now = Date.now();
      setAircraftMap((prev) => {
        const next = new Map(prev);
        let changed = false;

        for (const [icao, state] of prev.entries()) {
          const shouldBeStale = now - state.lastUpdated > STALE_AFTER_MS;
          if (state.isStale !== shouldBeStale) {
            next.set(icao, { ...state, isStale: shouldBeStale });
            changed = true;
          }
        }

        return changed ? next : prev;
      });
    }, STALE_SCAN_INTERVAL_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, []);

  const aircraft = useMemo(
    () => Array.from(aircraftMap.values()),
    [aircraftMap],
  );

  return { aircraft, dispatchWsMessage };
}
