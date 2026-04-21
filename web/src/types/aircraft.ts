export type FixMethod = "CPR" | "MLAT" | "PREDICTED";

export interface PositionFix {
  icao: string;
  callsign: string | null;
  lat: number;
  lon: number;
  alt_ft: number;
  method: FixMethod;
  gdop: number | null;
  sensor_count: number | null;
  ts: number; // Unix milliseconds
}

export interface AircraftState extends PositionFix {
  lastUpdated: number; // client-side Date.now() when last fix arrived
  isStale: boolean; // true if no fix received in last 30 seconds
}

export type WsMessageType = "fix" | "snapshot" | "remove";

export interface WsMessage {
  type: WsMessageType;
  data: PositionFix | PositionFix[] | { icao: string };
}
