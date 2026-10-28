"use client";

import type { TraceStep } from "@/lib/types";

const CHECKLIST: { label: string; tools: string[] }[] = [
  { label: "Checking image quality", tools: ["cloud_gate", "select_alternate_date"] },
  { label: "Feature extraction & matching (ORB)", tools: ["coregister", "refine_ecc"] },
  { label: "Image registration (USAC / MAGSAC)", tools: ["coregister", "refine_ecc"] },
  { label: "Change detection", tools: ["detect_change"] },
  { label: "Region analysis & scoring", tools: ["detect_change", "inspect_roi_native"] },
  { label: "Agent decision making", tools: ["create_review_case", "decide"] },
  { label: "Generating results", tools: ["__result__"] },
];

interface Props {
  steps: TraceStep[];
  running: boolean;
  done: boolean; // result received
}

export default function AnalysisProgress({ steps, running, done }: Props) {
  if (!running && steps.length === 0 && !done) return null;
  const seen = new Set(steps.map((s) => s.tool));
  if (done) seen.add("__result__");

  const states = CHECKLIST.map((c) => c.tools.some((t) => seen.has(t)));
  const firstPending = states.indexOf(false);
  const completed = states.filter(Boolean).length;
  const pct = Math.round((completed / CHECKLIST.length) * 100);

  return (
    <section>
      <h2 className="mb-1 text-sm font-semibold text-slate-700">
        {done ? "3 · Analysis complete" : "3 · Inspection in progress"}
      </h2>
      <p className="mb-3 text-xs text-slate-500">An autonomous agent runs the OpenCV 5 vision pipeline, deciding each next action from the evidence.</p>
      <ol className="space-y-2">
        {CHECKLIST.map((c, i) => {
          const isDone = states[i];
          const isActive = running && !isDone && i === firstPending;
          return (
            <li key={i} className="flex items-center gap-3 text-sm">
              <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold
                ${isDone ? "bg-emerald-500 text-white" : isActive ? "bg-amber-400 text-slate-900" : "bg-slate-200 text-slate-500"}`}>
                {isDone ? "✓" : i + 1}
              </span>
              <span className={isDone ? "text-slate-700" : isActive ? "text-slate-900" : "text-slate-400"}>
                {c.label}
                {isActive && <span className="ml-2 animate-pulse text-xs text-amber-600">processing…</span>}
              </span>
            </li>
          );
        })}
      </ol>
      <div className="mt-3 flex items-center gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200">
          <div className="h-full bg-blue-600 transition-all" style={{ width: `${pct}%` }} />
        </div>
        <span className="font-mono text-xs text-slate-500">{pct}%</span>
      </div>
    </section>
  );
}
