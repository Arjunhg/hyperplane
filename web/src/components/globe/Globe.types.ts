import type { MutableRefObject } from "react";
import type * as Cesium from "cesium";

import type { AircraftState } from "../../types/aircraft";

export interface GlobeProps {
  aircraft: AircraftState[];
}

export interface AircraftLayerProps {
  viewerRef: MutableRefObject<Cesium.Viewer | null>;
  aircraft: AircraftState[];
}

export interface UseCesiumViewerResult {
  viewerRef: MutableRefObject<Cesium.Viewer | null>;
}
