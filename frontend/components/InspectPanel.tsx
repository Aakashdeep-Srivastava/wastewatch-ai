"use client";

import { useRef, useState } from "react";
import { approve, streamInspect } from "@/lib/api";
import type { Bbox, InspectResult, TraceStep } from "@/lib/types";

interface Props {
  aoi: Bbox | null;
  onResult: (r: InspectResult | null) => void;
  onDetectionFocus: () => void;
}

const STATUS_STYLE: Record<string, string> = {
  PENDING_REVIEW: "bg-rose-100 text-rose-700 ring-rose-200",
  NEEDS_REVIEW: "bg-rose-100 text-rose-700 ring-rose-200",
  NO_SIGNIFICANT_CHANGE: "bg-emerald-100 text-emerald-700 ring-emerald-200",
  CONFIRMED: "bg-rose-600 text-white ring-rose-600",
  DISMISSED: "bg-slate-200 text-slate-700 ring-slate-300",
};

export default function InspectPanel({ aoi, onResult, onDetectionFocus }: Props) {
  const beforeRef = useRef<HTMLInputElement>(null);
  const afterRef = useRef<HTMLInputElement>(null);
  const altRef = useRef<HTMLInputElement>(null);

  const [events, setEvents] = useState<TraceStep[]>([]);
  const [result, setResult] = useState<InspectResult | null>(null);
  const [status, setStatus] = useState<string>("");
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState<{ text: string; kind: "" | "ok" | "err" }>({ text: "", kind: "" });
  const [token, setToken] = useState("dev-reviewer-token");
  const [reviewMsg, setReviewMsg] = useState<{ text: string; kind: "" | "ok" | "err" }>({ text: "", kind: "" });

  const reviewable = status === "PENDING_REVIEW" || status === "NEEDS_REVIEW";

  async function run() {
    const before = beforeRef.current?.files?.[0];
    const after = afterRef.current?.files?.[0];
    const altAfter = altRef.current?.files?.[0] ?? null;
    if (!before || !after) {
      setMsg({ text: "Select both a before and an after image.", kind: "err" });
      return;
    }
    setRunning(true);
    setEvents([]);
    setResult(null);
    setStatus("");
    setReviewMsg({ text: "", kind: "" });
    onResult(null);
    setMsg({ text: "Agent working…", kind: "" });
    try {
      await streamInspect({ before, after, altAfter, aoi }, (ev) => {
        if (ev.type === "step") {
          const { type: _t, ...step } = ev;
          setEvents((prev) => [...prev, step as TraceStep]);
        } else if (ev.type === "result") {
          setResult(ev.record);
          setStatus(ev.record.status);
          onResult(ev.record);
        } else if (ev.type === "error") {
          setMsg({ text: "Error: " + ev.message, kind: "err" });
        }
      });
      setMsg({ text: "Inspection complete.", kind: "ok" });
    } catch (err) {
      setMsg({ text: "Error: " + (err as Error).message, kind: "err" });
    } finally {
      setRunning(false);
    }
  }

  async function review(decision: "approve" | "dismiss") {
    if (!result) return;
    try {
      const data = await approve(result.id, decision, token);
      setStatus(data.status);
      setReviewMsg({ text: "Status: " + data.status, kind: "ok" });
    } catch (err) {
      setReviewMsg({ text: "Error: " + (err as Error).message, kind: "err" });
    }
  }

  const fileField = "block w-full rounded-lg border border-dashed border-slate-300 bg-slate-50 p-2 text-xs text-slate-600 file:mr-2 file:rounded file:border-0 file:bg-slate-200 file:px-2 file:py-1 file:text-slate-700";
  const label = "mb-1 block text-xs font-semibold text-slate-500";

  return (
    <div className="flex h-full flex-col gap-5 overflow-auto">
      {/* uploads */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Inspect a before / after pair</h2>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <span className={label}>Before</span>
            <input ref={beforeRef} type="file" accept="image/*" className={fileField} />
          </div>
          <div>
            <span className={label}>After</span>
            <input ref={afterRef} type="file" accept="image/*" className={fileField} />
          </div>
        </div>
        <div className="mt-3">
          <span className={label}>Alternate after date (optional)</span>
          <input ref={altRef} type="file" accept="image/*" className={fileField} />
        </div>
        <button
          onClick={run}
          disabled={running}
          className="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
        >
          {running ? "Running…" : "Run inspection"}
        </button>
        {msg.text && (
          <p className={`mt-2 text-xs ${msg.kind === "err" ? "text-rose-600" : msg.kind === "ok" ? "text-emerald-600" : "text-slate-500"}`}>
            {msg.text}
          </p>
        )}
      </section>

      {/* streamed agent activity */}
      {events.length > 0 && (
        <section>
          <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-700">
            Agent activity
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700">streaming</span>
          </h2>
          <div className="max-h-44 overflow-auto rounded-lg border border-slate-200 bg-white p-2">
            {events.map((s) => (
              <div key={s.step} className="border-l-2 border-slate-200 py-1 pl-2 text-xs">
                <b className="text-slate-900">{s.tool}</b>{" "}
                <span className="text-slate-600">{s.decision}</span>
                <div className="font-mono text-[10px] text-slate-400">{JSON.stringify(s.metric)}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* result */}
      {result && (
        <section>
          <h2 className="mb-2 text-sm font-semibold text-slate-700">Inspection {result.id}</h2>
          <div className="flex items-center justify-between">
            <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${STATUS_STYLE[status] ?? "bg-slate-100 text-slate-700 ring-slate-200"}`}>
              {status.replace(/_/g, " ")}
            </span>
            <span className="font-mono text-xs text-slate-500">
              score {Number(result.change_score).toFixed(3)}
            </span>
          </div>

          <div className="mt-3">
            <div className="flex items-center justify-between text-xs text-slate-500">
              <span>Disturbed surface</span>
              <span className="font-mono">{result.disturbed_surface}</span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-200">
              <div className="h-full bg-amber-400" style={{ width: `${Math.round((result.disturbed_surface || 0) * 100)}%` }} />
            </div>
          </div>

          {result.display && <p className="mt-2 text-xs text-slate-500">{result.display}</p>}

          {result.blobs.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-xs font-semibold text-slate-500">Detections ({result.blobs.length})</p>
              {result.blobs.map((b, i) => (
                <button
                  key={i}
                  onClick={onDetectionFocus}
                  className="mb-1.5 block w-full rounded-lg border border-slate-200 p-2 text-left text-xs hover:border-amber-400"
                >
                  <b className="text-amber-600">#{i + 1}</b> area ≈ {b.area}px² · disturbed-surface {b.disturbed_surface}
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full bg-amber-400" style={{ width: `${Math.round((b.disturbed_surface || 0) * 100)}%` }} />
                  </div>
                </button>
              ))}
            </div>
          )}

          <details className="mt-3">
            <summary className="cursor-pointer text-xs font-semibold text-slate-500">Agent trace ({result.trace.length} steps)</summary>
            <div className="mt-2">
              {result.trace.map((s) => (
                <div key={s.step} className="border-l-2 border-slate-200 py-1 pl-2 text-xs">
                  <b className="text-amber-600">{s.tool}</b>{" "}
                  <span className="text-slate-600">{s.decision}</span>
                </div>
              ))}
            </div>
          </details>

          {reviewable && (
            <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p className="mb-1 text-xs font-semibold text-slate-500">Human review</p>
              <input
                type="text"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="reviewer token"
                className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-xs"
              />
              <div className="mt-2 flex gap-2">
                <button onClick={() => review("approve")} className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800">
                  Approve
                </button>
                <button onClick={() => review("dismiss")} className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100">
                  Dismiss
                </button>
              </div>
              {reviewMsg.text && (
                <p className={`mt-2 text-xs ${reviewMsg.kind === "err" ? "text-rose-600" : "text-emerald-600"}`}>
                  {reviewMsg.text}
                </p>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
