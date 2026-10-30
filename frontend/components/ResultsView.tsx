"use client";

import { useState } from "react";
import { artifactUrl } from "@/lib/api";
import { useReview } from "@/lib/queries";
import { useJourney } from "@/lib/store";
import type { Bbox, Blob } from "@/lib/types";

const STATUS_STYLE: Record<string, string> = {
  PENDING_REVIEW: "bg-amber-100 text-amber-800 ring-amber-200",
  NEEDS_REVIEW: "bg-amber-100 text-amber-800 ring-amber-200",
  NEEDS_MORE_INFO: "bg-blue-100 text-blue-800 ring-blue-200",
  NO_SIGNIFICANT_CHANGE: "bg-emerald-100 text-emerald-700 ring-emerald-200",
  CONFIRMED: "bg-rose-600 text-white ring-rose-600",
  DISMISSED: "bg-slate-200 text-slate-700 ring-slate-300",
};

function severity(ds: number): "High" | "Medium" | "Low" {
  return ds >= 0.75 ? "High" : ds >= 0.55 ? "Medium" : "Low";
}
function regionBbox(b: Blob, aoi: Bbox, size: { w: number; h: number }): Bbox {
  const [w, s, e, n] = aoi;
  const x1 = w + (b.x / size.w) * (e - w);
  const x2 = w + ((b.x + b.w) / size.w) * (e - w);
  const yTop = n - (b.y / size.h) * (n - s);
  const yBot = n - ((b.y + b.h) / size.h) * (n - s);
  return [Math.min(x1, x2), Math.min(yTop, yBot), Math.max(x1, x2), Math.max(yTop, yBot)];
}

function BeforeAfter({ before, after }: { before: string; after: string }) {
  const [pos, setPos] = useState(50);
  return (
    <div className="relative select-none overflow-hidden rounded-lg border border-slate-200">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={before} alt="Before (T1)" className="block w-full" />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={after} alt="After (T2)" className="absolute inset-0 block w-full" style={{ clipPath: `inset(0 0 0 ${pos}%)` }} />
      <span className="absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white">Before (T1)</span>
      <span className="absolute right-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white">After (T2)</span>
      <input type="range" min={0} max={100} value={pos} onChange={(e) => setPos(Number(e.target.value))}
        className="absolute bottom-2 left-1/2 w-11/12 -translate-x-1/2" />
    </div>
  );
}

export default function ResultsView() {
  const result = useJourney((s) => s.result);
  const requestFlyTo = useJourney((s) => s.requestFlyTo);
  const reviewMut = useReview();
  const [tab, setTab] = useState<"before" | "after" | "change" | "details">("change");
  const [token, setToken] = useState("dev-reviewer-token");
  const [comment, setComment] = useState("");
  const [status, setStatus] = useState(result?.status ?? "");
  const [msg, setMsg] = useState<{ t: string; k: "" | "ok" | "err" }>({ t: "", k: "" });

  if (!result) return null;

  const cb = `?id=${result.id}`;
  const before = artifactUrl("/out/in_before.png") + cb;
  const after = artifactUrl("/out/in_after.png") + cb;
  const change = result.artifacts.change ? artifactUrl(result.artifacts.change) + cb : after;
  const size = result.image_size;
  const blobs = result.blobs || [];
  const maxArea = blobs.reduce((m, b) => Math.max(m, b.area), 0);
  const largestKm2 = result.area_km2 && size.w && size.h
    ? (maxArea / (size.w * size.h)) * result.area_km2 : null;
  const reviewable = status === "PENDING_REVIEW" || status === "NEEDS_REVIEW" || status === "NEEDS_MORE_INFO";

  function submit(decision: "approve" | "dismiss" | "needs_info") {
    reviewMut.mutate(
      { id: result!.id, decision, token, comment },
      {
        onSuccess: (d) => {
          setStatus(d.status);
          setMsg({ t: "Recorded: " + d.status.replace(/_/g, " "), k: "ok" });
        },
        onError: (e) => setMsg({ t: (e as Error).message, k: "err" }),
      },
    );
  }

  const tabBtn = (id: typeof tab, label: string) => (
    <button onClick={() => setTab(id)}
      className={`rounded-md px-2.5 py-1 text-xs font-semibold ${tab === id ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>
      {label}
    </button>
  );

  return (
    <section className="space-y-4">
      <div>
        <h2 className="mb-2 text-sm font-semibold text-slate-700">4 · Results</h2>
        <div className="flex items-center justify-between">
          <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${STATUS_STYLE[status] ?? "bg-slate-100 text-slate-700 ring-slate-200"}`}>
            {status.replace(/_/g, " ")}
          </span>
          {result.dates?.t1 && result.dates?.t2 && (
            <span className="font-mono text-[11px] text-slate-500">{result.dates.t1} → {result.dates.t2}</span>
          )}
        </div>
        {result.display && <p className="mt-2 text-xs text-slate-500">{result.display}</p>}
      </div>

      {/* Nemotron intelligence brief — the AI interpretation layer */}
      {result.brief && (
        <div className="rounded-xl border border-indigo-200 bg-gradient-to-br from-indigo-50 to-white p-3">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-[#76b900] px-2 py-0.5 text-[10px] font-bold text-white">
              <i className="inline-block h-1.5 w-1.5 rounded-full bg-white" />
              NVIDIA Nemotron · Nebius Token Factory
            </span>
            {result.brief.confidence != null && (
              <span className="font-mono text-[10px] text-slate-500">
                confidence {Number(result.brief.confidence).toFixed(2)}
              </span>
            )}
          </div>
          {result.brief.headline && (
            <p className="text-sm font-semibold text-slate-800">{result.brief.headline}</p>
          )}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {result.brief.likely_cause && (
              <span className="rounded-md bg-slate-900 px-2 py-0.5 text-[10px] font-semibold text-white">
                {result.brief.likely_cause.replace(/_/g, " ")}
              </span>
            )}
            {result.brief.legality && (
              <span className={`rounded-md px-2 py-0.5 text-[10px] font-semibold ${
                result.brief.legality === "likely_unpermitted"
                  ? "bg-rose-100 text-rose-700"
                  : result.brief.legality === "likely_permitted"
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-slate-100 text-slate-600"}`}>
                {result.brief.legality.replace(/_/g, " ")}
              </span>
            )}
            {result.brief.severity && (
              <span className="rounded-md bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
                severity: {result.brief.severity}
              </span>
            )}
          </div>
          {result.brief.rationale && (
            <p className="mt-2 text-xs leading-relaxed text-slate-600">{result.brief.rationale}</p>
          )}
          {result.brief.recommended_action && (
            <p className="mt-1.5 text-xs text-slate-700">
              <b>Recommended:</b> {result.brief.recommended_action}
            </p>
          )}
          <p className="mt-2 text-[10px] text-slate-400">
            Advisory only — the deterministic policy sets the verdict; a human confirms.
            {result.brief.model ? ` · ${result.brief.model}` : ""}
          </p>
        </div>
      )}

      {/* Global environmental context (open data the model reasoned over) */}
      {result.enrichment && (
        <div className="rounded-lg border border-slate-200 p-3">
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Global environmental context
          </h3>
          <div className="flex flex-wrap gap-2 text-[11px]">
            {result.enrichment.nearest_waste_facility && (
              <span className="rounded-md bg-slate-100 px-2 py-1 text-slate-700">
                {result.enrichment.nearest_waste_facility.distance_m != null
                  ? `Nearest permitted site: ${result.enrichment.nearest_waste_facility.distance_m} m (${result.enrichment.nearest_waste_facility.kind ?? "waste"})`
                  : (result.enrichment.nearest_waste_facility.note ?? "No permitted site nearby")}
              </span>
            )}
            {result.enrichment.air_quality?.pm2_5 != null && (
              <span className="rounded-md bg-slate-100 px-2 py-1 text-slate-700">
                PM2.5 {result.enrichment.air_quality.pm2_5} {result.enrichment.air_quality.units}
              </span>
            )}
            {result.enrichment.news?.results && result.enrichment.news.results.length > 0 && (
              <span className="rounded-md bg-slate-100 px-2 py-1 text-slate-700">
                {result.enrichment.news.results.length} local report(s)
              </span>
            )}
          </div>
          {result.enrichment.news?.results && result.enrichment.news.results.length > 0 && (
            <ul className="mt-2 space-y-0.5">
              {result.enrichment.news.results.slice(0, 3).map((r, i) => (
                <li key={i} className="truncate text-[11px]">
                  <a href={r.url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">
                    {r.title}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* viewer */}
      <div>
        <div className="mb-2 flex flex-wrap gap-1.5">
          {tabBtn("before", "Before (T1)")}
          {tabBtn("after", "After (T2)")}
          {tabBtn("change", "Change")}
          {tabBtn("details", "Details")}
        </div>
        {tab === "details" ? (
          <div className="rounded-lg border border-slate-200 p-3 text-xs text-slate-600">
            <div className="grid grid-cols-2 gap-2">
              <div>Change score: <b>{result.change_score.toFixed(3)}</b></div>
              <div>Disturbed surface: <b>{result.disturbed_surface}</b></div>
              <div>Image size: <b>{size.w}×{size.h}px</b></div>
              <div>Source: <b>{result.source}</b></div>
            </div>
            {result.artifacts.cloud && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={artifactUrl(result.artifacts.cloud) + cb} alt="cloud gate" className="mt-2 w-full rounded border border-slate-200" />
            )}
          </div>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={tab === "before" ? before : tab === "after" ? after : change}
            alt={tab} className="w-full rounded-lg border border-slate-200" />
        )}
        <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-slate-500">
          <span className="flex items-center gap-1"><i className="inline-block h-2.5 w-2.5 rounded-sm bg-rose-500" /> High change</span>
          <span className="flex items-center gap-1"><i className="inline-block h-2.5 w-2.5 rounded-sm bg-amber-400" /> Medium</span>
          <span className="flex items-center gap-1"><i className="inline-block h-2.5 w-2.5 rounded-sm bg-emerald-500" /> Low</span>
        </div>
      </div>

      {/* stat tiles */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg border border-slate-200 p-2">
          <div className="text-lg font-bold text-slate-800">{result.num_regions ?? blobs.length}</div>
          <div className="text-[10px] text-slate-500">Change regions</div>
        </div>
        <div className="rounded-lg border border-slate-200 p-2">
          <div className="text-lg font-bold text-slate-800">{largestKm2 != null ? largestKm2.toFixed(2) + " km²" : maxArea + "px²"}</div>
          <div className="text-[10px] text-slate-500">Largest area</div>
        </div>
        <div className="rounded-lg border border-slate-200 p-2">
          <div className="text-lg font-bold text-slate-800">{result.change_score.toFixed(2)}</div>
          <div className="text-[10px] text-slate-500">Disturbance score</div>
        </div>
      </div>

      {/* explore details: before/after slider */}
      <div>
        <h3 className="mb-2 text-xs font-semibold text-slate-600">5 · Explore details — before / after</h3>
        <BeforeAfter before={before} after={after} />
      </div>

      {/* regions */}
      {blobs.length > 0 && result.aoi && (
        <div>
          <h3 className="mb-2 text-xs font-semibold text-slate-600">Detected regions ({blobs.length})</h3>
          <div className="max-h-48 space-y-1.5 overflow-auto">
            {blobs.map((b, i) => {
              const km2 = result.area_km2 && size.w ? (b.area / (size.w * size.h)) * result.area_km2 : null;
              const sev = severity(b.disturbed_surface);
              const sevColor = sev === "High" ? "text-rose-600" : sev === "Medium" ? "text-amber-600" : "text-emerald-600";
              return (
                <button key={i} onClick={() => requestFlyTo(regionBbox(b, result.aoi!, size))}
                  className="block w-full rounded-lg border border-slate-200 p-2 text-left text-xs hover:border-blue-400">
                  <div className="flex justify-between">
                    <b className="text-slate-700">#{i + 1}</b>
                    <span className={sevColor}>{sev}</span>
                  </div>
                  <div className="text-slate-500">
                    {km2 != null ? `${km2.toFixed(3)} km²` : `${b.area}px²`} · change-surface {b.disturbed_surface}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* review */}
      {reviewable && (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
          <h3 className="mb-2 text-xs font-semibold text-slate-600">6 · Review &amp; decide</h3>
          <input value={token} onChange={(e) => setToken(e.target.value)} placeholder="reviewer token"
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-xs" />
          <textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Add a comment (optional) e.g. likely construction activity"
            className="mt-2 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-xs" rows={2} />
          <div className="mt-2 flex flex-wrap gap-2">
            <button onClick={() => submit("approve")} className="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-500">Confirm</button>
            <button onClick={() => submit("dismiss")} className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100">Dismiss</button>
            <button onClick={() => submit("needs_info")} className="rounded-lg border border-blue-300 px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-50">Needs more info</button>
          </div>
          {msg.t && <p className={`mt-2 text-xs ${msg.k === "err" ? "text-rose-600" : "text-emerald-600"}`}>{msg.t}</p>}
        </div>
      )}
    </section>
  );
}
