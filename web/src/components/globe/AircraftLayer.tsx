import { useEffect, useRef } from "react";
import * as Cesium from "cesium";

import {
  ENTITY_COLORS,
  ENTITY_STYLE,
  PATH_STYLE,
  POINT_SIZE,
  TRAIL_COLORS,
} from "../../constants/cesium";
import type { AircraftState, FixMethod } from "../../types/aircraft";
import type { AircraftLayerProps } from "./Globe.types";

function getEntityColor(method: FixMethod, isStale: boolean): Cesium.Color {
  return isStale ? ENTITY_COLORS.STALE : ENTITY_COLORS[method];
}

function getTrailColor(method: FixMethod, isStale: boolean): Cesium.Color {
  return isStale ? TRAIL_COLORS.STALE : TRAIL_COLORS[method];
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

function buildSampleTime(fix: AircraftState): Cesium.JulianDate {
  return Cesium.JulianDate.fromDate(new Date(fix.ts));
}

export function AircraftLayer({ viewerRef, aircraft }: AircraftLayerProps) {
  const entityMap = useRef<Map<string, Cesium.Entity>>(new Map());

  useEffect(() => {
    const viewer = viewerRef.current;
    if (viewer === null) {
      return;
    }

    const incoming = new Set<string>();

    for (const fix of aircraft) {
      const icao = fix.icao.toUpperCase();
      incoming.add(icao);

      const positionSample = buildCartesianPosition(fix);
      const sampleTime = buildSampleTime(fix);
      const pointColor = getEntityColor(fix.method, fix.isStale);
      const trailColor = getTrailColor(fix.method, fix.isStale);
      const pointSize = fix.isStale ? POINT_SIZE.STALE : POINT_SIZE.ACTIVE;
      const labelText = formatLabelText(fix);

      const entity = entityMap.current.get(icao);
      if (entity === undefined) {
        const position = new Cesium.SampledPositionProperty();
        position.addSample(sampleTime, positionSample);

        const created = viewer.entities.add(
          new Cesium.Entity({
            id: icao,
            position,
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
            path: new Cesium.PathGraphics({
              leadTime: PATH_STYLE.LEAD_TIME,
              trailTime: PATH_STYLE.TRAIL_TIME,
              width: PATH_STYLE.WIDTH,
              material: trailColor,
            }),
          }),
        );

        entityMap.current.set(icao, created);
        continue;
      }

      if (entity.position instanceof Cesium.SampledPositionProperty) {
        entity.position.addSample(sampleTime, positionSample);
      }

      if (entity.point !== undefined) {
        entity.point.pixelSize = new Cesium.ConstantProperty(pointSize);
        entity.point.color = new Cesium.ConstantProperty(pointColor);
      }

      if (entity.label !== undefined) {
        entity.label.text = new Cesium.ConstantProperty(labelText);
        entity.label.fillColor = new Cesium.ConstantProperty(pointColor);
      }

      if (entity.path !== undefined) {
        entity.path.material = new Cesium.ColorMaterialProperty(trailColor);
      }
    }

    for (const [icao, entity] of entityMap.current.entries()) {
      if (incoming.has(icao)) {
        continue;
      }
      viewer.entities.remove(entity);
      entityMap.current.delete(icao);
    }
  }, [aircraft, viewerRef]);

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
