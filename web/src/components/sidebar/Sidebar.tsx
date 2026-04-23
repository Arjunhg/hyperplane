import { AircraftList } from "./AircraftList";
import { StatsPanel } from "./StatsPanel";
import type { SidebarProps } from "./Sidebar.types";

export function Sidebar({ aircraft, wsStatus, onFocusAircraft }: SidebarProps) {
  return (
    <aside className="w-80 h-full border-r border-gray-700 bg-gray-900 p-4">
      <div className="flex h-full flex-col gap-4">
        <StatsPanel aircraft={aircraft} wsStatus={wsStatus} />
        <AircraftList aircraft={aircraft} onFocusAircraft={onFocusAircraft} />
      </div>
    </aside>
  );
}
