import { useRef } from "react";
import "cesium/Build/Cesium/Widgets/widgets.css";

import { AircraftLayer } from "./AircraftLayer";
import type { GlobeProps } from "./Globe.types";
import { useCesiumViewer } from "./useCesiumViewer";

export function Globe({ aircraft, focusRequest }: GlobeProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { viewerRef } = useCesiumViewer(containerRef);

  return (
    <div ref={containerRef} className="w-full h-full">
      <AircraftLayer viewerRef={viewerRef} aircraft={aircraft} focusRequest={focusRequest} />
    </div>
  );
}
