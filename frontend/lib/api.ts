import type { Bbox, StreamEvent } from "./types";

// Artifact paths come back from FastAPI as "/out/..."; route them through the proxy.
export function artifactUrl(path: string): string {
  return "/api" + path;
}

export interface InspectInputs {
  before: File;
  after: File;
  altAfter?: File | null;
  aoi?: Bbox | null;
}

function toFormData({ before, after, altAfter, aoi }: InspectInputs): FormData {
  const fd = new FormData();
  fd.append("before", before);
  fd.append("after", after);
  if (altAfter) fd.append("alt_after", altAfter);
  if (aoi) fd.append("aoi", JSON.stringify(aoi));
  return fd;
}

// Stream the agent's perceive->decide->act steps live (SSE over POST).
export async function streamInspect(
  inputs: InspectInputs,
  onEvent: (e: StreamEvent) => void,
): Promise<void> {
  const resp = await fetch("/api/inspect/stream", {
    method: "POST",
    body: toFormData(inputs),
  });
  if (!resp.ok) {
    const d = await resp.json().catch(() => ({}));
    throw new Error((d as { detail?: string }).detail ?? "inspection failed");
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

export async function approve(
  id: string,
  decision: "approve" | "dismiss",
  token: string,
): Promise<{ ok: boolean; status: string; reason: string }> {
  const fd = new FormData();
  fd.append("decision", decision);
  const resp = await fetch(`/api/approve/${id}`, {
    method: "POST",
    body: fd,
    headers: { "x-reviewer-token": token },
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.detail ?? "review failed");
  return data;
}
