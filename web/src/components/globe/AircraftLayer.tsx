import { useEffect, useRef } from "react";
import * as Cesium from "cesium";

import {
  ENTITY_COLORS,
  ENTITY_STYLE,
  POINT_SIZE,
} from "../../constants/cesium";
import type { AircraftState, FixMethod } from "../../types/aircraft";
import type { AircraftLayerProps } from "./Globe.types";

function getEntityColor(method: FixMethod, isStale: boolean): Cesium.Color {
  return isStale ? ENTITY_COLORS.STALE : ENTITY_COLORS[method];
}

function formatLabelText(fix: AircraftState): string {
  if (fix.callsign !== null && fix.callsign.trim() !== "") {
    return `${fix.icao.toUpperCase()} ${fix.callsign.trim()}`;
  }
  return fix.icao.toUpperCase();
}

function buildCartesianPosition(fix: AircraftState): Cesium.Cartesian3 {
  return Cesium.Cartesian3.fromDegrees(fix.lon, fix.lat, fix.alt_ft * 0.3048);
}

export function AircraftLayer({ viewerRef, aircraft, focusRequest }: AircraftLayerProps) {
  const entityMap = useRef<Map<string, Cesium.Entity>>(new Map());
  const hasAutoFocused = useRef(false);

  // --- Sync entities with aircraft state ---
  useEffect(() => {
    const viewer = viewerRef.current;
    if (viewer === null) {
      return;
    }

    const incoming = new Set<string>();

    for (const fix of aircraft) {
      const icao = fix.icao.toUpperCase();
      incoming.add(icao);

      const cartesian = buildCartesianPosition(fix);
      const pointColor = getEntityColor(fix.method, fix.isStale);
      const pointSize = fix.isStale ? POINT_SIZE.STALE : POINT_SIZE.ACTIVE;
      const labelText = formatLabelText(fix);

      const entity = entityMap.current.get(icao);
      if (entity === undefined) {
        // Use ConstantPositionProperty so the entity is always visible
        // regardless of the viewer clock time.
        const created = viewer.entities.add(
          new Cesium.Entity({
            id: icao,
            position: cartesian,
            point: new Cesium.PointGraphics({
              pixelSize: pointSize,
              color: pointColor,
              outlineColor: ENTITY_STYLE.POINT_OUTLINE_COLOR,
              outlineWidth: ENTITY_STYLE.POINT_OUTLINE_WIDTH,
            }),
            label: new Cesium.LabelGraphics({
              text: labelText,
              font: ENTITY_STYLE.LABEL_FONT,
              scale: ENTITY_STYLE.LABEL_SCALE,
              fillColor: pointColor,
              outlineColor: ENTITY_STYLE.LABEL_OUTLINE_COLOR,
              outlineWidth: ENTITY_STYLE.LABEL_OUTLINE_WIDTH,
              style: Cesium.LabelStyle.FILL_AND_OUTLINE,
              pixelOffset: new Cesium.Cartesian2(
                ENTITY_STYLE.LABEL_OFFSET_X,
                ENTITY_STYLE.LABEL_OFFSET_Y,
              ),
              horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
              verticalOrigin: Cesium.VerticalOrigin.CENTER,
            }),
          }),
        );

        entityMap.current.set(icao, created);
        continue;
      }

      // Update position directly — ConstantPositionProperty updates instantly.
      entity.position = new Cesium.ConstantPositionProperty(cartesian);

      if (entity.point !== undefined) {
        entity.point.pixelSize = new Cesium.ConstantProperty(pointSize);
        entity.point.color = new Cesium.ConstantProperty(pointColor);
      }

      if (entity.label !== undefined) {
        entity.label.text = new Cesium.ConstantProperty(labelText);
        entity.label.fillColor = new Cesium.ConstantProperty(pointColor);
      }
    }

    // Remove entities for aircraft no longer in the state.
    for (const [icao, entity] of entityMap.current.entries()) {
      if (incoming.has(icao)) {
        continue;
      }
      viewer.entities.remove(entity);
      entityMap.current.delete(icao);
    }
  }, [aircraft, viewerRef]);

  // --- Auto-focus on first aircraft arrival ---
  useEffect(() => {
    const viewer = viewerRef.current;
    if (viewer === null) {
      return;
    }

    if (aircraft.length === 0) {
      hasAutoFocused.current = false;
      return;
    }

    if (hasAutoFocused.current) {
      return;
    }

    hasAutoFocused.current = true;

    const first = aircraft[0];
    const destination = Cesium.Cartesian3.fromDegrees(
      first.lon,
      first.lat,
      first.alt_ft * 0.3048 + 200_000,
    );
    viewer.camera.flyTo({
      destination,
      orientation: {
        heading: 0,
        pitch: Cesium.Math.toRadians(-60),
        roll: 0,
      },
      duration: 1.5,
    });
  }, [aircraft.length, viewerRef]);

  // --- Click-to-focus from sidebar ---
  useEffect(() => {
    const viewer = viewerRef.current;
    if (viewer === null || focusRequest === null) {
      return;
    }

    const normalizedIcao = focusRequest.icao.toUpperCase();
    const entity = entityMap.current.get(normalizedIcao) ?? viewer.entities.getById(normalizedIcao);
    if (entity === undefined) {
      return;
    }

    void viewer.flyTo(entity, {
      duration: 1.0,
      offset: new Cesium.HeadingPitchRange(0, -0.55, 220_000),
    });
  }, [focusRequest, viewerRef, aircraft.length]);

  // --- Cleanup on unmount ---
  useEffect(() => {
    return () => {
      const viewer = viewerRef.current;
      if (viewer === null) {
        entityMap.current.clear();
        return;
      }

      for (const entity of entityMap.current.values()) {
        viewer.entities.remove(entity);
      }
      entityMap.current.clear();
    };
  }, [viewerRef]);

  return null;
}
