import * as Cesium from "cesium";

export const ENTITY_COLORS = {
  MLAT: Cesium.Color.CYAN,
  CPR: Cesium.Color.LIME,
  PREDICTED: Cesium.Color.fromCssColorString("#6b7280"), // Tailwind gray-500
  STALE: Cesium.Color.fromCssColorString("#374151"), // Tailwind gray-700
} as const;

export const TRAIL_COLORS = {
  MLAT: Cesium.Color.CYAN.withAlpha(0.4),
  CPR: Cesium.Color.LIME.withAlpha(0.4),
  PREDICTED: Cesium.Color.fromCssColorString("#6b7280").withAlpha(0.2),
  STALE: Cesium.Color.fromCssColorString("#374151").withAlpha(0.1),
} as const;

export const POINT_SIZE = {
  ACTIVE: 8,
  STALE: 5,
} as const;

export const PATH_STYLE = {
  LEAD_TIME: 0,
  TRAIL_TIME: 120,
  WIDTH: 1.5,
} as const;

export const ENTITY_STYLE = {
  POINT_OUTLINE_COLOR: Cesium.Color.BLACK,
  POINT_OUTLINE_WIDTH: 1,
  LABEL_FONT: "12px monospace",
  LABEL_SCALE: 0.8,
  LABEL_OUTLINE_COLOR: Cesium.Color.BLACK,
  LABEL_OUTLINE_WIDTH: 2,
  LABEL_OFFSET_X: 10,
  LABEL_OFFSET_Y: 0,
} as const;
