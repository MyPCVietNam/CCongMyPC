import { describe, expect, it } from "vitest";
import {
  faceBoxToOverlay,
  nativePxToOverlay,
  normRectToOverlay,
  objectContainMapping,
} from "./imageCoords";

describe("objectContainMapping", () => {
  it("letterboxes 2304x1296 into a wider element", () => {
    const map = objectContainMapping(2304, 1296, 1280, 400);
    expect(map.scale).toBeCloseTo(400 / 1296, 5);
    expect(map.contentHeight).toBeCloseTo(400, 3);
    expect(map.offsetY).toBeCloseTo(0, 3);
    expect(map.offsetX).toBeGreaterThan(0);
  });

  it("pillarboxes into a taller element", () => {
    const map = objectContainMapping(2304, 1296, 640, 900);
    expect(map.scale).toBeCloseTo(640 / 2304, 5);
    expect(map.offsetX).toBeCloseTo(0, 3);
    expect(map.offsetY).toBeGreaterThan(0);
  });

  it("maps native px and norm ROI consistently", () => {
    const map = objectContainMapping(2304, 1296, 1152, 648);
    expect(map.scale).toBeCloseTo(0.5, 5);
    const p = nativePxToOverlay(100, 200, map);
    expect(p.x).toBeCloseTo(50, 3);
    expect(p.y).toBeCloseTo(100, 3);
    const roi = normRectToOverlay({ x: 0.3, y: 0.05, w: 0.4, h: 0.25 }, 2304, 1296, map);
    expect(roi.x).toBeCloseTo(0.3 * 2304 * 0.5, 2);
    expect(roi.w).toBeCloseTo(0.4 * 2304 * 0.5, 2);
    const box = faceBoxToOverlay({ x_px: 400, y_px: 100, w_px: 160, h_px: 180 }, map);
    expect(box.w).toBeCloseTo(80, 3);
  });

  it("returns zero scale for empty element", () => {
    const map = objectContainMapping(2304, 1296, 0, 0);
    expect(map.scale).toBe(0);
  });
});
