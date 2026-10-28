"use client";

import { useState } from "react";
import { searchScenes, type SceneInspectBody } from "@/lib/api";
import type { Scene } from "@/lib/types";
import type { Selection } from "./Globe";

interface Props {
  selection: Selection | null;
  locationName: string | null;
  areaKm2: number;
  running: boolean;
  onRun: (body: SceneInspectBody) => void;
}

function yearAgo(): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - 1);
  return d.toISOString().slice(0, 10);
}

export default function SceneStep({ selection, locationName, areaKm2, running, onRun }: Props) {
  const [start, setStart] = useState(yearAgo());
  const [end, setEnd] = useState(new Date().toISOString().slice(0, 10));
  const [maxCloud, setMaxCloud] = useState(20);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [t1, setT1] = useState<string>("");
  const [t2, setT2] = useState<string>("");
  const [alt, setAlt] = useState<string>("");

  async function find() {
    if (!selection) return;
    setLoading(true); setErr(""); setScenes([]);
    try {
      const s = await searchScenes(selection.bbox, start, end, maxCloud);
      setScenes(s);
      if (s.length) { setT2(s[0].id); setT1(s[s.length - 1].id); }
      if (!s.length) setErr("No clear scenes found. Widen the date range or cloud limit.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const byId = (id: string) => scenes.find((s) => s.id === id) || null;
  function run() {
    const a = byId(t1), b = byId(t2);
    if (!selection || !a || !b) return;
    onRun({
      aoi: selection.bbox,
      t1_visual: a.visual, t2_visual: b.visual,
      alt_visual: byId(alt)?.visual ?? null,
      location: locationName,
      area_km2: Number(areaKm2.toFixed(2)),
      t1_date: a.date, t2_date: b.date,
    });
  }

  if (!selection) return null;

  const Thumb = ({ s }: { s: Scene | null }) =>
    s ? (
      <div className="mt-1 flex items-center gap-2">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {s.thumbnail ? <img src={s.thumbnail} alt={s.date} className="h-12 w-12 rounded border border-slate-200 object-cover" /> : null}
        <div className="text-[11px] text-slate-500">
          <div className="font-mono">{s.date}</div>
          <div>cloud {s.cloud_cover}% · {s.resolution_m} m</div>
        </div>
      </div>
    ) : null;

  const sel = "w-full rounded-lg border border-slate-300 px-2 py-1.5 text-xs";

  return (
    <section>
      <h2 className="mb-1 text-sm font-semibold text-slate-700">2 · Choose satellite images</h2>
      <p className="mb-3 text-xs text-slate-500">Real Sentinel-2 L2A scenes for this AOI (Earth Search / AWS open data).</p>

      <div className="grid grid-cols-2 gap-2">
        <label className="text-xs text-slate-500">From<input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={sel} /></label>
        <label className="text-xs text-slate-500">To<input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className={sel} /></label>
      </div>
      <label className="mt-2 block text-xs text-slate-500">
        Max cloud cover: <b className="text-slate-700">{maxCloud}%</b>
        <input type="range" min={0} max={80} value={maxCloud} onChange={(e) => setMaxCloud(Number(e.target.value))} className="w-full" />
      </label>
      <button onClick={find} disabled={loading} className="mt-2 w-full rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50">
        {loading ? "Searching Sentinel-2…" : "Find available images"}
      </button>
      {err && <p className="mt-2 text-xs text-rose-600">{err}</p>}

      {scenes.length > 0 && (
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <span className="text-xs font-semibold text-slate-600">Earlier (T1)</span>
              <select value={t1} onChange={(e) => setT1(e.target.value)} className={sel}>
                {scenes.map((s) => <option key={s.id} value={s.id}>{s.date} · {s.cloud_cover}%</option>)}
              </select>
              <Thumb s={byId(t1)} />
            </div>
            <div>
              <span className="text-xs font-semibold text-slate-600">Later (T2)</span>
              <select value={t2} onChange={(e) => setT2(e.target.value)} className={sel}>
                {scenes.map((s) => <option key={s.id} value={s.id}>{s.date} · {s.cloud_cover}%</option>)}
              </select>
              <Thumb s={byId(t2)} />
            </div>
          </div>
          <div>
            <span className="text-xs font-semibold text-slate-600">Alternative date (optional, if cloudy)</span>
            <select value={alt} onChange={(e) => setAlt(e.target.value)} className={sel}>
              <option value="">— none —</option>
              {scenes.map((s) => <option key={s.id} value={s.id}>{s.date} · {s.cloud_cover}%</option>)}
            </select>
          </div>
          <button onClick={run} disabled={running || !t1 || !t2} className="w-full rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50">
            {running ? "Running inspection…" : "Run inspection →"}
          </button>
          <p className="text-[11px] text-slate-400">Choose clear, low-cloud images for reliable change detection.</p>
        </div>
      )}
    </section>
  );
}
