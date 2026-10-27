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
  image_size: { w: number; h: number };
  aoi: Bbox | null;
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
