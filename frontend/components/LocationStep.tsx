"use client";

import { useState } from "react";
import { useGeocode } from "@/lib/queries";
import { useJourney, selectAreaKm2 } from "@/lib/store";
import { fmtBbox } from "@/lib/geo";

export default function LocationStep() {
  const [q, setQ] = useState("");
  const selection = useJourney((s) => s.selection);
  const locationName = useJourney((s) => s.locationName);
  const pickLocation = useJourney((s) => s.pickLocation);
  const area = useJourney(selectAreaKm2);
  const geo = useGeocode();

  function search(e: React.FormEvent) {
    e.preventDefault();
    const term = q.trim();
    if (!term) return;
    geo.mutate(term);
  }

  const results = geo.data ?? [];

  return (
    <section>
      <h2 className="mb-1 text-sm font-semibold text-slate-700">1 · Select location</h2>
      <p className="mb-3 text-xs text-slate-500">Search a place, then draw a rectangle or polygon on the globe (or use the current view).</p>

      <form onSubmit={search} className="flex gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search e.g. Goa, India"
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
        <button className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-800" disabled={geo.isPending}>
          {geo.isPending ? "…" : "Search"}
        </button>
      </form>
      {geo.isError && <p className="mt-2 text-xs text-rose-600">Search failed.</p>}

      {results.length > 0 && (
        <ul className="mt-2 divide-y divide-slate-100 overflow-hidden rounded-lg border border-slate-200">
          {results.map((r, i) => (
            <li key={i}>
              <button
                onClick={() => { pickLocation(r); setQ((r.name ?? "").split(",")[0]); geo.reset(); }}
                className="block w-full px-3 py-2 text-left text-xs hover:bg-slate-50"
              >
                {r.name}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
        <div className="text-xs font-semibold text-slate-600">
          {locationName ?? "No location selected"}
        </div>
        {selection ? (
          <div className="mt-1 space-y-0.5 text-xs text-slate-500">
            <div>Area ≈ <b className="text-slate-700">{area.toFixed(1)} km²</b></div>
            <div className="font-mono break-all">{fmtBbox(selection.bbox)}</div>
          </div>
        ) : (
          <div className="mt-1 text-xs text-slate-400">Draw an area of interest on the globe.</div>
        )}
      </div>
    </section>
  );
}
