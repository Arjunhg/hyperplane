import type { AircraftState } from "../../types/aircraft";

export type ConnectionStatus = "connecting" | "connected" | "disconnected";

export interface AircraftRowProps {
  aircraft: AircraftState;
  onFocusAircraft: (icao: string) => void;
}

export interface AircraftListProps {
  aircraft: AircraftState[];
  onFocusAircraft: (icao: string) => void;
}

export interface StatsPanelProps {
  aircraft: AircraftState[];
  wsStatus: ConnectionStatus;
}

export interface SidebarProps {
  aircraft: AircraftState[];
  wsStatus: ConnectionStatus;
  onFocusAircraft: (icao: string) => void;
}
