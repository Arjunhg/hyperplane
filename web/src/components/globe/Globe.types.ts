import type { MutableRefObject } from "react";
import type * as Cesium from "cesium";

import type { AircraftState } from "../../types/aircraft";

export interface FocusRequest {
  icao: string;
  requestId: number;
}

export interface GlobeProps {
  aircraft: AircraftState[];
  focusRequest: FocusRequest | null;
}

export interface AircraftLayerProps {
  viewerRef: MutableRefObject<Cesium.Viewer | null>;
  aircraft: AircraftState[];
  focusRequest: FocusRequest | null;
}

export interface UseCesiumViewerResult {
  viewerRef: MutableRefObject<Cesium.Viewer | null>;
}
