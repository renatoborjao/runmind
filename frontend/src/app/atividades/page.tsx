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
        map = L.map(ref.current, { zoomControl: true, attributionControl: true, scrollWheelZoom: false });
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: "© OpenStreetMap",
        }).addTo(map);
        const line = L.polyline(pts, { color: "#0FB499", weight: 4 }).addTo(map);
        L.circleMarker(pts[0], { radius: 6, color: "#fff", weight: 2, fillColor: "#0FB499", fillOpacity: 1 }).addTo(map);
        L.circleMarker(pts[pts.length - 1], { radius: 6, color: "#fff", weight: 2, fillColor: "#E24666", fillOpacity: 1 }).addTo(map);
        map.fitBounds(line.getBounds(), { padding: [22, 22] });
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
function statCells(it: FeedItem): [string, string][] {
  const c: [string, string][] = [[it.pace ? `${it.pace}` : "—", "pace /km"], [`${it.duration_min}`, "min"]];
  if (it.avg_hr != null) c.push([`${it.avg_hr}`, "bpm"]);
  return c;
}
function header(ctx: CanvasRenderingContext2D, W: number, d: CardData) {
  markAt(ctx, 64, 100);
  ctx.font = "600 26px system-ui, sans-serif"; ctx.fillStyle = "#C9CAD6"; ctx.textAlign = "right";
  ctx.fillText(d.date, W - 64, 96); ctx.textAlign = "left";
  ctx.font = "700 32px system-ui, sans-serif"; ctx.fillStyle = "#EDEEF5";
  ctx.fillText(d.name.slice(0, 30), 64, 150);
}
function footer(ctx: CanvasRenderingContext2D, W: number, H: number) {
  ctx.fillStyle = "#8A8B9E"; ctx.font = "600 24px system-ui, sans-serif"; ctx.textAlign = "center";
  ctx.fillText("runmind.duckdns.org", W / 2, H - 28); ctx.textAlign = "left";
}

function styleClassico(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  drawBg(ctx, W, H, d.photo);
  if (d.photo) { topScrim(ctx, W); bottomScrim(ctx, W, H, H - 560); }
  header(ctx, W, d);
  if (d.pts.length >= 2) drawRouteInBox(ctx, d.pts, W - 300, 120, 236, 168, "#1FD9B8", 5);
  kmBig(ctx, 60, H - 200, d.kmTxt);
  const cells = statCells(d.it), cw = (W - 120) / cells.length;
  cells.forEach(([v, l], i) => {
    const cx = 60 + cw * i;
    ctx.fillStyle = "#FFFFFF"; ctx.font = "800 60px system-ui, sans-serif"; ctx.fillText(v, cx, H - 110);
    ctx.fillStyle = "#C9CAD6"; ctx.font = "600 28px system-ui, sans-serif"; ctx.fillText(l, cx, H - 66);
  });
  footer(ctx, W, H);
}

function styleMinimal(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  drawBg(ctx, W, H, d.photo);
  if (d.photo) topScrim(ctx, W);
  markAt(ctx, 64, 100);
  ctx.font = "600 26px system-ui, sans-serif"; ctx.fillStyle = "#C9CAD6"; ctx.textAlign = "right";
  ctx.fillText(d.date, W - 64, 96); ctx.textAlign = "left";
  const barH = 168, y = H - 64 - barH;
  roundRect(ctx, 48, y, W - 96, barH, 26); ctx.fillStyle = "rgba(10,11,18,0.72)"; ctx.fill();
  kmBig(ctx, 84, y + 106, d.kmTxt, 92);
  const line = `${d.it.pace ? d.it.pace + " /km    " : ""}${d.it.duration_min} min${d.it.avg_hr != null ? "    " + d.it.avg_hr + " bpm" : ""}`;
  ctx.fillStyle = "#EDEEF5"; ctx.font = "700 34px system-ui, sans-serif"; ctx.textAlign = "right";
  ctx.fillText(line, W - 84, y + 100); ctx.textAlign = "left";
}

function styleTrajeto(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  drawBg(ctx, W, H, d.photo);
  if (d.photo) { ctx.fillStyle = "rgba(6,7,12,0.4)"; ctx.fillRect(0, 0, W, H); }
  header(ctx, W, d);
  if (d.pts.length >= 2) drawRouteInBox(ctx, d.pts, 100, 250, 880, 700, "#1FD9B8", 11);
  else { ctx.fillStyle = "#3A3B49"; ctx.font = "600 120px system-ui, sans-serif"; ctx.textAlign = "center"; ctx.fillText("🏃", W / 2, 640); ctx.textAlign = "left"; }
  bottomScrim(ctx, W, H, H - 300);
  kmBig(ctx, 60, H - 150, d.kmTxt, 128);
  ctx.fillStyle = "#EDEEF5"; ctx.font = "700 40px system-ui, sans-serif"; ctx.textAlign = "right";
  ctx.fillText(`${d.it.pace ? d.it.pace + " /km   " : ""}${d.it.duration_min} min`, W - 64, H - 165); ctx.textAlign = "left";
  footer(ctx, W, H);
}

function styleSelo(ctx: CanvasRenderingContext2D, W: number, H: number, d: CardData) {
  drawBg(ctx, W, H, d.photo);
  const bw = 600, bh = 300, bx = 48, by = H - 56 - bh;
  roundRect(ctx, bx, by, bw, bh, 30); ctx.fillStyle = "rgba(10,11,18,0.84)"; ctx.fill();
  markAt(ctx, bx + 34, by + 64, 36);
  kmBig(ctx, bx + 34, by + 178, d.kmTxt, 96);
  ctx.fillStyle = "#C9CAD6"; ctx.font = "600 30px system-ui, sans-serif";
  ctx.fillText(`${d.it.pace ? d.it.pace + " /km · " : ""}${d.it.duration_min} min${d.it.avg_hr != null ? " · " + d.it.avg_hr + " bpm" : ""}`, bx + 34, by + 240);
  if (d.pts.length >= 2) drawRouteInBox(ctx, d.pts, W - 250, 110, 190, 150, "#1FD9B8", 5);
}

const CARD_STYLES: { key: string; label: string; draw: (c: CanvasRenderingContext2D, W: number, H: number, d: CardData) => void }[] = [
  { key: "classico", label: "Clássico", draw: styleClassico },
  { key: "minimal", label: "Minimal", draw: styleMinimal },
  { key: "trajeto", label: "Trajeto", draw: styleTrajeto },
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
    setPhotoImg(null); setStyleIdx(0); setEditor(true);
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
      const blob: Blob = await new Promise((res) => cv.toBlob((b) => res(b as Blob), "image/jpeg", 0.9));
      const file = new File([blob], "ritmind-corrida.jpg", { type: "image/jpeg" });
      const navShare = navigator as Navigator & { canShare?: (d: unknown) => boolean };
      if (navShare.canShare && navShare.canShare({ files: [file] })) {
        await navigator.share({ files: [file], text: `${km(sel.distance_km)} km no Ritmind 🏃` });
      } else {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = "ritmind-corrida.jpg"; a.click();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
      }
    } catch { /* cancelou ou indisponível */ }
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
                <button className="icon-btn" aria-label="Fechar" onClick={() => setEditor(false)}>
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
                {sharing ? "Abrindo…" : "Compartilhar"}
              </button>
            </div>
          )}

          <div className="qstats">
            <div className="qstat"><div className="v">{km(it.distance_km)}<small> km</small></div><div className="k">Distância</div></div>
            <div className="qstat"><div className="v">{it.duration_min}<small> min</small></div><div className="k">Tempo</div></div>
            <div className="qstat"><div className="v">{it.pace ?? "—"}<small>{it.pace ? "/km" : ""}</small></div><div className="k">Pace</div></div>
          </div>

          {(it.avg_hr != null || it.elevation_gain != null) && (
            <div className="qstats">
              <div className="qstat"><div className="v">{it.avg_hr ?? "—"}<small>{it.avg_hr ? " bpm" : ""}</small></div><div className="k">FC média</div></div>
              <div className="qstat"><div className="v">{it.elevation_gain ?? "—"}<small>{it.elevation_gain ? " m" : ""}</small></div><div className="k">Ganho</div></div>
              <div className="qstat"><div className="v" style={{ fontSize: 14 }}>{it.source === "app" ? "App" : "Strava/Garmin"}</div><div className="k">Fonte</div></div>
            </div>
          )}

          {it.has_track ? (
            loadingTrack || !track ? (
              <div className="card center"><p className="auth-sub" style={{ margin: 0 }}>Carregando traçado…</p></div>
            ) : (
              <>
                {track.points.length >= 2 && (
                  <section className="card" style={{ padding: 0, overflow: "hidden" }}><MapView points={track.points} /></section>
                )}
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
