import type { Bbox } from "./types";

// Approximate area of a lat/lng bbox in km² (equirectangular, fine for AOIs).
export function bboxAreaKm2(b: Bbox): number {
  const [w, s, e, n] = b;
  const latMid = ((s + n) / 2) * (Math.PI / 180);
  const widthKm = Math.abs(e - w) * 111.32 * Math.cos(latMid);
  const heightKm = Math.abs(n - s) * 110.57;
  return widthKm * heightKm;
}

// Area of a polygon (array of [lng,lat]) in km², planar approx around centroid.
export function polygonAreaKm2(pts: [number, number][]): number {
  if (pts.length < 3) return 0;
  const latMid =
    (pts.reduce((a, p) => a + p[1], 0) / pts.length) * (Math.PI / 180);
  const kx = 111.32 * Math.cos(latMid);
  const ky = 110.57;
  let area = 0;
  for (let i = 0; i < pts.length; i++) {
    const [x1, y1] = pts[i];
    const [x2, y2] = pts[(i + 1) % pts.length];
    area += x1 * kx * (y2 * ky) - x2 * kx * (y1 * ky);
  }
  return Math.abs(area) / 2;
}

export function polygonBbox(pts: [number, number][]): Bbox {
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

export function bboxCenter(b: Bbox): [number, number] {
  return [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];
}

export function fmtBbox(b: Bbox): string {
  return `[${b.map((n) => n.toFixed(4)).join(", ")}]`;
}
