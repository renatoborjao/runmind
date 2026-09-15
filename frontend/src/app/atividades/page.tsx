"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import BottomNav from "../bottom-nav";
import {
  getFeed,
  getTrack,
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

// Mapa real com o trajeto (Leaflet + OSM). Cai pro traçado em SVG se o mapa não
// carregar (offline/tiles bloqueados).
function MapView({ points }: { points: { lat: number; lon: number }[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const pts = points.filter((p) => p.lat && p.lon).map((p) => [p.lat, p.lon]);
    if (pts.length < 2 || !ref.current) return;
    let map: any;
    let cancelled = false;
    loadLeaflet()
      .then((L: any) => {
        if (cancelled || !ref.current) return;
        // Mapa TRAVADO no percurso: encostar o dedo não arrasta/gira o mapa —
        // ele fica focado no traçado (o atleta pediu "só no percurso"). Os
        // botões de zoom seguem valendo pra aproximar/afastar.
        map = L.map(ref.current, {
          zoomControl: true,
          attributionControl: true,
          scrollWheelZoom: false,
          dragging: false,
          touchZoom: false,
          doubleClickZoom: false,
          boxZoom: false,
          keyboard: false,
          tap: false,
        });
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: "© OpenStreetMap",
        }).addTo(map);
        const line = L.polyline(pts, { color: "#0FB499", weight: 4 }).addTo(map);
        L.circleMarker(pts[0], { radius: 6, color: "#fff", weight: 2, fillColor: "#0FB499", fillOpacity: 1 }).addTo(map);
        L.circleMarker(pts[pts.length - 1], { radius: 6, color: "#fff", weight: 2, fillColor: "#E24666", fillOpacity: 1 }).addTo(map);
        const b = line.getBounds();
        map.fitBounds(b, { padding: [22, 22] });
        map.setMaxBounds(b.pad(0.25));  // não deixa o mapa vagar pra longe do percurso
        setTimeout(() => map && map.invalidateSize(), 120);
      })
      .catch(() => setFailed(true));
    return () => {
      cancelled = true;
      if (map) map.remove();
    };
  }, [points]);

  if (failed) return <TrackMapSVG points={points} />;
  return <div ref={ref} className="map-box" />;
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
  return (
    <section className="card">
      <div className="card-head">
        <span className="eyebrow">{title}</span>
        <span className="chart-range">{show(maxY)} · {show(minY)}</span>
      </div>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden>
        {area && <path d={areaPath} fill={color} opacity={0.14} />}
        <path d={line} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      </svg>
    </section>
  );
}

// Dinâmica de corrida (Garmin): cadência máx, contato com o solo, oscilação e
// comprimento de passada — o pacote "avançado" que o atleta via só no Garmin.
function RunDynamics({ m }: { m: NonNullable<TrackData["metrics"]> }) {
  const cells: { v: string; k: string }[] = [];
  if (m.max_cadence) cells.push({ v: `${m.max_cadence} spm`, k: "Cadência máx" });
  if (m.ground_contact_ms) cells.push({ v: `${m.ground_contact_ms} ms`, k: "Contato solo" });
  if (m.vertical_oscillation_cm) cells.push({ v: `${m.vertical_oscillation_cm} cm`, k: "Oscilação vert." });
  if (m.stride_length_cm) {
    const s = m.stride_length_cm > 10 ? m.stride_length_cm / 100 : m.stride_length_cm;
    cells.push({ v: `${s.toFixed(2)} m`, k: "Passada" });
  }
  if (m.vertical_ratio) cells.push({ v: `${m.vertical_ratio}%`, k: "Razão vertical" });
  if (m.max_power) cells.push({ v: `${m.max_power} W`, k: "Potência máx" });
  if (!cells.length) return null;
  return (
    <section className="card">
      <div className="card-head"><span className="eyebrow">Dinâmica de corrida</span></div>
      <div className="dyn">
        {cells.map((c, i) => (
          <div className="dyn-cell" key={i}><div className="v">{c.v}</div><div className="k">{c.k}</div></div>
        ))}
      </div>
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

// desenha o traçado dentro de uma caixa do canvas (fit + início/fim)
function drawRouteInBox(
  ctx: CanvasRenderingContext2D,
  pts: { lat: number; lon: number }[],
  bx: number, by: number, bw: number, bh: number,
  color: string, lw: number,
) {
  const good = pts.filter((p) => p.lat && p.lon);
  if (good.length < 2) return false;
  let minLa = 90, maxLa = -90, minLo = 180, maxLo = -180;
  for (const p of good) { minLa = Math.min(minLa, p.lat); maxLa = Math.max(maxLa, p.lat); minLo = Math.min(minLo, p.lon); maxLo = Math.max(maxLo, p.lon); }
  const midLa = (minLa + maxLa) / 2;
  const kx = Math.cos((midLa * Math.PI) / 180);
  const spanLo = Math.max(1e-6, (maxLo - minLo) * kx);
  const spanLa = Math.max(1e-6, maxLa - minLa);
  const scale = Math.min(bw / spanLo, bh / spanLa);
  const ox = bx + (bw - spanLo * scale) / 2, oy = by + (bh - spanLa * scale) / 2;
  const px = (p: { lat: number; lon: number }) => ox + (p.lon - minLo) * kx * scale;
  const py = (p: { lat: number; lon: number }) => oy + (maxLa - p.lat) * scale;
  ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.lineJoin = "round"; ctx.lineCap = "round";
  ctx.beginPath();
  good.forEach((p, i) => { const x = px(p), y = py(p); if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
  ctx.stroke();
  const r = Math.max(6, lw * 1.4);
  ctx.fillStyle = "#FFFFFF"; ctx.beginPath(); ctx.arc(px(good[0]), py(good[0]), r, 0, 7); ctx.fill();
  ctx.fillStyle = "#E24666"; ctx.beginPath(); ctx.arc(px(good[good.length - 1]), py(good[good.length - 1]), r, 0, 7); ctx.fill();
  return true;
}

// ---- estilos de card compartilhável (todos por cima da foto, ou fundo escuro) ----
interface CardData { it: FeedItem; pts: { lat: number; lon: number }[]; date: string; name: string; kmTxt: string; photo: HTMLImageElement | null; }

function drawBg(ctx: CanvasRenderingContext2D, W: number, H: number, photo: HTMLImageElement | null) {
  if (photo && photo.width) {
    const s = Math.max(W / photo.width, H / photo.height);
    const dw = photo.width * s, dh = photo.height * s;
    ctx.drawImage(photo, (W - dw) / 2, (H - dh) / 2, dw, dh);
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
function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
function markAt(ctx: CanvasRenderingContext2D, x: number, baseY: number, size = 46) {
  ctx.font = `800 ${size}px system-ui, -apple-system, Segoe UI, sans-serif`;
  ctx.fillStyle = "#1FD9B8"; ctx.fillText("Rit", x, baseY);
  const rw = ctx.measureText("Rit").width;
  ctx.fillStyle = "#FFFFFF"; ctx.fillText("mind", x + rw, baseY);
}
function kmBig(ctx: CanvasRenderingContext2D, x: number, baseY: number, kmTxt: string, size = 150) {
  ctx.fillStyle = "#1FD9B8"; ctx.font = `800 ${size}px system-ui, sans-serif`;
  ctx.fillText(kmTxt, x, baseY);
  const w = ctx.measureText(kmTxt).width;
  ctx.fillStyle = "#C9CAD6"; ctx.font = `600 ${Math.round(size * 0.27)}px system-ui, sans-serif`;
  ctx.fillText(" km", x + w + 8, baseY);
}
// células de estatística no padrão Strava: número em cima (grande), rótulo em
// caixa-alta embaixo (pequeno). Distância/Ritmo/Tempo (+FC quando tem).
function statCells(it: FeedItem): [string, string][] {
  const c: [string, string][] = [
    [it.distance_km.toFixed(2).replace(".", ","), "DISTÂNCIA (KM)"],
    [it.pace ?? "—", "RITMO /KM"],
    [`${it.duration_min}`, "TEMPO (MIN)"],
  ];
  if (it.avg_hr != null) c.push([`${it.avg_hr}`, "FC MÉDIA"]);
  return c;
}
// desenha a fileira de estatísticas com LARGURA AUTOMÁTICA por coluna (número
// e rótulo nunca se sobrepõem, não importa o tamanho do texto).
function drawStatRow(
  ctx: CanvasRenderingContext2D, x: number, baseY: number,
  cells: [string, string][], gap: number, valSize: number, labSize: number,
) {
  let cx = x;
  for (const [v, l] of cells) {
    ctx.fillStyle = "#FFFFFF"; ctx.font = `800 ${valSize}px system-ui, sans-serif`;
    ctx.fillText(v, cx, baseY);
    const w1 = ctx.measureText(v).width;
    ctx.fillStyle = "#D4D5E0"; ctx.font = `600 ${labSize}px system-ui, sans-serif`;
    ctx.fillText(l, cx, baseY + labSize + 12);
    const w2 = ctx.measureText(l).width;
    cx += Math.max(w1, w2) + gap;
  }
}
function brandDate(ctx: CanvasRenderingContext2D, W: number, d: CardData) {
  markAt(ctx, 64, 104, 44);
  ctx.font = "600 28px system-ui, sans-serif"; ctx.fillStyle = "#E7E8F0"; ctx.textAlign = "right";
  ctx.fillText(d.date, W - 64, 100); ctx.textAlign = "left";
}
function footer(ctx: CanvasRenderingContext2D, W: number, H: number) {
  ctx.fillStyle = "#9A9BAE"; ctx.font = "600 22px system-ui, sans-serif"; ctx.textAlign = "center";
  ctx.fillText("ritmind", W / 2, H - 34); ctx.textAlign = "left";
}

// CLÁSSICO — overlay estilo Strava: foto + degradê + fileira de stats embaixo.
// Sem foto, o traçado vira o herói do fundo.
function styleClassico(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  drawBg(ctx, W, H, d.photo);
  if (d.photo) { topScrim(ctx, W); bottomScrim(ctx, W, H, H - 430); }
  else if (d.pts.length >= 2) drawRouteInBox(ctx, d.pts, 96, 300, W - 192, 560, "#1FD9B8", 9);
  brandDate(ctx, W, d);
  if (d.photo && d.pts.length >= 2) drawRouteInBox(ctx, d.pts, W - 296, 150, 232, 150, "#FFFFFF", 5);
  drawStatRow(ctx, 64, H - 150, statCells(d.it), 60, 82, 24);
  footer(ctx, W, H);
}

// MINIMAL — barra de vidro embaixo: km grande à esquerda, ritmo/tempo à direita.
function styleMinimal(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  drawBg(ctx, W, H, d.photo);
  if (d.photo) topScrim(ctx, W);
  else if (d.pts.length >= 2) drawRouteInBox(ctx, d.pts, 96, 320, W - 192, 520, "#1FD9B8", 8);
  brandDate(ctx, W, d);
  const barH = 176, y = H - 72 - barH;
  roundRect(ctx, 48, y, W - 96, barH, 28); ctx.fillStyle = "rgba(10,11,18,0.74)"; ctx.fill();
  kmBig(ctx, 88, y + 112, d.kmTxt, 96);
  const line = `${d.it.pace ? d.it.pace + " /km" : ""}${d.it.pace ? "    " : ""}${d.it.duration_min} min`;
  ctx.fillStyle = "#EDEEF5"; ctx.font = "700 36px system-ui, sans-serif"; ctx.textAlign = "right";
  ctx.fillText(line, W - 88, y + 106); ctx.textAlign = "left";
  if (d.it.avg_hr != null) {
    ctx.fillStyle = "#C9CAD6"; ctx.font = "600 30px system-ui, sans-serif"; ctx.textAlign = "right";
    ctx.fillText(`${d.it.avg_hr} bpm`, W - 88, y + 150); ctx.textAlign = "left";
  }
}

// TRAJETO — o mapa é o herói (grande), stats embaixo.
function styleTrajeto(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  drawBg(ctx, W, H, d.photo);
  if (d.photo) { ctx.fillStyle = "rgba(6,7,12,0.45)"; ctx.fillRect(0, 0, W, H); }
  brandDate(ctx, W, d);
  if (d.pts.length >= 2) drawRouteInBox(ctx, d.pts, 100, 240, W - 200, 700, "#1FD9B8", 11);
  else { ctx.fillStyle = "#3A3B49"; ctx.font = "600 120px system-ui, sans-serif"; ctx.textAlign = "center"; ctx.fillText("🏃", W / 2, 640); ctx.textAlign = "left"; }
  bottomScrim(ctx, W, H, H - 320);
  drawStatRow(ctx, 64, H - 150, statCells(d.it), 60, 78, 24);
  footer(ctx, W, H);
}

// SELO — cartão de vidro compacto (canto inferior) pra colar em qualquer foto/story.
function styleSelo(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  drawBg(ctx, W, H, d.photo);
  const bw = 640, bh = 316, bx = 48, by = H - 60 - bh;
  roundRect(ctx, bx, by, bw, bh, 32); ctx.fillStyle = "rgba(10,11,18,0.85)"; ctx.fill();
  markAt(ctx, bx + 36, by + 68, 38);
  kmBig(ctx, bx + 36, by + 188, d.kmTxt, 100);
  ctx.fillStyle = "#C9CAD6"; ctx.font = "600 30px system-ui, sans-serif";
  ctx.fillText(`${d.it.pace ? d.it.pace + " /km · " : ""}${d.it.duration_min} min${d.it.avg_hr != null ? " · " + d.it.avg_hr + " bpm" : ""}`, bx + 36, by + 254);
  if (d.pts.length >= 2) drawRouteInBox(ctx, d.pts, W - 250, 110, 190, 150, "#1FD9B8", 5);
}

const CARD_STYLES: { key: string; label: string; draw: (c: CanvasRenderingContext2D, W: number, H: number, d: CardData) => void }[] = [
  { key: "classico", label: "Clássico", draw: styleClassico },
  { key: "trajeto", label: "Trajeto", draw: styleTrajeto },
  { key: "minimal", label: "Minimal", draw: styleMinimal },
  { key: "selo", label: "Selo", draw: styleSelo },
];

export default function AtividadesPage() {
  const router = useRouter();
  const [feed, setFeed] = useState<FeedItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [sel, setSel] = useState<FeedItem | null>(null);
  const [track, setTrack] = useState<TrackData | null>(null);
  const [loadingTrack, setLoadingTrack] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [editor, setEditor] = useState(false);
  const [photoImg, setPhotoImg] = useState<HTMLImageElement | null>(null);
  const [styleIdx, setStyleIdx] = useState(0);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const previewRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    (async () => {
      const f = await getFeed();
      if (f === null) { router.replace("/entrar"); return; }
      setFeed(f);
      setLoading(false);
    })();
  }, [router]);

  async function open(it: FeedItem) {
    setSel(it);
    setTrack(null);
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

  // redesenha o preview quando muda estilo/foto/atividade
  useEffect(() => {
    if (!editor || !sel) return;
    const cv = previewRef.current;
    if (!cv) return;
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
    };
    CARD_STYLES[styleIdx].draw(ctx, 1080, 1350, d);
  }, [editor, styleIdx, photoImg, sel, track]);

  async function shareCurrent() {
    const cv = previewRef.current;
    if (!cv || !sel) return;
    setSharing(true);
    try {
      const blob: Blob = await new Promise((res) => cv.toBlob((b) => res(b as Blob), "image/jpeg", 0.92));
      const file = new File([blob], "ritmind-corrida.jpg", { type: "image/jpeg" });
      const navShare = navigator as Navigator & { canShare?: (d: unknown) => boolean };
      if (navShare.canShare && navShare.canShare({ files: [file] })) {
        try {
          await navigator.share({ files: [file], text: `${km(sel.distance_km)} km no Ritmind 🏃` });
          setSharing(false);
          return;
        } catch (err) {
          // usuário cancelou o menu de compartilhar: não mostra fallback
          if (err instanceof DOMException && err.name === "AbortError") { setSharing(false); return; }
        }
      }
      // sem share nativo (ou falhou): mostra a imagem pra salvar/segurar
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

    // estatísticas extras (só as que existem) em blocos de 3, tipo Strava
    const m = track?.metrics;
    const extras: { v: string; unit: string; k: string }[] = [];
    if (it.avg_hr != null) extras.push({ v: String(it.avg_hr), unit: " bpm", k: "FC média" });
    if (it.max_hr != null) extras.push({ v: String(it.max_hr), unit: " bpm", k: "FC máx" });
    if (bestSec != null) extras.push({ v: fmtPaceSec(bestSec), unit: "/km", k: "Melhor km" });
    if (m?.avg_cadence) extras.push({ v: String(m.avg_cadence), unit: " spm", k: "Cadência" });
    if (m?.avg_power) extras.push({ v: String(m.avg_power), unit: " W", k: "Potência" });
    if (m?.calories) extras.push({ v: String(m.calories), unit: " kcal", k: "Calorias" });
    if (it.elevation_gain != null) extras.push({ v: String(it.elevation_gain), unit: " m", k: "Ganho" });
    if (m?.elevation_loss) extras.push({ v: String(m.elevation_loss), unit: " m", k: "Perda" });
    if (m?.training_effect) extras.push({ v: m.training_effect.toFixed(1), unit: "", k: "Efeito aeróbico" });
    if (m?.anaerobic_effect) extras.push({ v: m.anaerobic_effect.toFixed(1), unit: "", k: "Efeito anaeróbico" });
    if (it.air_temp_c != null) extras.push({ v: String(it.air_temp_c), unit: "°C", k: "Temp." });
    else if (m?.avg_temperature != null) extras.push({ v: String(m.avg_temperature), unit: "°C", k: "Temp." });
    extras.push({ v: it.source === "app" ? "App" : "Strava/Garmin", unit: "", k: "Fonte" });
    const extraRows: typeof extras[] = [];
    for (let i = 0; i < extras.length; i += 3) extraRows.push(extras.slice(i, i + 3));
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
              <header className="appbar">
                <button className="icon-btn" aria-label="Fechar" onClick={() => { setEditor(false); setResultUrl(null); }}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
                </button>
                <div className="title"><div className="t">Compartilhar</div></div>
                <span style={{ width: 34 }} />
              </header>

              <div className="se-preview">
                <canvas ref={previewRef} className="se-canvas" />
              </div>

              <div className="se-styles">
                {CARD_STYLES.map((s, i) => (
                  <button key={s.key} className={`se-chip${i === styleIdx ? " on" : ""}`} onClick={() => setStyleIdx(i)}>{s.label}</button>
                ))}
              </div>

              <div className="se-photo">
                <button className="btn-ghost" onClick={() => fileRef.current?.click()}>
                  {photoImg ? "Trocar foto" : "📷 Adicionar sua foto"}
                </button>
                {photoImg && <button className="btn-ghost" onClick={() => setPhotoImg(null)}>Remover</button>}
              </div>

              <button className="btn se-share" onClick={shareCurrent} disabled={sharing}>
                {sharing ? "Gerando…" : "Compartilhar"}
              </button>

              {resultUrl && (
                <div className="se-result" onClick={() => setResultUrl(null)}>
                  <div className="se-result-in" onClick={(e) => e.stopPropagation()}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={resultUrl} alt="Card da corrida" />
                    <p>Segure a imagem para salvar ou compartilhar 📲</p>
                    <a className="btn" href={resultUrl} download="ritmind-corrida.jpg">Baixar imagem</a>
                    <button className="btn-ghost" onClick={() => setResultUrl(null)}>Voltar</button>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="qstats">
            <div className="qstat"><div className="v">{km(it.distance_km)}<small> km</small></div><div className="k">Distância</div></div>
            <div className="qstat"><div className="v">{it.duration_min}<small> min</small></div><div className="k">Tempo</div></div>
            <div className="qstat"><div className="v">{it.pace ?? "—"}<small>{it.pace ? "/km" : ""}</small></div><div className="k">Pace</div></div>
          </div>

          {extraRows.map((row, ri) => (
            <div className="qstats" key={ri}>
              {row.map((s, ci) => (
                <div className="qstat" key={ci}>
                  <div className="v" style={s.v.length > 6 ? { fontSize: 13.5 } : undefined}>{s.v}<small>{s.unit}</small></div>
                  <div className="k">{s.k}</div>
                </div>
              ))}
            </div>
          ))}

          {it.hr_zones && <HrZones zones={it.hr_zones} />}

          {it.has_track ? (
            loadingTrack || !track ? (
              <div className="card center"><p className="auth-sub" style={{ margin: 0 }}>Carregando traçado…</p></div>
            ) : (
              <>
                {track.points.length >= 2 && (
                  <section className="card" style={{ padding: 0, overflow: "hidden" }}><MapView points={track.points} /></section>
                )}
                {track.series?.elev?.length ? (
                  <Chart title="Altimetria" dist={track.series.dist} values={track.series.elev} color="#8B7BE8" area unit=" m" />
                ) : null}
                {track.series?.hr?.length ? (
                  <Chart title="Frequência cardíaca" dist={track.series.dist} values={track.series.hr} color="#E24666" unit=" bpm" />
                ) : null}
                {track.metrics && <RunDynamics m={track.metrics} />}
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
