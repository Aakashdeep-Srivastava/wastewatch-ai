import { create } from "zustand";
import type { Selection } from "@/components/Globe";
import { bboxAreaKm2, polygonAreaKm2 } from "@/lib/geo";
import type { Bbox, GeocodeResult, InspectResult, TraceStep } from "@/lib/types";

function ringFromBbox(b: Bbox): [number, number][] {
  return [
    [b[0], b[1]],
    [b[2], b[1]],
    [b[2], b[3]],
    [b[0], b[3]],
  ];
}

// -----------------------------------------------------------------------------
// The inspection-journey store (client/UI state). Zustand holds everything the
// 8-step flow needs; server data (scenes, alerts) lives in TanStack Query, not
// here. `flyTo` is a transient signal the page consumes to drive the imperative
// MapLibre camera, then clears.
// -----------------------------------------------------------------------------
export interface JourneyState {
  selection: Selection | null;
  locationName: string | null;
  liveSteps: TraceStep[];
  result: InspectResult | null;
  running: boolean;
  error: string;
  flyTo: Bbox | null;

  // location
  pickLocation: (r: GeocodeResult) => void;
  setSelection: (sel: Selection | null) => void;

  // imperative camera signal
  requestFlyTo: (b: Bbox) => void;
  clearFlyTo: () => void;

  // inspection run lifecycle (driven by the SSE stream in lib/queries)
  startRun: () => void;
  appendStep: (step: TraceStep) => void;
  setResult: (r: InspectResult) => void;
  setError: (msg: string) => void;
  finishRun: () => void;

  reset: () => void;
}

export const useJourney = create<JourneyState>((set) => ({
  selection: null,
  locationName: null,
  liveSteps: [],
  result: null,
  running: false,
  error: "",
  flyTo: null,

  pickLocation: (r) => {
    const bbox: Bbox =
      r.bbox ?? [r.lon - 0.05, r.lat - 0.05, r.lon + 0.05, r.lat + 0.05];
    set({
      selection: { bbox, polygon: ringFromBbox(bbox) },
      locationName: (r.name ?? "").split(",").slice(0, 2).join(",").trim() || null,
      result: null,
      flyTo: bbox,
    });
  },

  setSelection: (sel) =>
    set((s) => ({
      selection: sel,
      result: null,
      locationName: sel ? s.locationName : null,
    })),

  requestFlyTo: (b) => set({ flyTo: b }),
  clearFlyTo: () => set({ flyTo: null }),

  startRun: () => set({ running: true, error: "", liveSteps: [], result: null }),
  appendStep: (step) => set((s) => ({ liveSteps: [...s.liveSteps, step] })),
  setResult: (r) => set({ result: r }),
  setError: (msg) => set({ error: msg }),
  finishRun: () => set({ running: false }),

  reset: () => set({ result: null, liveSteps: [], error: "" }),
}));

// Derived selector: AOI area in km² from the current selection.
export function selectAreaKm2(s: JourneyState): number {
  if (!s.selection) return 0;
  return s.selection.polygon.length > 4
    ? polygonAreaKm2(s.selection.polygon)
    : bboxAreaKm2(s.selection.bbox);
}
