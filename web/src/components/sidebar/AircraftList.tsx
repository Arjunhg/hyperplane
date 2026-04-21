import { useMemo } from "react";

import { AircraftRow } from "./AircraftRow";
import type { AircraftListProps } from "./Sidebar.types";

export function AircraftList({ aircraft }: AircraftListProps) {
  const sortedAircraft = useMemo(() => {
    return [...aircraft].sort((a, b) => {
      if (a.isStale !== b.isStale) {
        return a.isStale ? 1 : -1;
      }
      return b.lastUpdated - a.lastUpdated;
    });
  }, [aircraft]);

  if (sortedAircraft.length === 0) {
    return (
      <div className="rounded-md border border-gray-800 bg-gray-900/60 p-4 text-sm text-gray-400">
        No aircraft tracked yet
      </div>
    );
  }

  return (
    <div className="overflow-y-auto max-h-[calc(100vh-200px)]">
      <ul className="space-y-2">
        {sortedAircraft.map((item) => (
          <AircraftRow key={item.icao} aircraft={item} />
        ))}
      </ul>
    </div>
  );
}
