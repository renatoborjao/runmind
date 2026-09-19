"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import BottomNav from "../bottom-nav";
import {
  getActivityAnalysis,
  getFeed,
  getTrack,
  type CoachAnalysis,
  type FeedItem,
  type TrackData,
} from "@/lib/api";

// Carrega o Leaflet (mapa real, tiles do OpenStreetMap — grátis, sem chave) sob
// demanda via CDN. Resolve quando window.L está pronto.
declare global { interface Window { L?: any } }

function loadLeaflet(): Promise<any> {
  return new Promise((resolve, reject) => {
    if (window.L) return resolve(window.L);
    if (!document.getElementById("leaflet-css")) {
      const link = document.createElement("link");
      link.id = "leaflet-css";
      link.rel = "stylesheet";
      link.href = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";
      document.head.appendChild(link);
    }
    const existing = document.getElementById("leaflet-js") as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener("load", () => resolve(window.L));
      existing.addEventListener("error", () => reject(new Error("leaflet")));
      if (window.L) resolve(window.L);
      return;
    }
    const s = document.createElement("script");
    s.id = "leaflet-js";
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";
    s.onload = () => resolve(window.L);
    s.onerror = () => reject(new Error("leaflet"));
    document.head.appendChild(s);
  });
}

// Desenha o traçado (linha + início/fim) num mapa Leaflet e devolve a linha.
function _drawRoute(L: any, map: any, pts: number[][]) {
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "© OpenStreetMap",
  }).addTo(map);
  const line = L.polyline(pts, { color: "#0FB499", weight: 5 }).addTo(map);
  L.circleMarker(pts[0], { radius: 6, color: "#fff", weight: 2, fillColor: "#0FB499", fillOpacity: 1 }).addTo(map);
  L.circleMarker(pts[pts.length - 1], { radius: 6, color: "#fff", weight: 2, fillColor: "#E24666", fillOpacity: 1 }).addTo(map);
  return line;
}

// Mapa FIXO do detalhe (estilo Strava): não arrasta nem dá zoom inline — só
// mostra o percurso com a bolinha de playback. Tocar abre o mapa em tela cheia.
function MapView({ points }: { points: { lat: number; lon: number }[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const [full, setFull] = useState(false);

  useEffect(() => {
    const pts = points.filter((p) => p.lat && p.lon).map((p) => [p.lat, p.lon]);
    if (pts.length < 2 || !ref.current) return;
    let map: any;
    let anim: ReturnType<typeof setInterval> | undefined;
    let cancelled = false;
    loadLeaflet()
      .then((L: any) => {
        if (cancelled || !ref.current) return;
        map = L.map(ref.current, {
          zoomControl: false, attributionControl: true, scrollWheelZoom: false,
          dragging: false, touchZoom: false, doubleClickZoom: false,
          boxZoom: false, keyboard: false, tap: false,
        });
        const line = _drawRoute(L, map, pts);
        map.fitBounds(line.getBounds(), { padding: [22, 22] });
        setTimeout(() => map && map.invalidateSize(), 120);
        // bolinha "correndo" o percurso (playback, estilo Strava)
        const dot = L.circleMarker(pts[0], { radius: 7, color: "#fff", weight: 3, fillColor: "#0FB499", fillOpacity: 1 }).addTo(map);
        const step = Math.max(1, Math.round(pts.length / 240));
        let i = 0;
        anim = setInterval(() => { i += step; if (i >= pts.length) i = 0; dot.setLatLng(pts[i]); }, 45);
      })
      .catch(() => setFailed(true));
    return () => { cancelled = true; if (anim) clearInterval(anim); if (map) map.remove(); };
  }, [points]);

  if (failed) return <TrackMapSVG points={points} />;
  return (
    <div className="map-tap">
      <div ref={ref} className="map-box" />
      <button className="map-overlay" aria-label="Ampliar mapa" onClick={() => setFull(true)}>
        <span className="map-hint">Toque para ampliar</span>
      </button>
      {full && <FullMap points={points} onClose={() => setFull(false)} />}
    </div>
  );
}

// Mapa em TELA CHEIA (navegável): arrasta, dá zoom, botões — como o Strava
// quando você toca no mapa.
function FullMap({ points, onClose }: { points: { lat: number; lon: number }[]; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const pts = points.filter((p) => p.lat && p.lon).map((p) => [p.lat, p.lon]);
    if (pts.length < 2 || !ref.current) return;
    let map: any;
    let cancelled = false;
    loadLeaflet()
      .then((L: any) => {
        if (cancelled || !ref.current) return;
        map = L.map(ref.current, { zoomControl: true, attributionControl: true, scrollWheelZoom: true });
        const line = _drawRoute(L, map, pts);
        map.fitBounds(line.getBounds(), { padding: [30, 30] });
        setTimeout(() => map && map.invalidateSize(), 120);
      })
      .catch(() => {});
    return () => { cancelled = true; if (map) map.remove(); };
  }, [points]);
  return (
    <div className="fullmap">
      <button className="fullmap-close" aria-label="Fechar" onClick={onClose}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
      </button>
      <div ref={ref} className="fullmap-box" />
    </div>
  );
}

function Mark() {
  return (
    <span className="mark" aria-hidden>
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round"><path d="M2 12h4l2.5-7 4 15 2.5-8H22" /></svg>
    </span>
  );
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}
function fmtTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}
function km(v: number): string {
  return v.toFixed(2).replace(".", ",");
}
function fmtPaceSec(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

// Zonas de FC (Z1..Z5, por %FCmáx) — mesma leitura que o Strava mostra: quanto
// tempo o atleta passou em cada intensidade. Os valores vêm em MINUTOS.
const ZONE_META = [
  { n: "Z1", t: "Recuperação", c: "#6FCF97" },
  { n: "Z2", t: "Leve", c: "#0FB499" },
  { n: "Z3", t: "Moderado", c: "#F2C94C" },
  { n: "Z4", t: "Limiar", c: "#F2994A" },
  { n: "Z5", t: "Máximo", c: "#E24666" },
];
function HrZones({ zones }: { zones: number[] }) {
  const total = zones.reduce((a, b) => a + (b || 0), 0);
  if (total <= 0 || zones.length !== 5) return null;
  const max = Math.max(...zones, 0.01);
  return (
    <section className="card">
      <div className="card-head"><span className="eyebrow">Zonas de FC</span></div>
      <div className="hrz">
        {zones.map((z, i) => {
          const meta = ZONE_META[i];
          const pct = Math.round((z / total) * 100);
          const w = Math.max(3, Math.round((z / max) * 100));
          return (
            <div className="hrz-row" key={i}>
              <span className="hrz-tag"><b>{meta.n}</b> {meta.t}</span>
              <span className="hrz-bar"><i style={{ width: `${w}%`, background: meta.c }} /></span>
              <span className="hrz-val">{pct}%<small>{z >= 1 ? ` ${Math.round(z)} min` : " <1 min"}</small></span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// Gráfico simples (área/linha) de uma métrica ao longo da distância — a "cara
// de Strava": altimetria e FC plotadas. Só desenha os pontos com valor.
function Chart({ title, dist, values, color, area, unit, fmt }: {
  title: string;
  dist: number[];
  values: (number | null)[];
  color: string;
  area?: boolean;
  unit?: string;
  fmt?: (v: number) => string;
}) {
  const pairs: [number, number][] = [];
  for (let i = 0; i < dist.length; i++) {
    const v = values[i];
    if (v != null && !isNaN(v)) pairs.push([dist[i], v]);
  }
  if (pairs.length < 2) return null;
  const W = 320, H = 108, padL = 4, padR = 4, padT = 10, padB = 14;
  const xs = pairs.map((p) => p[0]), ys = pairs.map((p) => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const spanX = maxX - minX || 1, spanY = maxY - minY || 1;
  const X = (x: number) => padL + ((x - minX) / spanX) * (W - padL - padR);
  const Y = (y: number) => padT + ((maxY - y) / spanY) * (H - padT - padB);
  const line = pairs.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}`).join(" ");
  const areaPath = `${line} L${X(maxX).toFixed(1)} ${H - padB} L${X(minX).toFixed(1)} ${H - padB} Z`;
  const show = (v: number) => (fmt ? fmt(v) : String(Math.round(v))) + (unit ?? "");
  const avg = ys.reduce((a, b) => a + b, 0) / ys.length;
  const midY = padT + (H - padT - padB) / 2;
  return (
    <section className="card">
      <div className="card-head">
        <span className="eyebrow">{title}</span>
        <span className="chart-range">méd {show(avg)}</span>
      </div>
      <div className="chart-wrap">
        <span className="chart-y chart-y-top">{show(maxY)}</span>
        <span className="chart-y chart-y-bot">{show(minY)}</span>
        <svg className="chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden>
          <line x1={padL} y1={midY} x2={W - padR} y2={midY} stroke="var(--line)" strokeWidth={1} vectorEffect="non-scaling-stroke" opacity={0.6} />
          {area && <path d={areaPath} fill={color} opacity={0.14} />}
          <path d={line} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
        </svg>
      </div>
      <div className="chart-x"><span>0 km</span><span>{maxX.toFixed(1).replace(".", ",")} km</span></div>
    </section>
  );
}

// Fallback: traçado como polyline em SVG (sem mapa base) quando o Leaflet falha.
function TrackMapSVG({ points }: { points: { lat: number; lon: number }[] }) {
  const pts = points.filter((p) => p.lat && p.lon);
  if (pts.length < 2) return null;
  const lats = pts.map((p) => p.lat), lons = pts.map((p) => p.lon);
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const minLon = Math.min(...lons), maxLon = Math.max(...lons);
  const kx = Math.cos(((minLat + maxLat) / 2 * Math.PI) / 180);
  const W = 320, H = 200, pad = 16;
  const spanX = (maxLon - minLon) * kx || 1e-6;
  const spanY = (maxLat - minLat) || 1e-6;
  const scale = Math.min((W - 2 * pad) / spanX, (H - 2 * pad) / spanY);
  const ox = (W - spanX * scale) / 2, oy = (H - spanY * scale) / 2;
  const X = (lon: number) => ox + (lon - minLon) * kx * scale;
  const Y = (lat: number) => H - (oy + (lat - minLat) * scale);
  const d = pts.map((p) => `${X(p.lon).toFixed(1)},${Y(p.lat).toFixed(1)}`).join(" ");
  const first = pts[0], last = pts[pts.length - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label="Traçado" style={{ display: "block" }}>
      <polyline points={d} fill="none" stroke="var(--accent)" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={X(first.lon)} cy={Y(first.lat)} r="5" fill="var(--accent)" stroke="var(--surface)" strokeWidth="2" />
      <circle cx={X(last.lon)} cy={Y(last.lat)} r="5" fill="var(--rose)" stroke="var(--surface)" strokeWidth="2" />
    </svg>
  );
}

// ---- mapa REAL de fundo (estilo Strava): tiles escuros do CARTO (grátis, com
// CORS -> canvas exportável) + a rota por cima, renderizados num canvas offscreen ----
function _lon2x(lon: number, z: number) { return ((lon + 180) / 360) * 256 * Math.pow(2, z); }
function _lat2y(lat: number, z: number) {
  const r = (lat * Math.PI) / 180;
  return ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * 256 * Math.pow(2, z);
}
function _tileURL(z: number, x: number, y: number) {
  const subs = ["a", "b", "c", "d"];
  return `https://${subs[(x + y) % subs.length]}.basemaps.cartocdn.com/dark_all/${z}/${x}/${y}.png`;
}
function _loadTile(url: string): Promise<HTMLImageElement | null> {
  return new Promise((res) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => res(img);
    img.onerror = () => res(null);
    img.src = url;
  });
}
async function buildMapCard(points: { lat: number; lon: number }[], W: number, H: number): Promise<HTMLCanvasElement | null> {
  const good = points.filter((p) => p.lat && p.lon);
  if (good.length < 2) return null;
  let minLa = 90, maxLa = -90, minLo = 180, maxLo = -180;
  for (const p of good) { minLa = Math.min(minLa, p.lat); maxLa = Math.max(maxLa, p.lat); minLo = Math.min(minLo, p.lon); maxLo = Math.max(maxLo, p.lon); }
  const padLa = (maxLa - minLa) * 0.16 || 0.003, padLo = (maxLo - minLo) * 0.16 || 0.003;
  minLa -= padLa; maxLa += padLa; minLo -= padLo; maxLo += padLo;
  let z = 17;
  for (; z >= 3; z--) {
    if (_lon2x(maxLo, z) - _lon2x(minLo, z) <= W && _lat2y(minLa, z) - _lat2y(maxLa, z) <= H) break;
  }
  const originX = (_lon2x(minLo, z) + _lon2x(maxLo, z)) / 2 - W / 2;
  const originY = (_lat2y(minLa, z) + _lat2y(maxLa, z)) / 2 - H / 2;
  const cv = document.createElement("canvas"); cv.width = W; cv.height = H;
  const ctx = cv.getContext("2d"); if (!ctx) return null;
  ctx.fillStyle = "#11131C"; ctx.fillRect(0, 0, W, H);
  const maxT = Math.pow(2, z) - 1;
  const jobs: Promise<void>[] = [];
  for (let tx = Math.floor(originX / 256); tx <= Math.floor((originX + W) / 256); tx++) {
    for (let ty = Math.floor(originY / 256); ty <= Math.floor((originY + H) / 256); ty++) {
      if (ty < 0 || ty > maxT) continue;
      const gx = ((tx % (maxT + 1)) + (maxT + 1)) % (maxT + 1);
      const dx = tx * 256 - originX, dy = ty * 256 - originY;
      jobs.push(_loadTile(_tileURL(z, gx, ty)).then((img) => { if (img) ctx.drawImage(img, dx, dy, 256, 256); }));
    }
  }
  await Promise.all(jobs);
  ctx.save();
  ctx.shadowColor = "rgba(31,217,184,0.5)"; ctx.shadowBlur = 16;
  ctx.strokeStyle = "#1FD9B8"; ctx.lineWidth = 8; ctx.lineJoin = "round"; ctx.lineCap = "round";
  ctx.beginPath();
  good.forEach((p, i) => { const x = _lon2x(p.lon, z) - originX, y = _lat2y(p.lat, z) - originY; if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
  ctx.stroke();
  ctx.restore();
  return cv;
}

// ---- estilos de card compartilhável (foto OU mapa real de fundo) ----
interface CardData { it: FeedItem; pts: { lat: number; lon: number }[]; date: string; name: string; kmTxt: string; photo: HTMLImageElement | null; mapCard: HTMLCanvasElement | null; }

function drawBg(ctx: CanvasRenderingContext2D, W: number, H: number, photo: HTMLImageElement | null, mapCard: HTMLCanvasElement | null) {
  if (photo && photo.width) {
    const s = Math.max(W / photo.width, H / photo.height);
    const dw = photo.width * s, dh = photo.height * s;
    ctx.drawImage(photo, (W - dw) / 2, (H - dh) / 2, dw, dh);
  } else if (mapCard) {
    ctx.drawImage(mapCard, 0, 0, W, H);
  } else {
    ctx.fillStyle = "#0C0D16"; ctx.fillRect(0, 0, W, H);
  }
}
function topScrim(ctx: CanvasRenderingContext2D, W: number) {
  const g = ctx.createLinearGradient(0, 0, 0, 240);
  g.addColorStop(0, "rgba(6,7,12,0.72)"); g.addColorStop(1, "rgba(6,7,12,0)");
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, 240);
}
function bottomScrim(ctx: CanvasRenderingContext2D, W: number, H: number, fromY: number) {
  const g = ctx.createLinearGradient(0, fromY, 0, H);
  g.addColorStop(0, "rgba(6,7,12,0)"); g.addColorStop(0.55, "rgba(6,7,12,0.78)"); g.addColorStop(1, "rgba(6,7,12,0.96)");
  ctx.fillStyle = g; ctx.fillRect(0, fromY, W, H - fromY);
}
// família usada no canvas — igual à do app (Archivo, via next/font). Resolvida
// do CSS em runtime pro card ter a MESMA cara de fonte do resto (estilo Strava).
let CANVAS_FONT = "system-ui, sans-serif";
function refreshCanvasFont() {
  if (typeof window === "undefined") return;
  const v = getComputedStyle(document.body).getPropertyValue("--font-display").trim();
  if (v) CANVAS_FONT = `${v}, system-ui, sans-serif`;
}

function markAt(ctx: CanvasRenderingContext2D, x: number, baseY: number, size = 46) {
  ctx.font = `800 ${size}px ${CANVAS_FONT}`;
  ctx.fillStyle = "#1FD9B8"; ctx.fillText("Rit", x, baseY);
  const rw = ctx.measureText("Rit").width;
  ctx.fillStyle = "#FFFFFF"; ctx.fillText("mind", x + rw, baseY);
}
function brandCentered(ctx: CanvasRenderingContext2D, cx: number, baseY: number, size: number) {
  ctx.font = `800 ${size}px ${CANVAS_FONT}`;
  const rw = ctx.measureText("Rit").width, mw = ctx.measureText("mind").width;
  const start = cx - (rw + mw) / 2;
  ctx.textAlign = "left";
  ctx.fillStyle = "#1FD9B8"; ctx.fillText("Rit", start, baseY);
  ctx.fillStyle = "#FFFFFF"; ctx.fillText("mind", start + rw, baseY);
}
// sombra suave: deixa texto/rota legíveis sobre QUALQUER foto (o card é
// transparente e vai ser colado por cima da foto do atleta no Instagram).
function withShadow(ctx: CanvasRenderingContext2D, fn: () => void) {
  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,0.55)"; ctx.shadowBlur = 16; ctx.shadowOffsetY = 2;
  fn();
  ctx.restore();
}
// traçado dentro de uma caixa (fit + início/fim), com brilho — pra fundo transparente
function drawRouteBox(
  ctx: CanvasRenderingContext2D, pts: { lat: number; lon: number }[],
  bx: number, by: number, bw: number, bh: number, color: string, lw: number,
) {
  const good = pts.filter((p) => p.lat && p.lon);
  if (good.length < 2) return;
  let minLa = 90, maxLa = -90, minLo = 180, maxLo = -180;
  for (const p of good) { minLa = Math.min(minLa, p.lat); maxLa = Math.max(maxLa, p.lat); minLo = Math.min(minLo, p.lon); maxLo = Math.max(maxLo, p.lon); }
  const kx = Math.cos(((minLa + maxLa) / 2 * Math.PI) / 180);
  const spanLo = Math.max(1e-6, (maxLo - minLo) * kx), spanLa = Math.max(1e-6, maxLa - minLa);
  const scale = Math.min(bw / spanLo, bh / spanLa);
  const ox = bx + (bw - spanLo * scale) / 2, oy = by + (bh - spanLa * scale) / 2;
  const px = (p: { lat: number; lon: number }) => ox + (p.lon - minLo) * kx * scale;
  const py = (p: { lat: number; lon: number }) => oy + (maxLa - p.lat) * scale;
  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,0.45)"; ctx.shadowBlur = 12;
  ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.lineJoin = "round"; ctx.lineCap = "round";
  ctx.beginPath();
  good.forEach((p, i) => { const x = px(p), y = py(p); if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
  ctx.stroke();
  ctx.restore();
}
function brandDate(ctx: CanvasRenderingContext2D, W: number, d: CardData) {
  markAt(ctx, 64, 104, 44);
  ctx.font = `600 28px ${CANVAS_FONT}`; ctx.fillStyle = "#E7E8F0"; ctx.textAlign = "right";
  ctx.fillText(d.date, W - 64, 100); ctx.textAlign = "left";
}
function footer(ctx: CanvasRenderingContext2D, W: number, H: number) {
  ctx.fillStyle = "#9A9BAE"; ctx.font = `600 22px ${CANVAS_FONT}`; ctx.textAlign = "center";
  ctx.fillText("ritmind", W / 2, H - 34); ctx.textAlign = "left";
}

// tempo tipo Strava: "53min 24s" (ou "1h05" em corrida longa)
function fmtDur(s: number): string {
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
  if (h > 0) return `${h}h${String(m).padStart(2, "0")}`;
  return ss > 0 ? `${m}min ${ss}s` : `${m}min`;
}
// [rótulo, valor com unidade] — Distância / Ritmo / Tempo (+ FC quando tem)
function shareCells(it: FeedItem): [string, string][] {
  const c: [string, string][] = [
    ["Distância", `${it.distance_km.toFixed(2).replace(".", ",")} km`],
    ["Ritmo", `${it.pace ?? "—"} /km`],
    ["Tempo", fmtDur(it.duration_s || it.duration_min * 60)],
  ];
  if (it.avg_hr != null) c.push(["FC média", `${it.avg_hr} bpm`]);
  return c;
}
// fileira de colunas (rótulo em cima, valor embaixo), largura automática;
// centerAt centraliza o conjunto num x. Sempre com sombra (fundo transparente).
function drawStatCols(
  ctx: CanvasRenderingContext2D, startX: number, baseY: number,
  cells: [string, string][], gap: number, valSize: number, labSize: number,
  centerAt?: number,
) {
  const widths = cells.map(([lab, val]) => {
    ctx.font = `800 ${valSize}px ${CANVAS_FONT}`; const wv = ctx.measureText(val).width;
    ctx.font = `600 ${labSize}px ${CANVAS_FONT}`; const wl = ctx.measureText(lab).width;
    return Math.max(wv, wl);
  });
  const total = widths.reduce((a, b) => a + b, 0) + gap * (cells.length - 1);
  let cx = centerAt != null ? centerAt - total / 2 : startX;
  withShadow(ctx, () => {
    ctx.textAlign = "left";
    cells.forEach(([lab, val], i) => {
      ctx.fillStyle = "#D6D7E2"; ctx.font = `600 ${labSize}px ${CANVAS_FONT}`;
      ctx.fillText(lab, cx, baseY);
      ctx.fillStyle = "#FFFFFF"; ctx.font = `800 ${valSize}px ${CANVAS_FONT}`;
      ctx.fillText(val, cx, baseY + valSize + 8);
      cx += widths[i] + gap;
    });
  });
}

// ===== estilos TRANSPARENTES (PNG com fundo vazado) pra colar em cima da foto =====

// CENTRALIZADO — stats empilhados no centro + traçado pequeno + marca (template 1).
function styleCentralizado(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  const cx = W / 2;
  const cells = shareCells(d.it).slice(0, 3);
  let y = 360;
  withShadow(ctx, () => {
    ctx.textAlign = "center";
    for (const [lab, val] of cells) {
      ctx.fillStyle = "#EAEBF2"; ctx.font = `600 36px ${CANVAS_FONT}`; ctx.fillText(lab, cx, y);
      ctx.fillStyle = "#FFFFFF"; ctx.font = `800 96px ${CANVAS_FONT}`; ctx.fillText(val, cx, y + 96);
      y += 180;
    }
    ctx.textAlign = "left";
  });
  if (d.pts.length >= 2) drawRouteBox(ctx, d.pts, cx - 150, y - 6, 300, 220, "#1FD9B8", 8);
  withShadow(ctx, () => brandCentered(ctx, cx, y + 296, 42));
}

// ROTA — traçado grande como herói + marca + stats embaixo (template 2).
function styleRota(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  const cx = W / 2;
  if (d.pts.length >= 2) drawRouteBox(ctx, d.pts, 110, 250, W - 220, 620, "#1FD9B8", 13);
  withShadow(ctx, () => brandCentered(ctx, cx, 980, 46));
  drawStatCols(ctx, 0, 1030, shareCells(d.it).slice(0, 3), 72, 58, 30, cx);
}

// CANTINHO — marca + stats no canto inferior esquerdo (template 3).
function styleCantinho(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  withShadow(ctx, () => markAt(ctx, 64, H - 230, 44));
  drawStatCols(ctx, 64, H - 150, shareCells(d.it).slice(0, 3), 64, 60, 28);
}

// COM MAPA — card completo (não transparente): mapa/foto de fundo + stats.
function styleMapa(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  drawBg(ctx, W, H, d.photo, d.mapCard);
  topScrim(ctx, W); bottomScrim(ctx, W, H, H - 420);
  brandDate(ctx, W, d);
  drawStatCols(ctx, 64, H - 200, shareCells(d.it).slice(0, 3), 56, 72, 26);
  footer(ctx, W, H);
}

interface CardStyle { key: string; label: string; transparent: boolean; draw: (c: CanvasRenderingContext2D, W: number, H: number, d: CardData) => void; }
const CARD_STYLES: CardStyle[] = [
  { key: "centralizado", label: "Central", transparent: true, draw: styleCentralizado },
  { key: "rota", label: "Rota", transparent: true, draw: styleRota },
  { key: "cantinho", label: "Cantinho", transparent: true, draw: styleCantinho },
  { key: "mapa", label: "Com mapa", transparent: false, draw: styleMapa },
];

function AtividadesInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [feed, setFeed] = useState<FeedItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [sel, setSel] = useState<FeedItem | null>(null);
  const [track, setTrack] = useState<TrackData | null>(null);
  const [loadingTrack, setLoadingTrack] = useState(false);
  const [analysis, setAnalysis] = useState<CoachAnalysis | null>(null);
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [editor, setEditor] = useState(false);
  const [photoImg, setPhotoImg] = useState<HTMLImageElement | null>(null);
  const [styleIdx, setStyleIdx] = useState(0);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [mapCard, setMapCard] = useState<HTMLCanvasElement | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const previewRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    (async () => {
      const f = await getFeed();
      if (f === null) { router.replace("/entrar"); return; }
      setFeed(f);
      setLoading(false);
      // deep-link: /atividades?date=YYYY-MM-DD (ou ?key=arch-123) abre direto a
      // atividade — é assim que o "Ver como foi" da home entra na corrida do dia
      // em vez de cair na lista. useSearchParams (não window.location) pra pegar
      // a query já na 1ª navegação client-side (antes exigia refresh). Sem match
      // (ex.: sync ainda não chegou), fica na lista mesmo (degrada bem).
      const key = params.get("key");
      const date = params.get("date");
      const hit = key
        ? f.find((it) => it.key === key)
        : date
          ? f.find((it) => it.date_iso === date)
          : null;
      if (hit) open(hit);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, params]);

  async function open(it: FeedItem) {
    setSel(it);
    setTrack(null);
    setAnalysis(null);
    setAnalysisOpen(false);
    // análise do coach (best-effort, não bloqueia o traçado)
    getActivityAnalysis(it).then(setAnalysis).catch(() => {});
    if (it.has_track) {
      setLoadingTrack(true);
      setTrack(await getTrack(it));
      setLoadingTrack(false);
    }
  }

  function openEditor() {
    setPhotoImg(null); setStyleIdx(0); setResultUrl(null); setEditor(true);
  }

  function onPickPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const img = new Image();
    img.onload = () => setPhotoImg(img);
    img.src = URL.createObjectURL(file);
  }

  // monta o mapa REAL de fundo (tiles + rota) só no estilo "Com mapa" e sem foto
  useEffect(() => {
    if (!editor || CARD_STYLES[styleIdx].transparent || photoImg) { setMapCard(null); return; }
    const pts = track?.points ?? [];
    if (pts.length < 2) { setMapCard(null); return; }
    let alive = true;
    buildMapCard(pts, 1080, 1350).then((c) => { if (alive) setMapCard(c); });
    return () => { alive = false; };
  }, [editor, styleIdx, photoImg, track]);

  // redesenha o preview quando muda estilo/foto/atividade/mapa
  useEffect(() => {
    if (!editor || !sel) return;
    const cv = previewRef.current;
    if (!cv) return;
    refreshCanvasFont();
    const paint = () => {
      cv.width = 1080; cv.height = 1350;
      const ctx = cv.getContext("2d");
      if (!ctx) return;
      ctx.textBaseline = "alphabetic";
      ctx.clearRect(0, 0, 1080, 1350);
      const d: CardData = {
        it: sel,
        pts: track?.points ?? [],
        date: fmtDate(sel.datetime ?? sel.date_iso),
        name: sel.name || "Corrida",
        kmTxt: km(sel.distance_km),
        photo: photoImg,
        mapCard,
      };
      CARD_STYLES[styleIdx].draw(ctx, 1080, 1350, d);
    };
    paint();
    // redesenha quando a fonte (Archivo) terminar de carregar, pra não sair no fallback
    document.fonts?.ready.then(paint).catch(() => {});
  }, [editor, styleIdx, photoImg, sel, track, mapCard]);

  // PNG (mantém a transparência) do card atual
  async function makeBlob(): Promise<Blob | null> {
    const cv = previewRef.current;
    if (!cv) return null;
    return new Promise((res) => cv.toBlob((b) => res(b), "image/png"));
  }

  // COPIAR a imagem pro clipboard — pra colar direto no Instagram/story
  async function copyImage() {
    if (!sel) return;
    setSharing(true);
    try {
      const blob = await makeBlob();
      if (!blob) throw new Error("no blob");
      const CI = (window as unknown as { ClipboardItem?: typeof ClipboardItem }).ClipboardItem;
      if (navigator.clipboard && CI) {
        await navigator.clipboard.write([new CI({ "image/png": blob })]);
        setCopied(true);
        setTimeout(() => setCopied(false), 2500);
      } else {
        setResultUrl(URL.createObjectURL(blob));
      }
    } catch {
      const blob = await makeBlob();
      if (blob) setResultUrl(URL.createObjectURL(blob));
    }
    setSharing(false);
  }

  async function shareCurrent() {
    if (!sel) return;
    setSharing(true);
    try {
      const blob = await makeBlob();
      if (!blob) throw new Error("no blob");
      const file = new File([blob], "ritmind-corrida.png", { type: "image/png" });
      const navShare = navigator as Navigator & { canShare?: (d: unknown) => boolean };
      if (navShare.canShare && navShare.canShare({ files: [file] })) {
        try {
          await navigator.share({ files: [file], text: `${km(sel.distance_km)} km no Ritmind 🏃` });
          setSharing(false);
          return;
        } catch (err) {
          if (err instanceof DOMException && err.name === "AbortError") { setSharing(false); return; }
        }
      }
      setResultUrl(URL.createObjectURL(blob));
    } catch { /* indisponível */ }
    setSharing(false);
  }

  if (loading || !feed) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
          <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
        </div>
      </main>
    );
  }

  // TELA: detalhe
  if (sel) {
    const it = sel;
    const maxPace = track && track.splits.length
      ? Math.max(...track.splits.map((s) => s.sec / (s.partial_km || 1)), 1)
      : 1;

    // melhor km = km cheio mais rápido (parcial final de fora) — leitura estilo
    // Strava, calculada dos splits quando o traçado carrega
    const fullKm = track ? track.splits.filter((s) => s.km != null && s.sec > 0) : [];
    const bestSec = fullKm.length
      ? Math.min(...fullKm.map((s) => s.sec / (s.partial_km || 1)))
      : null;

    const m = track?.metrics;

    // GRID principal: só 3 tiles glanceáveis (além de dist/tempo/ritmo). O resto
    // vira lista em "Detalhes" — pra tela não virar um monte de bullets.
    const primary: { v: string; unit: string; k: string }[] = [];
    if (it.avg_hr != null) primary.push({ v: String(it.avg_hr), unit: " bpm", k: "FC média" });
    if (m?.avg_cadence) primary.push({ v: String(m.avg_cadence), unit: " spm", k: "Cadência" });
    if (it.elevation_gain != null) primary.push({ v: String(it.elevation_gain), unit: " m", k: "Ganho" });
    if (primary.length < 3 && m?.calories) primary.push({ v: String(m.calories), unit: " kcal", k: "Calorias" });
    if (primary.length < 3 && m?.avg_power) primary.push({ v: String(m.avg_power), unit: " W", k: "Potência" });

    // DETALHES: lista compacta (rótulo — valor), só o que existe
    const details: [string, string][] = [];
    if (it.max_hr != null) details.push(["FC máxima", `${it.max_hr} bpm`]);
    if (bestSec != null) details.push(["Melhor km", `${fmtPaceSec(bestSec)}/km`]);
    if (m?.max_cadence) details.push(["Cadência máx", `${m.max_cadence} spm`]);
    if (m?.avg_power && !primary.some((p) => p.k === "Potência")) details.push(["Potência média", `${m.avg_power} W`]);
    if (m?.max_power) details.push(["Potência máx", `${m.max_power} W`]);
    if (m?.calories && !primary.some((p) => p.k === "Calorias")) details.push(["Calorias", `${m.calories} kcal`]);
    if (m?.training_effect) details.push(["Efeito aeróbico", m.training_effect.toFixed(1)]);
    if (m?.anaerobic_effect) details.push(["Efeito anaeróbico", m.anaerobic_effect.toFixed(1)]);
    if (m?.elevation_loss) details.push(["Perda de elevação", `${m.elevation_loss} m`]);
    if (m?.ground_contact_ms) details.push(["Contato com o solo", `${m.ground_contact_ms} ms`]);
    if (m?.vertical_oscillation_cm) details.push(["Oscilação vertical", `${m.vertical_oscillation_cm} cm`]);
    if (m?.stride_length_cm) { const sl = m.stride_length_cm > 10 ? m.stride_length_cm / 100 : m.stride_length_cm; details.push(["Passada", `${sl.toFixed(2)} m`]); }
    if (m?.vertical_ratio) details.push(["Razão vertical", `${m.vertical_ratio}%`]);
    const temp = it.air_temp_c ?? m?.avg_temperature;
    if (temp != null) details.push(["Temperatura", `${temp} °C`]);
    return (
      <main className="stage">
        <div className="phone">
          <header className="appbar">
            <button className="icon-btn" aria-label="Voltar" onClick={() => setSel(null)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
            </button>
            <div className="title"><div className="k">{fmtDate(it.datetime ?? it.date_iso)}</div><div className="t">{it.name}</div></div>
            <button className="icon-btn" aria-label="Compartilhar" onClick={openEditor}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.1} strokeLinecap="round" strokeLinejoin="round"><circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" /><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4" /></svg>
            </button>
          </header>

          <input ref={fileRef} type="file" accept="image/*" hidden onChange={onPickPhoto} />

          {editor && (
            <div className="share-editor">
              <div className="se-inner">
              <header className="appbar">
                <button className="icon-btn" aria-label="Fechar" onClick={() => { setEditor(false); setResultUrl(null); }}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
                </button>
                <div className="title"><div className="t">Compartilhar</div></div>
                <span style={{ width: 34 }} />
              </header>

              <div className="se-preview">
                <canvas ref={previewRef} className={`se-canvas${CARD_STYLES[styleIdx].transparent ? " transp" : ""}`} />
              </div>

              <div className="se-styles">
                {CARD_STYLES.map((s, i) => (
                  <button key={s.key} className={`se-chip${i === styleIdx ? " on" : ""}`} onClick={() => setStyleIdx(i)}>{s.label}</button>
                ))}
              </div>

              {CARD_STYLES[styleIdx].transparent ? (
                <p className="se-hint">Fundo transparente — copie e cole por cima da sua foto no story do Instagram 📲</p>
              ) : (
                <div className="se-photo">
                  <button className="btn-ghost" onClick={() => fileRef.current?.click()}>
                    {photoImg ? "Trocar foto" : "📷 Adicionar sua foto"}
                  </button>
                  {photoImg && <button className="btn-ghost" onClick={() => setPhotoImg(null)}>Remover</button>}
                </div>
              )}

              <div className="se-actions">
                <button className="btn se-share" onClick={copyImage} disabled={sharing}>
                  {copied ? "Copiado! ✓" : sharing ? "Gerando…" : "Copiar imagem"}
                </button>
                <button className="btn-ghost" onClick={shareCurrent} disabled={sharing}>Compartilhar</button>
              </div>

              {resultUrl && (
                <div className="se-result" onClick={() => setResultUrl(null)}>
                  <div className="se-result-in" onClick={(e) => e.stopPropagation()}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={resultUrl} alt="Card da corrida" />
                    <p>Segure a imagem para copiar ou salvar — depois cole no seu story 📲</p>
                    <a className="btn" href={resultUrl} download="ritmind-corrida.png">Baixar imagem</a>
                    <button className="btn-ghost" onClick={() => setResultUrl(null)}>Voltar</button>
                  </div>
                </div>
              )}
              </div>
            </div>
          )}

          {/* MAPA no topo (herói), estilo Strava — rola pra baixo pra ver as infos */}
          {it.has_track && track && track.points.length >= 2 && (
            <section className="map-section map-hero"><MapView points={track.points} /></section>
          )}

          <div className="qstats">
            <div className="qstat"><div className="v">{km(it.distance_km)}<small> km</small></div><div className="k">Distância</div></div>
            <div className="qstat"><div className="v">{it.duration_min}<small> min</small></div><div className="k">Tempo</div></div>
            <div className="qstat"><div className="v">{it.pace ?? "—"}<small>{it.pace ? "/km" : ""}</small></div><div className="k">Pace</div></div>
          </div>

          {primary.length > 0 && (
            <div className="qstats">
              {primary.slice(0, 3).map((s, ci) => (
                <div className="qstat" key={ci}>
                  <div className="v">{s.v}<small>{s.unit}</small></div>
                  <div className="k">{s.k}</div>
                </div>
              ))}
            </div>
          )}

          {analysis?.analysis && (
            <section className="card coach-analysis">
              <button className="ca-toggle" onClick={() => setAnalysisOpen((o) => !o)} aria-expanded={analysisOpen}>
                <span className="ca-title">📊 Análise do coach{analysis.workout_type ? ` · ${analysis.workout_type}` : ""}</span>
                <svg className={`ca-chev${analysisOpen ? " open" : ""}`} viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M6 9l6 6 6-6" /></svg>
              </button>
              {analysisOpen && <p className="ca-text">{analysis.analysis}</p>}
            </section>
          )}

          {it.hr_zones && <HrZones zones={it.hr_zones} />}

          {it.has_track ? (
            loadingTrack || !track ? (
              <div className="card center"><p className="auth-sub" style={{ margin: 0 }}>Carregando traçado…</p></div>
            ) : (
              <>
                {track.series?.elev?.length ? (
                  <Chart title="Altimetria" dist={track.series.dist} values={track.series.elev} color="#8B7BE8" area unit=" m" />
                ) : null}
                {track.series?.hr?.length ? (
                  <Chart title="Frequência cardíaca" dist={track.series.dist} values={track.series.hr} color="#E24666" unit=" bpm" />
                ) : null}
                {track.splits.length > 0 && (() => {
                  const hasHr = track.splits.some((s) => s.hr != null);
                  return (
                    <section className="card">
                      <div className="card-head"><span className="eyebrow">Parciais por km</span></div>
                      <div className={`splits${hasHr ? " with-hr" : ""}`}>
                        <div className="split head">
                          <span className="sk">km</span>
                          <span className="sbar" />
                          <span className="sp">pace</span>
                          {hasHr && <span className="shr">FC</span>}
                        </div>
                        {track.splits.map((s, i) => {
                          const paceSec = s.sec / (s.partial_km || 1);
                          const w = Math.max(8, Math.round((paceSec / maxPace) * 100));
                          return (
                            <div className="split" key={i}>
                              <span className="sk">{s.km ?? `${String(s.partial_km).replace(".", ",")}`}<small>{s.km ? "" : " km"}</small></span>
                              <span className="sbar"><i style={{ width: `${w}%` }} /></span>
                              <span className="sp">{s.pace ?? "—"}<small>/km</small></span>
                              {hasHr && <span className="shr">{s.hr != null ? s.hr : "—"}<small>{s.hr != null ? " bpm" : ""}</small></span>}
                            </div>
                          );
                        })}
                      </div>
                    </section>
                  );
                })()}
              </>
            )
          ) : (
            <div className="card center">
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>Trajeto e parciais não foram salvos nesta atividade. Corridas gravadas pelo app mostram o mapa e os splits. 🗺️</p>
            </div>
          )}

          {details.length > 0 && (
            <section className="card">
              <div className="card-head"><span className="eyebrow">Detalhes</span></div>
              <div className="det">
                {details.map(([k, v], i) => (
                  <div className="det-row" key={i}><span className="det-k">{k}</span><span className="det-v">{v}</span></div>
                ))}
              </div>
            </section>
          )}

          <p className="det-src">Fonte: {it.source === "app" ? "GPS do app" : "Strava/Garmin"}</p>
        </div>
      </main>
    );
  }

  // TELA: feed
  return (
    <main className="stage">
      <div className="phone has-nav">
        <div className="topbar">
          <div className="brand"><Mark /><span className="word">Rit<b>mind</b></span></div>
        </div>
        <div className="greet"><h1>Atividades</h1></div>

        <button className="cta-btn" onClick={() => router.push("/correr")}>
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><polygon points="10 8 16 12 10 16 10 8" fill="currentColor" stroke="none" /></svg>
          Correr agora (GPS)
        </button>

        {feed.length === 0 ? (
          <div className="card center">
            <p className="muted" style={{ margin: 0 }}>Nenhuma atividade ainda. Grava uma corrida pelo app ou conecta o Strava/Garmin. 🏃</p>
          </div>
        ) : (
          feed.map((it) => (
            <section key={it.key} className="card tap" onClick={() => open(it)}>
              <div className="run-row">
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="rr-date">
                    {fmtDate(it.datetime ?? it.date_iso)}{fmtTime(it.datetime) ? ` · ${fmtTime(it.datetime)}` : ""}
                    <span className={`src-tag ${it.source}`}>{it.source === "app" ? "app" : "sync"}</span>
                    {it.has_track && <span className="src-tag track">mapa</span>}
                  </div>
                  <div className="rr-km">{km(it.distance_km)} km</div>
                  <div className="rr-meta">{it.duration_min} min · {it.pace ?? "—"}/km{it.avg_hr ? ` · ${it.avg_hr} bpm` : ""}</div>
                </div>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M9 6l6 6-6 6" /></svg>
              </div>
            </section>
          ))
        )}
      </div>
      <BottomNav />
    </main>
  );
}

// useSearchParams (deep-link ?date=/?key=) exige boundary de Suspense no export
// estático do Next — senão a query não chega na 1ª navegação (só no refresh).
export default function AtividadesPage() {
  return (
    <Suspense
      fallback={
        <main className="stage">
          <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
            <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
          </div>
        </main>
      }
    >
      <AtividadesInner />
    </Suspense>
  );
}
