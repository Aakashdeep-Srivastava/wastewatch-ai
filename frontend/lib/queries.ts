import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  geocode,
  listAlerts,
  review,
  searchScenes,
  streamSceneInspect,
  type SceneInspectBody,
} from "@/lib/api";
import { useJourney } from "@/lib/store";
import type { Bbox } from "@/lib/types";

// Query keys in one place so invalidation never drifts from the query.
export const qk = {
  alerts: ["alerts"] as const,
};

// ----- request/response server state (TanStack Query) ------------------------

/** Keyless place search — triggered on form submit, so it is a mutation. */
export function useGeocode() {
  return useMutation({ mutationFn: (q: string) => geocode(q) });
}

/** Sentinel-2 scene search — triggered on click, so it is a mutation. */
export function useScenes() {
  return useMutation({
    mutationFn: (v: { bbox: Bbox; start: string; end: string; maxCloud: number }) =>
      searchScenes(v.bbox, v.start, v.end, v.maxCloud),
  });
}

/** The dashboard inspection list (cached, auto-refetched). */
export function useAlerts() {
  return useQuery({ queryKey: qk.alerts, queryFn: listAlerts });
}

/** Human review decision. Invalidates the alerts list on success so the
 *  dashboard reflects the new state without a manual reload. */
export function useReview() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (v: {
      id: string;
      decision: "approve" | "dismiss" | "needs_info";
      token: string;
      comment?: string;
    }) => review(v.id, v.decision, v.token, v.comment),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.alerts }),
  });
}

// ----- the inspection run (SSE stream — NOT a TanStack query) ----------------
// TanStack Query models request/response, not streams. The agent streams its
// perceive->decide->act steps over SSE, so we drive it imperatively and write
// each event into the Zustand journey store. On completion we invalidate the
// alerts cache so the dashboard picks up the new inspection.
export function useRunInspection() {
  const client = useQueryClient();

  async function run(body: SceneInspectBody) {
    const { startRun, appendStep, setResult, setError, finishRun } =
      useJourney.getState();
    startRun();
    try {
      await streamSceneInspect(body, (ev) => {
        if (ev.type === "step") {
          appendStep({
            step: ev.step,
            tool: ev.tool,
            metric: ev.metric,
            decision: ev.decision,
            t: ev.t,
          });
        } else if (ev.type === "result") {
          setResult(ev.record);
          client.invalidateQueries({ queryKey: qk.alerts });
        } else if (ev.type === "error") {
          setError(ev.message);
        }
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      finishRun();
    }
  }

  return { run };
}
