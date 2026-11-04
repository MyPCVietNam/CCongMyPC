/** object-fit: contain mapping between native frame pixels and overlay CSS space. */

export type NormRect = { x: number; y: number; w: number; h: number };

export type ContainMapping = {
  contentWidth: number;
  contentHeight: number;
  offsetX: number;
  offsetY: number;
  scale: number;
};

export function objectContainMapping(
  nativeW: number,
  nativeH: number,
  elementW: number,
  elementH: number
): ContainMapping {
  const nw = Math.max(nativeW, 1);
  const nh = Math.max(nativeH, 1);
  const ew = Math.max(elementW, 0);
  const eh = Math.max(elementH, 0);
  if (ew <= 0 || eh <= 0) {
    return { contentWidth: 0, contentHeight: 0, offsetX: 0, offsetY: 0, scale: 0 };
  }
  const scale = Math.min(ew / nw, eh / nh);
  const contentWidth = nw * scale;
  const contentHeight = nh * scale;
  return {
    contentWidth,
    contentHeight,
    offsetX: (ew - contentWidth) / 2,
    offsetY: (eh - contentHeight) / 2,
    scale,
  };
}

export function nativePxToOverlay(
  xPx: number,
  yPx: number,
  map: ContainMapping
): { x: number; y: number } {
  return {
    x: map.offsetX + xPx * map.scale,
    y: map.offsetY + yPx * map.scale,
  };
}

export function normRectToOverlay(rect: NormRect, nativeW: number, nativeH: number, map: ContainMapping) {
  const x0 = rect.x * nativeW;
  const y0 = rect.y * nativeH;
  const x1 = (rect.x + rect.w) * nativeW;
  const y1 = (rect.y + rect.h) * nativeH;
  const a = nativePxToOverlay(x0, y0, map);
  const b = nativePxToOverlay(x1, y1, map);
  return { x: a.x, y: a.y, w: Math.max(b.x - a.x, 0), h: Math.max(b.y - a.y, 0) };
}

export function faceBoxToOverlay(
  face: { x_px: number; y_px: number; w_px: number; h_px: number },
  map: ContainMapping
) {
  const a = nativePxToOverlay(face.x_px, face.y_px, map);
  return {
    x: a.x,
    y: a.y,
    w: face.w_px * map.scale,
    h: face.h_px * map.scale,
  };
}
