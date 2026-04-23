import { MethodBadge } from "../shared/MethodBadge";
import type { AircraftRowProps } from "./Sidebar.types";

function formatAltitudeFeet(altitudeFeet: number): string {
  return `${Math.round(altitudeFeet).toLocaleString()} ft`;
}

export function AircraftRow({ aircraft, onFocusAircraft }: AircraftRowProps) {
  const rowOpacity = aircraft.isStale ? "opacity-40" : "";
  const callsign = aircraft.callsign && aircraft.callsign.trim() !== "" ? aircraft.callsign : "-";

  return (
    <li className={`rounded-md transition-colors hover:bg-gray-800 ${rowOpacity}`}>
      <button
        type="button"
        onClick={() => onFocusAircraft(aircraft.icao)}
        className="w-full px-3 py-2 text-left"
        title="Focus aircraft on globe"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="font-mono text-sm text-gray-100">{aircraft.icao.toUpperCase()}</div>
            <div className="truncate text-sm text-gray-300">{callsign}</div>
            <div className="text-xs text-gray-400">{formatAltitudeFeet(aircraft.alt_ft)}</div>
          </div>
          <MethodBadge method={aircraft.method} />
        </div>
      </button>
    </li>
  );
}
