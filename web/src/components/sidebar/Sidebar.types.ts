import type { AircraftState } from "../../types/aircraft";

export type ConnectionStatus = "connecting" | "connected" | "disconnected";

export interface AircraftRowProps {
  aircraft: AircraftState;
}

export interface AircraftListProps {
  aircraft: AircraftState[];
}

export interface StatsPanelProps {
  aircraft: AircraftState[];
  wsStatus: ConnectionStatus;
}

export interface SidebarProps {
  aircraft: AircraftState[];
  wsStatus: ConnectionStatus;
}
