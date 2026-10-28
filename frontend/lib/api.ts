import type {
  AlertSummary,
  Bbox,
  GeocodeResult,
  Scene,
  StreamEvent,
} from "./types";

// Artifact paths come back from FastAPI as "/out/..."; route through the proxy.
export function artifactUrl(path: string): string {
  return "/api" + path;
}

async function readSSE(
  resp: Response,
  onEvent: (e: StreamEvent) => void,
): Promise<void> {
  if (!resp.ok) {
    const d = await resp.json().catch(() => ({}));
    throw new Error((d as { detail?: string }).detail ?? "request failed");
  }
  if (!resp.body) throw new Error("streaming not supported by this browser");
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const line = chunk.split("\n").find((l) => l.startsWith("data:"));
      if (line) onEvent(JSON.parse(line.slice(5).trim()) as StreamEvent);
    }
  }
}

export async function geocode(q: string): Promise<GeocodeResult[]> {
  const r = await fetch("/api/geocode?q=" + encodeURIComponent(q));
  if (!r.ok) throw new Error("geocoding failed");
  return (await r.json()).results as GeocodeResult[];
}

export async function searchScenes(
  bbox: Bbox,
  start: string,
  end: string,
  maxCloud: number,
): Promise<Scene[]> {
  const qs = new URLSearchParams({
    bbox: bbox.join(","),
    start,
    end,
    max_cloud: String(maxCloud),
  });
  const r = await fetch("/api/scenes?" + qs.toString());
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(d.detail ?? "scene search failed");
  }
  return (await r.json()).scenes as Scene[];
}

export interface SceneInspectBody {
  aoi: Bbox;
  t1_visual: string;
  t2_visual: string;
  alt_visual?: string | null;
  location?: string | null;
  area_km2?: number | null;
  t1_date?: string;
  t2_date?: string;
}

export async function streamSceneInspect(
  body: SceneInspectBody,
  onEvent: (e: StreamEvent) => void,
): Promise<void> {
  const resp = await fetch("/api/inspect/scene/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await readSSE(resp, onEvent);
}

// Manual upload path (kept as a fallback when imagery fetch is unavailable).
export async function streamUploadInspect(
  inputs: { before: File; after: File; altAfter?: File | null; aoi?: Bbox | null; location?: string | null; areaKm2?: number | null },
  onEvent: (e: StreamEvent) => void,
): Promise<void> {
  const fd = new FormData();
  fd.append("before", inputs.before);
  fd.append("after", inputs.after);
  if (inputs.altAfter) fd.append("alt_after", inputs.altAfter);
  if (inputs.aoi) fd.append("aoi", JSON.stringify(inputs.aoi));
  if (inputs.location) fd.append("location", inputs.location);
  if (inputs.areaKm2 != null) fd.append("area_km2", String(inputs.areaKm2));
  const resp = await fetch("/api/inspect/stream", { method: "POST", body: fd });
  await readSSE(resp, onEvent);
}

export async function listAlerts(): Promise<AlertSummary[]> {
  const r = await fetch("/api/alerts");
  if (!r.ok) throw new Error("failed to load inspections");
  return (await r.json()).alerts as AlertSummary[];
}

export async function review(
  id: string,
  decision: "approve" | "dismiss" | "needs_info",
  token: string,
  comment?: string,
): Promise<{ ok: boolean; status: string; reason: string }> {
  const fd = new FormData();
  fd.append("decision", decision);
  if (comment) fd.append("comment", comment);
  const resp = await fetch(`/api/approve/${id}`, {
    method: "POST",
    body: fd,
    headers: { "x-reviewer-token": token },
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.detail ?? "review failed");
  return data;
}
