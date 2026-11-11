import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { FacilityMapPoint } from "@/api/types";
import { humanize } from "@/lib/formatters";

const ETH_CENTER: [number, number] = [9.0, 38.7];

function pinIcon(color = "#0d7d74", selected = false) {
  const size = selected ? 22 : 16;
  return L.divIcon({
    className: "mb-pin",
    html: `<span style="
      display:block;width:${size}px;height:${size}px;border-radius:50% 50% 50% 0;
      transform:rotate(-45deg);background:${color};
      border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.35);
    "></span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size],
    popupAnchor: [0, -size],
  });
}

export function FacilityMap({
  points,
  onSelect,
  selectedId,
  height = 460,
}: {
  points: FacilityMapPoint[];
  onSelect?: (id: number) => void;
  selectedId?: number | null;
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: ETH_CENTER,
      zoom: 6,
      scrollWheelZoom: true,
    });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19,
    }).addTo(map);
    layerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      layerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!map || !layer) return;
    layer.clearLayers();
    const valid = points.filter((p) => p.latitude && p.longitude);
    const bounds: [number, number][] = [];
    for (const p of valid) {
      const lat = parseFloat(p.latitude);
      const lng = parseFloat(p.longitude);
      if (isNaN(lat) || isNaN(lng)) continue;
      bounds.push([lat, lng]);
      const marker = L.marker([lat, lng], {
        icon: pinIcon(p.id === selectedId ? "#dd403a" : "#0d7d74", p.id === selectedId),
      });
      marker.bindPopup(
        `<div style="font-family:Inter,sans-serif;min-width:150px">
          <strong style="font-size:13px">${escapeHtml(p.name)}</strong><br/>
          <span style="color:#5d6d6b;font-size:12px">${humanize(p.facility_type)} · ${escapeHtml(p.region)}</span>
        </div>`,
      );
      if (onSelect) marker.on("click", () => onSelect(p.id));
      marker.addTo(layer);
    }
    if (bounds.length > 0) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 12 });
    } else {
      map.setView(ETH_CENTER, 6);
    }
  }, [points, selectedId, onSelect]);

  return <div ref={containerRef} className="map-container" style={{ height }} />;
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string),
  );
}

export function LocationPicker({
  latitude,
  longitude,
  onChange,
}: {
  latitude: string;
  longitude: string;
  onChange: (lat: string, lng: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const lat = parseFloat(latitude) || ETH_CENTER[0];
    const lng = parseFloat(longitude) || ETH_CENTER[1];
    const map = L.map(containerRef.current, { center: [lat, lng], zoom: 12 });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 19,
    }).addTo(map);
    if (latitude && longitude) {
      markerRef.current = L.marker([lat, lng], { icon: pinIcon("#dd403a", true), draggable: true }).addTo(map);
      markerRef.current.on("dragend", () => {
        const pos = markerRef.current!.getLatLng();
        onChangeRef.current(pos.lat.toFixed(6), pos.lng.toFixed(6));
      });
    }
    map.on("click", (e: L.LeafletMouseEvent) => {
      const { lat: la, lng: ln } = e.latlng;
      if (markerRef.current) markerRef.current.setLatLng([la, ln]);
      else {
        markerRef.current = L.marker([la, ln], { icon: pinIcon("#dd403a", true), draggable: true }).addTo(map);
        markerRef.current.on("dragend", () => {
          const pos = markerRef.current!.getLatLng();
          onChangeRef.current(pos.lat.toFixed(6), pos.lng.toFixed(6));
        });
      }
      onChangeRef.current(la.toFixed(6), ln.toFixed(6));
    });
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      markerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div ref={containerRef} className="map-pin-picker" />;
}