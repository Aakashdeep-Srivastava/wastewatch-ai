"use client";

import { useState } from "react";
import Link from "next/link";
import Header from "@/components/Header";
import { useAlerts } from "@/lib/queries";

const LABEL: Record<string, { text: string; cls: string }> = {
  PENDING_REVIEW: { text: "Pending Review", cls: "bg-amber-100 text-amber-800" },
  NEEDS_REVIEW: { text: "Pending Review", cls: "bg-amber-100 text-amber-800" },
  NEEDS_MORE_INFO: { text: "Needs Info", cls: "bg-blue-100 text-blue-800" },
  CONFIRMED: { text: "Completed", cls: "bg-emerald-100 text-emerald-700" },
  NO_SIGNIFICANT_CHANGE: { text: "No Change", cls: "bg-emerald-100 text-emerald-700" },
  DISMISSED: { text: "Dismissed", cls: "bg-slate-200 text-slate-600" },
};

const FILTERS = ["All", "Pending", "Completed", "Dismissed", "Needs Info"] as const;
type Filter = (typeof FILTERS)[number];

function matches(f: Filter, status: string): boolean {
  if (f === "All") return true;
  if (f === "Pending") return status === "PENDING_REVIEW" || status === "NEEDS_REVIEW";
  if (f === "Completed") return status === "CONFIRMED" || status === "NO_SIGNIFICANT_CHANGE";
  if (f === "Dismissed") return status === "DISMISSED";
  if (f === "Needs Info") return status === "NEEDS_MORE_INFO";
  return true;
}

function fmtDate(ts: number | null): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toISOString().slice(0, 10);
}

export default function Dashboard() {
  const [filter, setFilter] = useState<Filter>("All");
  const { data: alerts = [], isLoading, isError, error } = useAlerts();

  const rows = alerts.filter((a) => matches(filter, a.status));

  return (
    <div className="flex h-screen flex-col">
      <Header active="dashboard" />
      <main className="min-h-0 flex-1 overflow-auto p-6">
        <div className="mx-auto max-w-5xl">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-slate-800">Inspection Dashboard</h2>
              <p className="text-xs text-slate-500">All inspections, status and history.</p>
            </div>
            <Link href="/" className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800">
              + New Inspection
            </Link>
          </div>

          <div className="mb-3 flex flex-wrap gap-2">
            {FILTERS.map((f) => (
              <button key={f} onClick={() => setFilter(f)}
                className={`rounded-full px-3 py-1 text-xs font-semibold ${filter === f ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>
                {f}
              </button>
            ))}
          </div>

          {isLoading ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : isError ? (
            <p className="text-sm text-rose-600">Error: {(error as Error).message}</p>
          ) : rows.length === 0 ? (
            <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
              No inspections yet. <Link href="/" className="font-semibold text-blue-600">Start one →</Link>
            </p>
          ) : (
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs text-slate-500">
                  <tr>
                    <th className="px-4 py-2 font-semibold">ID</th>
                    <th className="px-4 py-2 font-semibold">Location</th>
                    <th className="px-4 py-2 font-semibold">Dates</th>
                    <th className="px-4 py-2 font-semibold">Status</th>
                    <th className="px-4 py-2 text-right font-semibold">Regions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rows.map((a) => {
                    const lab = LABEL[a.status] ?? { text: a.status, cls: "bg-slate-100 text-slate-600" };
                    return (
                      <tr key={a.id} className="hover:bg-slate-50">
                        <td className="px-4 py-2 font-mono text-xs text-slate-500">#{a.id}</td>
                        <td className="px-4 py-2 text-slate-700">{a.location ?? "—"}</td>
                        <td className="px-4 py-2 font-mono text-xs text-slate-500">
                          {a.dates?.t1 && a.dates?.t2 ? `${a.dates.t1} → ${a.dates.t2}` : fmtDate(a.created)}
                        </td>
                        <td className="px-4 py-2">
                          <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${lab.cls}`}>{lab.text}</span>
                        </td>
                        <td className="px-4 py-2 text-right font-semibold text-slate-700">{a.num_regions}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
