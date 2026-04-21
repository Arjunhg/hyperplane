import { useEffect, useMemo, useState } from "react";

import { StatusDot } from "../shared/StatusDot";
import type { StatsPanelProps } from "./Sidebar.types";

interface HealthResponse {
  status: string;
  active_aircraft: number;
  fixes_per_minute: number;
}

export function StatsPanel({ aircraft, wsStatus }: StatsPanelProps) {
  const [fixesPerMinute, setFixesPerMinute] = useState<number>(0);

  const activeAircraftCount = useMemo(
    () => aircraft.filter((item) => !item.isStale).length,
    [aircraft],
  );

  useEffect(() => {
    let isMounted = true;

    const fetchHealth = async () => {
      try {
        const response = await fetch("/health");
        if (!response.ok) {
          return;
        }
        const payload = (await response.json()) as HealthResponse;
        if (isMounted) {
          setFixesPerMinute(payload.fixes_per_minute ?? 0);
        }
      } catch {
        if (isMounted) {
          setFixesPerMinute(0);
        }
      }
    };

    void fetchHealth();
    const timer = window.setInterval(() => {
      void fetchHealth();
    }, 10_000);

    return () => {
      isMounted = false;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <div className="grid grid-cols-3 gap-2">
      <div className="rounded-md border border-gray-700 bg-gray-800/80 p-3">
        <div className="text-xs text-gray-400">Active Aircraft</div>
        <div className="text-lg font-semibold text-white">{activeAircraftCount}</div>
      </div>
      <div className="rounded-md border border-gray-700 bg-gray-800/80 p-3">
        <div className="text-xs text-gray-400">Fixes / min</div>
        <div className="text-lg font-semibold text-white">{fixesPerMinute}</div>
      </div>
      <div className="rounded-md border border-gray-700 bg-gray-800/80 p-3">
        <div className="text-xs text-gray-400">Connection</div>
        <div className="pt-1">
          <StatusDot status={wsStatus} />
        </div>
      </div>
    </div>
  );
}
