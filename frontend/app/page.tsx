"use client";

import { useRef, useState } from "react";
import Image from "next/image";
import Globe, { type GlobeHandle } from "@/components/Globe";
import InspectPanel from "@/components/InspectPanel";
import type { Bbox, InspectResult } from "@/lib/types";

export default function Home() {
  const [aoi, setAoi] = useState<Bbox | null>(null);
  const [result, setResult] = useState<InspectResult | null>(null);
  const globeRef = useRef<GlobeHandle>(null);

  return (
    <div className="flex h-screen flex-col">
      <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
        <div className="flex items-center gap-3">
          <Image src="/logo.png" width={38} height={38} alt="WasteWatch AI" className="rounded-lg" priority />
          <div>
            <h1 className="text-base font-bold leading-tight">WasteWatch AI</h1>
            <p className="text-xs text-slate-500">Satellite Environmental Intelligence</p>
          </div>
        </div>
        <span className="flex items-center gap-2 text-xs text-slate-500">
          <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
          Agent online · human approves every alert
        </span>
      </header>

      <main className="grid min-h-0 flex-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_400px]">
        <div className="min-h-[420px]">
          <Globe ref={globeRef} aoi={aoi} result={result} onAOI={setAoi} />
        </div>

        <aside className="flex min-h-0 flex-col gap-4 overflow-hidden rounded-2xl border border-slate-200 bg-white p-5">
          <section>
            <h2 className="mb-2 text-sm font-semibold text-slate-700">Area of interest</h2>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-2 font-mono text-xs text-slate-600 break-all">
              {aoi ? `[${aoi.map((n) => n.toFixed(4)).join(", ")}]` : "none — draw a rectangle or use the current view on the globe"}
            </div>
          </section>

          <InspectPanel
            aoi={aoi}
            onResult={setResult}
            onDetectionFocus={() => globeRef.current?.flyToAOI()}
          />
        </aside>
      </main>
    </div>
  );
}
