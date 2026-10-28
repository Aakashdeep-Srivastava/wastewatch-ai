export type Bbox = [number, number, number, number]; // [west, south, east, north]

export interface Blob {
  x: number;
  y: number;
  w: number;
  h: number;
  area: number;
  disturbed_surface: number;
}

export interface TraceStep {
  step: number;
  tool: string;
  metric: Record<string, unknown>;
  decision: string;
  t: number;
}

export interface InspectResult {
  id: string;
  status: string;
  candidate_type?: string | null;
  display?: string;
  change_score: number;
  disturbed_surface: number;
  blobs: Blob[];
  num_regions?: number;
  image_size: { w: number; h: number };
  aoi: Bbox | null;
  location?: string | null;
  area_km2?: number | null;
  dates?: { t1?: string; t2?: string } | null;
  source?: string;
  created?: number;
  adviser?: unknown;
  trace: TraceStep[];
  artifacts: Record<string, string>;
}

export type StreamEvent =
  | { type: "start"; image_size: { w: number; h: number }; aoi: Bbox | null }
  | ({ type: "step" } & TraceStep)
  | { type: "result"; record: InspectResult }
  | { type: "ui"; component: unknown }
  | { type: "error"; message: string };

export interface Scene {
  id: string;
  date: string;
  datetime: string;
  cloud_cover: number;
  resolution_m: number;
  visual: string;
  thumbnail: string | null;
}

export interface GeocodeResult {
  name: string;
  lat: number;
  lon: number;
  bbox: Bbox | null;
}

export interface AlertSummary {
  id: string;
  status: string;
  location: string | null;
  created: number | null;
  updated: number | null;
  num_regions: number;
  change_score: number | null;
  area_km2: number | null;
  dates: { t1?: string; t2?: string } | null;
  source: string | null;
}
