"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import maplibregl from "maplibre-gl";
import type { Bbox, InspectResult, Blob } from "@/lib/types";

const SENTINEL =
  "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/GoogleMapsCompatible/{z}/{y}/{x}.jpg";
const EARTH =
  "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_NextGeneration/default/2004-01-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg";

export interface GlobeHandle {
  flyToAOI: () => void;
}

interface Props {
  aoi: Bbox | null;
  result: InspectResult | null;
  onAOI: (b: Bbox | null) => void;
}

function emptyFC(): GeoJSON.FeatureCollection {
  return { type: "FeatureCollection", features: [] };
}

function bboxPolygon(b: Bbox): GeoJSON.FeatureCollection {
  const [w, s, e, n] = b;
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {},
        geometry: {
          type: "Polygon",
          coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
        },
      },
    ],
  };
}

// pixel -> geo (assumes the pair covers the AOI, north-up, no rotation)
function blobFeature(
  blob: Blob,
  box: Bbox,
  size: { w: number; h: number },
): GeoJSON.Feature {
  const [w, s, e, n] = box;
  const x1 = w + (blob.x / size.w) * (e - w);
  const x2 = w + ((blob.x + blob.w) / size.w) * (e - w);
  const yTop = n - (blob.y / size.h) * (n - s);
  const yBot = n - ((blob.y + blob.h) / size.h) * (n - s);
  return {
    type: "Feature",
    properties: { ds: blob.disturbed_surface ?? 0, area: blob.area ?? 0 },
    geometry: {
      type: "Polygon",
      coordinates: [[[x1, yTop], [x2, yTop], [x2, yBot], [x1, yBot], [x1, yTop]]],
    },
  };
}

const Globe = forwardRef<GlobeHandle, Props>(function Globe(
  { aoi, result, onAOI },
  ref,
) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const ready = useRef(false);
  const [drawing, setDrawing] = useState(false);

  // refs mirror latest values for use inside stable map event handlers
  const drawingRef = useRef(drawing);
  const onAOIRef = useRef(onAOI);
  const aoiRef = useRef(aoi);
  useEffect(() => void (drawingRef.current = drawing), [drawing]);
  useEffect(() => void (onAOIRef.current = onAOI), [onAOI]);
  useEffect(() => void (aoiRef.current = aoi), [aoi]);

  useImperativeHandle(ref, () => ({
    flyToAOI() {
      const b = aoiRef.current;
      const m = mapRef.current;
      if (b && m) {
        m.flyTo({
          center: [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2],
          zoom: 11,
          essential: true,
        });
      }
    },
  }));

  // init map once
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
          sentinel: {
            type: "raster",
            tiles: [SENTINEL],
            tileSize: 256,
            maxzoom: 14,
            attribution:
              "Sentinel-2 cloudless 2016 © EOX (CC BY 4.0), modified Copernicus Sentinel data",
          },
          earth: {
            type: "raster",
            tiles: [EARTH],
            tileSize: 256,
            maxzoom: 8,
            attribution: "NASA EOSDIS GIBS",
          },
        },
        layers: [
          { id: "sentinel", type: "raster", source: "sentinel" },
          {
            id: "earth",
            type: "raster",
            source: "earth",
            paint: {
              "raster-opacity": [
                "interpolate",
                ["linear"],
                ["zoom"],
                1, 1, 3, 0.6, 5, 0,
              ],
            },
          },
        ],
      },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");

    map.on("load", () => {
      try {
        map.setProjection({ type: "globe" });
      } catch {
        /* older maplibre: stays flat */
      }
      map.addSource("aoi", { type: "geojson", data: emptyFC() });
      map.addLayer({
        id: "aoi-fill",
        type: "fill",
        source: "aoi",
        paint: { "fill-color": "#f0b429", "fill-opacity": 0.08 },
      });
      map.addLayer({
        id: "aoi-line",
        type: "line",
        source: "aoi",
        paint: { "line-color": "#f0b429", "line-width": 2, "line-dasharray": [2, 1] },
      });
      map.addSource("detections", { type: "geojson", data: emptyFC() });
      map.addLayer({
        id: "det-fill",
        type: "fill",
        source: "detections",
        paint: {
          "fill-color": [
            "interpolate", ["linear"], ["get", "ds"],
            0, "#2fbf71", 0.55, "#f0b429", 0.75, "#e5484d",
          ],
          "fill-opacity": 0.25,
        },
      });
      map.addLayer({
        id: "det-line",
        type: "line",
        source: "detections",
        paint: {
          "line-color": [
            "interpolate", ["linear"], ["get", "ds"],
            0, "#2fbf71", 0.55, "#f0b429", 0.75, "#e5484d",
          ],
          "line-width": 2,
        },
      });
      ready.current = true;
      syncAOI();
      syncDetections();
    });

    map.on("click", "det-fill", (e) => {
      const p = e.features?.[0]?.properties ?? {};
      new maplibregl.Popup()
        .setLngLat(e.lngLat)
        .setHTML(
          `<b>Detection</b><br>area ≈ ${p.area}px²<br>disturbed-surface ${p.ds}`,
        )
        .addTo(map);
    });
    map.on("mouseenter", "det-fill", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "det-fill", () => (map.getCanvas().style.cursor = ""));

    // rectangle drawing
    let start: maplibregl.LngLat | null = null;
    let dragging = false;
    map.on("mousedown", (e) => {
      if (!drawingRef.current) return;
      dragging = true;
      start = e.lngLat;
      map.dragPan.disable();
    });
    map.on("mousemove", (e) => {
      if (!drawingRef.current || !dragging || !start) return;
      (map.getSource("aoi") as maplibregl.GeoJSONSource)?.setData(
        bboxPolygon([start.lng, start.lat, e.lngLat.lng, e.lngLat.lat]),
      );
    });
    map.on("mouseup", (e) => {
      if (!drawingRef.current || !dragging || !start) return;
      dragging = false;
      map.dragPan.enable();
      const raw: Bbox = [start.lng, start.lat, e.lngLat.lng, e.lngLat.lat];
      const norm: Bbox = [
        Math.min(raw[0], raw[2]), Math.min(raw[1], raw[3]),
        Math.max(raw[0], raw[2]), Math.max(raw[1], raw[3]),
      ];
      start = null;
      setDrawing(false);
      map.getCanvas().style.cursor = "";
      onAOIRef.current(norm);
    });

    return () => {
      map.remove();
      mapRef.current = null;
      ready.current = false;
    };
  }, []);

  function syncAOI() {
    const map = mapRef.current;
    if (!map || !ready.current) return;
    const src = map.getSource("aoi") as maplibregl.GeoJSONSource | undefined;
    src?.setData(aoiRef.current ? bboxPolygon(aoiRef.current) : emptyFC());
  }

  function syncDetections() {
    const map = mapRef.current;
    if (!map || !ready.current) return;
    const src = map.getSource("detections") as maplibregl.GeoJSONSource | undefined;
    if (!src) return;
    const box = aoiRef.current;
    if (!box || !result || !result.image_size || !(result.blobs || []).length) {
      src.setData(emptyFC());
      return;
    }
    src.setData({
      type: "FeatureCollection",
      features: result.blobs.map((b) => blobFeature(b, box, result.image_size)),
    });
    map.fitBounds([[box[0], box[1]], [box[2], box[3]]], {
      padding: 60,
      maxZoom: 13,
      duration: 900,
    });
  }

  useEffect(syncAOI, [aoi]);
  useEffect(syncDetections, [aoi, result]);

  const flyGoa = () =>
    mapRef.current?.flyTo({ center: [73.95, 15.5], zoom: 10, speed: 0.7, essential: true });
  const viewEarth = () =>
    mapRef.current?.flyTo({ center: [70, 18], zoom: 1.4, speed: 0.7, essential: true });
  const useView = () => {
    const b = mapRef.current?.getBounds();
    if (b) onAOI([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]);
  };
  const toggleDraw = () => {
    const next = !drawing;
    setDrawing(next);
    const m = mapRef.current;
    if (m) m.getCanvas().style.cursor = next ? "crosshair" : "";
  };

  const btn =
    "rounded-lg border border-white/20 bg-slate-900/70 px-3 py-1.5 text-xs font-semibold text-slate-100 backdrop-blur hover:bg-slate-800/80";
  const btnOn = "border-amber-400 text-amber-300";

  return (
    <div className="relative h-full w-full overflow-hidden rounded-2xl bg-[#020914]">
      <div ref={container} className="absolute inset-0" />
      <div className="pointer-events-none absolute inset-0">
        <div className="pointer-events-auto absolute left-4 top-4 flex flex-wrap gap-2">
          <button className={`${btn} bg-amber-400 text-slate-900 border-amber-400 hover:bg-amber-300`} onClick={flyGoa}>
            Fly to Goa
          </button>
          <button className={btn} onClick={viewEarth}>View Earth</button>
          <button className={`${btn} ${drawing ? btnOn : ""}`} onClick={toggleDraw}>
            {drawing ? "Click-drag on map…" : "Draw AOI"}
          </button>
          <button className={btn} onClick={useView}>Use current view</button>
          <button className={btn} onClick={() => onAOI(null)}>Clear</button>
        </div>
        <div className="absolute bottom-6 left-4 max-w-sm rounded-lg border border-white/15 bg-slate-900/80 p-3 text-[11px] leading-relaxed text-slate-300 backdrop-blur">
          Basemaps (NASA / EOX) are fixed historical composites — navigation and
          context only, <b className="text-slate-100">not</b> a source for temporal
          change detection. Analysis runs on the uploaded Sentinel-2 pair.
        </div>
      </div>
    </div>
  );
});

export default Globe;
