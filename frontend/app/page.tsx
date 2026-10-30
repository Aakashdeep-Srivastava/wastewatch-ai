"use client";

import { useEffect, useRef } from "react";
import Header from "@/components/Header";
import Globe, { type GlobeHandle } from "@/components/Globe";
import LocationStep from "@/components/LocationStep";
import SceneStep from "@/components/SceneStep";
import AnalysisProgress from "@/components/AnalysisProgress";
import ResultsView from "@/components/ResultsView";
import { useJourney } from "@/lib/store";

export default function Home() {
  const selection = useJourney((s) => s.selection);
  const result = useJourney((s) => s.result);
  const running = useJourney((s) => s.running);
  const liveSteps = useJourney((s) => s.liveSteps);
  const error = useJourney((s) => s.error);
  const flyTo = useJourney((s) => s.flyTo);
  const clearFlyTo = useJourney((s) => s.clearFlyTo);
  const setSelection = useJourney((s) => s.setSelection);
  const reset = useJourney((s) => s.reset);

  const globeRef = useRef<GlobeHandle>(null);

  // The store raises a transient flyTo signal (on location pick / region focus);
  // drive the imperative MapLibre camera here, then clear it.
  useEffect(() => {
    if (flyTo) {
      globeRef.current?.flyToBbox(flyTo);
      clearFlyTo();
    }
  }, [flyTo, clearFlyTo]);

  return (
    <div className="flex h-screen flex-col">
      <Header active="inspect" />
      <main className="grid min-h-0 flex-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="relative min-h-[60vh] lg:min-h-[420px]">
          <Globe ref={globeRef} selection={selection} result={result} onSelect={setSelection} />
        </div>

        <aside className="flex min-h-0 flex-col gap-5 overflow-auto rounded-2xl border border-slate-200 bg-white p-5">
          <LocationStep />

          {selection && !result && !running && liveSteps.length === 0 && <SceneStep />}

          {(running || liveSteps.length > 0 || result) && <AnalysisProgress />}

          {error && <p className="text-xs text-rose-600">Error: {error}</p>}

          {result && (
            <>
              <ResultsView />
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
