"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import maplibregl from "maplibre-gl";
import type { Bbox, Blob, InspectResult } from "@/lib/types";

const SENTINEL =
  "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/GoogleMapsCompatible/{z}/{y}/{x}.jpg";
const EARTH =
  "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_NextGeneration/default/2004-01-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg";

export type Selection = { bbox: Bbox; polygon: [number, number][] };

export interface GlobeHandle {
  flyToBbox: (b: Bbox) => void;
  flyTo: (lng: number, lat: number, zoom?: number) => void;
}

interface Props {
  selection: Selection | null;
  result: InspectResult | null;
  onSelect: (sel: Selection | null) => void;
}

type DrawMode = "none" | "rect" | "poly";

function emptyFC(): GeoJSON.FeatureCollection {
  return { type: "FeatureCollection", features: [] };
}
function ringFC(ring: [number, number][]): GeoJSON.FeatureCollection {
  const closed = ring.length && ring[0] !== ring[ring.length - 1] ? [...ring, ring[0]] : ring;
  return {
    type: "FeatureCollection",
    features: [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [closed] } }],
  };
}
function pointsFC(pts: [number, number][]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: pts.map((p) => ({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: p } })),
  };
}
function rectRing(a: maplibregl.LngLat, b: maplibregl.LngLat): [number, number][] {
  return [[a.lng, a.lat], [b.lng, a.lat], [b.lng, b.lat], [a.lng, b.lat]];
}
function bboxOf(ring: [number, number][]): Bbox {
  const xs = ring.map((p) => p[0]);
  const ys = ring.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}
function blobFeature(blob: Blob, box: Bbox, size: { w: number; h: number }): GeoJSON.Feature {
  const [w, s, e, n] = box;
  const x1 = w + (blob.x / size.w) * (e - w);
  const x2 = w + ((blob.x + blob.w) / size.w) * (e - w);
  const yTop = n - (blob.y / size.h) * (n - s);
  const yBot = n - ((blob.y + blob.h) / size.h) * (n - s);
  return {
    type: "Feature",
    properties: { ds: blob.disturbed_surface ?? 0, area: blob.area ?? 0 },
    geometry: { type: "Polygon", coordinates: [[[x1, yTop], [x2, yTop], [x2, yBot], [x1, yBot], [x1, yTop]]] },
  };
}

const Globe = forwardRef<GlobeHandle, Props>(function Globe(
  { selection, result, onSelect },
  ref,
) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const ready = useRef(false);
  const [mode, setMode] = useState<DrawMode>("none");

  const modeRef = useRef(mode);
  const onSelectRef = useRef(onSelect);
  const selectionRef = useRef(selection);
  const polyPts = useRef<[number, number][]>([]);
  useEffect(() => void (modeRef.current = mode), [mode]);
  useEffect(() => void (onSelectRef.current = onSelect), [onSelect]);
  useEffect(() => void (selectionRef.current = selection), [selection]);

  useImperativeHandle(ref, () => ({
    flyToBbox(b: Bbox) {
      mapRef.current?.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 60, maxZoom: 12, duration: 900 });
    },
    flyTo(lng, lat, zoom = 10) {
      mapRef.current?.flyTo({ center: [lng, lat], zoom, essential: true });
    },
  }));

  useEffect(() => {
    if (!container.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      center: [72, 18],
      zoom: 1.4,
      minZoom: 0,
      maxZoom: 14,
      attributionControl: { compact: true },
      style: {
        version: 8,
        sources: {
          sentinel: { type: "raster", tiles: [SENTINEL], tileSize: 256, maxzoom: 14,
            attribution: "Sentinel-2 cloudless 2016 © EOX (CC BY 4.0), modified Copernicus Sentinel data" },
          earth: { type: "raster", tiles: [EARTH], tileSize: 256, maxzoom: 8, attribution: "NASA EOSDIS GIBS" },
        },
        layers: [
          { id: "sentinel", type: "raster", source: "sentinel" },
          { id: "earth", type: "raster", source: "earth",
            paint: { "raster-opacity": ["interpolate", ["linear"], ["zoom"], 1, 1, 3, 0.6, 5, 0] } },
        ],
      },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");

    map.on("load", () => {
      try { map.setProjection({ type: "globe" }); } catch { /* flat fallback */ }
      map.resize(); // ensure canvas matches the (now laid-out) container
      map.addSource("sel", { type: "geojson", data: emptyFC() });
      map.addLayer({ id: "sel-fill", type: "fill", source: "sel", paint: { "fill-color": "#2563eb", "fill-opacity": 0.1 } });
      map.addLayer({ id: "sel-line", type: "line", source: "sel", paint: { "line-color": "#2563eb", "line-width": 2 } });
      map.addSource("draw", { type: "geojson", data: emptyFC() });
      map.addLayer({ id: "draw-line", type: "line", source: "draw", paint: { "line-color": "#f0b429", "line-width": 2, "line-dasharray": [2, 1] } });
      map.addSource("draw-pts", { type: "geojson", data: emptyFC() });
      map.addLayer({ id: "draw-pts", type: "circle", source: "draw-pts", paint: { "circle-radius": 4, "circle-color": "#f0b429" } });
      map.addSource("detections", { type: "geojson", data: emptyFC() });
      map.addLayer({ id: "det-fill", type: "fill", source: "detections",
        paint: { "fill-color": ["interpolate", ["linear"], ["get", "ds"], 0, "#2fbf71", 0.55, "#f0b429", 0.75, "#e5484d"], "fill-opacity": 0.28 } });
      map.addLayer({ id: "det-line", type: "line", source: "detections",
        paint: { "line-color": ["interpolate", ["linear"], ["get", "ds"], 0, "#2fbf71", 0.55, "#f0b429", 0.75, "#e5484d"], "line-width": 2 } });
      ready.current = true;
      syncSelection();
      syncDetections();
    });

    map.on("click", "det-fill", (e) => {
      const p = e.features?.[0]?.properties ?? {};
      new maplibregl.Popup().setLngLat(e.lngLat)
        .setHTML(`<b>Detection</b><br>area ≈ ${p.area}px²<br>disturbed-surface ${p.ds}`).addTo(map);
    });

    // rectangle drag
    let rectStart: maplibregl.LngLat | null = null;
    let dragging = false;
    map.on("mousedown", (e) => {
      if (modeRef.current !== "rect") return;
      dragging = true; rectStart = e.lngLat; map.dragPan.disable();
    });
    map.on("mousemove", (e) => {
      if (modeRef.current !== "rect" || !dragging || !rectStart) return;
      (map.getSource("draw") as maplibregl.GeoJSONSource)?.setData(ringFC(rectRing(rectStart, e.lngLat)));
    });
    map.on("mouseup", (e) => {
      if (modeRef.current !== "rect" || !dragging || !rectStart) return;
      dragging = false; map.dragPan.enable();
      const ring = rectRing(rectStart, e.lngLat);
      rectStart = null;
      (map.getSource("draw") as maplibregl.GeoJSONSource)?.setData(emptyFC());
      setMode("none"); map.getCanvas().style.cursor = "";
      onSelectRef.current({ bbox: bboxOf(ring), polygon: ring });
    });

    // polygon clicks
    map.on("click", (e) => {
      if (modeRef.current !== "poly") return;
      polyPts.current = [...polyPts.current, [e.lngLat.lng, e.lngLat.lat]];
      (map.getSource("draw") as maplibregl.GeoJSONSource)?.setData(ringFC(polyPts.current));
      (map.getSource("draw-pts") as maplibregl.GeoJSONSource)?.setData(pointsFC(polyPts.current));
    });

    return () => { map.remove(); mapRef.current = null; ready.current = false; };
  }, []);

  function syncSelection() {
    const map = mapRef.current;
    if (!map || !ready.current) return;
    const sel = selectionRef.current;
    (map.getSource("sel") as maplibregl.GeoJSONSource | undefined)?.setData(
      sel ? ringFC(sel.polygon) : emptyFC(),
    );
  }
  function syncDetections() {
    const map = mapRef.current;
    if (!map || !ready.current) return;
    const src = map.getSource("detections") as maplibregl.GeoJSONSource | undefined;
    const box = selectionRef.current?.bbox;
    if (!src) return;
    if (!box || !result || !result.image_size || !(result.blobs || []).length) {
      src.setData(emptyFC());
      return;
    }
    src.setData({ type: "FeatureCollection", features: result.blobs.map((b) => blobFeature(b, box, result.image_size)) });
    map.fitBounds([[box[0], box[1]], [box[2], box[3]]], { padding: 60, maxZoom: 13, duration: 900 });
  }
  useEffect(syncSelection, [selection]);
  useEffect(syncDetections, [selection, result]);

  function finishPolygon() {
    if (polyPts.current.length < 3) return;
    const ring = polyPts.current.slice();
    polyPts.current = [];
    const map = mapRef.current;
    (map?.getSource("draw") as maplibregl.GeoJSONSource)?.setData(emptyFC());
    (map?.getSource("draw-pts") as maplibregl.GeoJSONSource)?.setData(emptyFC());
    setMode("none");
    if (map) map.getCanvas().style.cursor = "";
    onSelectRef.current({ bbox: bboxOf(ring), polygon: ring });
  }
  function clearAll() {
    polyPts.current = [];
    const map = mapRef.current;
    (map?.getSource("draw") as maplibregl.GeoJSONSource)?.setData(emptyFC());
    (map?.getSource("draw-pts") as maplibregl.GeoJSONSource)?.setData(emptyFC());
    setMode("none");
    if (map) map.getCanvas().style.cursor = "";
    onSelect(null);
  }
  function startMode(m: DrawMode) {
    polyPts.current = [];
    (mapRef.current?.getSource("draw") as maplibregl.GeoJSONSource)?.setData(emptyFC());
    (mapRef.current?.getSource("draw-pts") as maplibregl.GeoJSONSource)?.setData(emptyFC());
    setMode(m);
    if (mapRef.current) mapRef.current.getCanvas().style.cursor = m === "none" ? "" : "crosshair";
  }
  function useView() {
    const b = mapRef.current?.getBounds();
    if (!b) return;
    const ring: [number, number][] = [
      [b.getWest(), b.getSouth()], [b.getEast(), b.getSouth()],
      [b.getEast(), b.getNorth()], [b.getWest(), b.getNorth()],
    ];
    onSelect({ bbox: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], polygon: ring });
  }

  const btn = "rounded-lg border border-white/20 bg-slate-900/70 px-3 py-1.5 text-xs font-semibold text-slate-100 backdrop-blur hover:bg-slate-800/80";
  const on = "border-amber-400 text-amber-300";

  return (
    <div className="absolute inset-0 overflow-hidden rounded-2xl bg-[#020914]">
      {/* MapLibre forces the container to position:relative, so it must size via
          height:100% (not inset-0) against this definite-height parent. */}
      <div ref={container} className="h-full w-full" />
      <div className="pointer-events-none absolute inset-0">
        <div className="pointer-events-auto absolute left-4 top-4 flex flex-wrap gap-2">
          <button className={`${btn} border-amber-400 bg-amber-400 text-slate-900 hover:bg-amber-300`} onClick={() => mapRef.current?.flyTo({ center: [73.95, 15.5], zoom: 10, speed: 0.7, essential: true })}>Fly to Goa</button>
          <button className={btn} onClick={() => mapRef.current?.flyTo({ center: [70, 18], zoom: 1.4, speed: 0.7, essential: true })}>View Earth</button>
          <button className={`${btn} ${mode === "rect" ? on : ""}`} onClick={() => startMode(mode === "rect" ? "none" : "rect")}>▭ Rectangle</button>
          <button className={`${btn} ${mode === "poly" ? on : ""}`} onClick={() => startMode(mode === "poly" ? "none" : "poly")}>⬠ Polygon</button>
          <button className={btn} onClick={useView}>Use view</button>
          <button className={btn} onClick={clearAll}>Clear</button>
          {mode === "poly" && (
            <button className={`${btn} border-emerald-400 text-emerald-300`} onClick={finishPolygon}>Finish ({polyPts.current.length})</button>
          )}
        </div>
        {mode !== "none" && (
          <div className="pointer-events-none absolute left-1/2 top-4 -translate-x-1/2 rounded-full bg-slate-900/80 px-3 py-1 text-xs text-amber-200 backdrop-blur">
            {mode === "rect" ? "Drag a rectangle on the map" : "Click to add polygon points, then Finish"}
          </div>
        )}
        <div className="absolute bottom-6 left-4 max-w-sm rounded-lg border border-white/15 bg-slate-900/80 p-3 text-[11px] leading-relaxed text-slate-300 backdrop-blur">
          Basemaps (NASA / EOX) are fixed historical composites — navigation and
          context only. The inspection runs on <b className="text-slate-100">real Sentinel-2</b> scenes
          fetched for your AOI and chosen dates.
        </div>
      </div>
    </div>
  );
});

export default Globe;
