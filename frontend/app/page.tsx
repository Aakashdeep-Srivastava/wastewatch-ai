"use client";

import { useRef, useState } from "react";
import Header from "@/components/Header";
import Globe, { type GlobeHandle, type Selection } from "@/components/Globe";
import LocationStep from "@/components/LocationStep";
import SceneStep from "@/components/SceneStep";
import AnalysisProgress from "@/components/AnalysisProgress";
import ResultsView from "@/components/ResultsView";
import { streamSceneInspect, type SceneInspectBody } from "@/lib/api";
import { bboxAreaKm2, polygonAreaKm2 } from "@/lib/geo";
import type { Bbox, GeocodeResult, InspectResult, TraceStep } from "@/lib/types";

function ringFromBbox(b: Bbox): [number, number][] {
  return [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]];
}

export default function Home() {
  const [selection, setSelection] = useState<Selection | null>(null);
  const [locationName, setLocationName] = useState<string | null>(null);
  const [liveSteps, setLiveSteps] = useState<TraceStep[]>([]);
  const [result, setResult] = useState<InspectResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const globeRef = useRef<GlobeHandle>(null);

  const areaKm2 = selection
    ? selection.polygon.length > 4
      ? polygonAreaKm2(selection.polygon)
      : bboxAreaKm2(selection.bbox)
    : 0;

  function pickLocation(r: GeocodeResult) {
    const bbox = r.bbox ?? ([r.lon - 0.05, r.lat - 0.05, r.lon + 0.05, r.lat + 0.05] as Bbox);
    setSelection({ bbox, polygon: ringFromBbox(bbox) });
    setLocationName(r.name.split(",").slice(0, 2).join(",").trim());
    setResult(null);
    globeRef.current?.flyToBbox(bbox);
  }

  function onSelect(sel: Selection | null) {
    setSelection(sel);
    setResult(null);
    if (!sel) setLocationName(null);
  }

  async function runScene(body: SceneInspectBody) {
    setRunning(true);
    setError("");
    setLiveSteps([]);
    setResult(null);
    try {
      await streamSceneInspect(body, (ev) => {
        if (ev.type === "step") {
          const { type: _t, ...step } = ev;
          setLiveSteps((prev) => [...prev, step as TraceStep]);
        } else if (ev.type === "result") {
          setResult(ev.record);
        } else if (ev.type === "error") {
          setError(ev.message);
        }
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  function reset() {
    setResult(null);
    setLiveSteps([]);
    setError("");
  }

  return (
    <div className="flex h-screen flex-col">
      <Header active="inspect" />
      <main className="grid min-h-0 flex-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="relative min-h-[60vh] lg:min-h-[420px]">
          <Globe ref={globeRef} selection={selection} result={result} onSelect={onSelect} />
        </div>

        <aside className="flex min-h-0 flex-col gap-5 overflow-auto rounded-2xl border border-slate-200 bg-white p-5">
          <LocationStep selection={selection} locationName={locationName} onPick={pickLocation} />

          {selection && !result && !running && liveSteps.length === 0 && (
            <SceneStep selection={selection} locationName={locationName} areaKm2={areaKm2} running={running} onRun={runScene} />
          )}

          {(running || liveSteps.length > 0 || result) && (
            <AnalysisProgress steps={liveSteps} running={running} done={!!result} />
          )}

          {error && <p className="text-xs text-rose-600">Error: {error}</p>}

          {result && (
            <>
              <ResultsView
                result={result}
                onReviewed={() => { /* status handled inside; dashboard reflects on reload */ }}
                onFocusRegion={(b) => globeRef.current?.flyToBbox(b)}
              />
              <button onClick={reset} className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100">
                Run another inspection on this area
              </button>
            </>
          )}
        </aside>
      </main>
    </div>
  );
}
