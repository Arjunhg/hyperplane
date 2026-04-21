import { useEffect, useRef } from "react";
import * as Cesium from "cesium";
import type { RefObject } from "react";

import type { UseCesiumViewerResult } from "./Globe.types";

export function useCesiumViewer(
  containerRef: RefObject<HTMLDivElement>,
): UseCesiumViewerResult {
  const viewerRef = useRef<Cesium.Viewer | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (container === null || viewerRef.current !== null) {
      return;
    }

    viewerRef.current = new Cesium.Viewer(container, {
      animation: false,
      timeline: false,
      geocoder: false,
      homeButton: false,
      baseLayerPicker: false,
      sceneModePicker: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: false,
      navigationHelpButton: true,
    });

    return () => {
      if (viewerRef.current !== null && !viewerRef.current.isDestroyed()) {
        viewerRef.current.destroy();
      }
      viewerRef.current = null;
    };
  }, [containerRef]);

  return { viewerRef };
}
