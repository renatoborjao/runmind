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

export default function AtividadesPage() {
  const router = useRouter();
  const [feed, setFeed] = useState<FeedItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [sel, setSel] = useState<FeedItem | null>(null);
  const [track, setTrack] = useState<TrackData | null>(null);
  const [loadingTrack, setLoadingTrack] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

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

  async function doShare(cv: HTMLCanvasElement, kmTxt: string) {
    const blob: Blob = await new Promise((res) => cv.toBlob((b) => res(b as Blob), "image/jpeg", 0.9));
    const file = new File([blob], "ritmind-corrida.jpg", { type: "image/jpeg" });
    const navShare = navigator as Navigator & { canShare?: (d: unknown) => boolean };
    if (navShare.canShare && navShare.canShare({ files: [file] })) {
      await navigator.share({ files: [file], text: `${kmTxt} km no Ritmind 🏃` });
    } else {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "ritmind-corrida.jpg"; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    }
  }

  // desenha o card (com FOTO de fundo, estilo Strava, ou card escuro do Ritmind)
  async function renderCard(it: FeedItem, tk: TrackData | null, photo: HTMLImageElement | null) {
    setShareOpen(false);
    setSharing(true);
    try {
      const W = 1080, H = 1350;
      const cv = document.createElement("canvas");
      cv.width = W; cv.height = H;
      const ctx = cv.getContext("2d");
      if (!ctx) { setSharing(false); return; }
      ctx.textBaseline = "alphabetic";
      const pts = tk?.points || [];

      if (photo) {
        // foto cobrindo o quadro (cover-fit)
        const s = Math.max(W / photo.width, H / photo.height);
        const dw = photo.width * s, dh = photo.height * s;
        ctx.drawImage(photo, (W - dw) / 2, (H - dh) / 2, dw, dh);
        // escurece topo e base pra leitura
        const gTop = ctx.createLinearGradient(0, 0, 0, 240);
        gTop.addColorStop(0, "rgba(6,7,12,0.75)"); gTop.addColorStop(1, "rgba(6,7,12,0)");
        ctx.fillStyle = gTop; ctx.fillRect(0, 0, W, 240);
        const gBot = ctx.createLinearGradient(0, H - 560, 0, H);
        gBot.addColorStop(0, "rgba(6,7,12,0)"); gBot.addColorStop(0.55, "rgba(6,7,12,0.78)"); gBot.addColorStop(1, "rgba(6,7,12,0.96)");
        ctx.fillStyle = gBot; ctx.fillRect(0, H - 560, W, 560);
        // traçado pequeno no canto superior direito
        if (pts.length >= 2) drawRouteInBox(ctx, pts, W - 300, 120, 236, 168, "#1FD9B8", 5);
      } else {
        ctx.fillStyle = "#0C0D16"; ctx.fillRect(0, 0, W, H);
        // traçado grande no meio
        if (pts.length >= 2) drawRouteInBox(ctx, pts, 90, 250, 900, 640, "#1FD9B8", 8);
        else {
          ctx.fillStyle = "#3A3B49"; ctx.font = "600 120px system-ui, sans-serif"; ctx.textAlign = "center";
          ctx.fillText("🏃", W / 2, 620); ctx.textAlign = "left";
        }
      }

      // marca + data + nome
      ctx.font = "800 46px system-ui, -apple-system, Segoe UI, sans-serif";
      ctx.fillStyle = "#1FD9B8"; ctx.fillText("Rit", 64, 100);
      const rw = ctx.measureText("Rit").width;
      ctx.fillStyle = "#FFFFFF"; ctx.fillText("mind", 64 + rw, 100);
      ctx.font = "600 26px system-ui, sans-serif"; ctx.fillStyle = "#C9CAD6";
      ctx.textAlign = "right"; ctx.fillText(fmtDate(it.datetime ?? it.date_iso), W - 64, 96); ctx.textAlign = "left";
      ctx.font = "700 32px system-ui, sans-serif"; ctx.fillStyle = "#EDEEF5";
      ctx.fillText((it.name || "Corrida").slice(0, 30), 64, 150);

      // bloco de stats (ancorado embaixo)
      const kmTxt = km(it.distance_km);
      ctx.fillStyle = "#1FD9B8"; ctx.font = "800 150px system-ui, sans-serif";
      ctx.fillText(kmTxt, 60, H - 200);
      const kmW = ctx.measureText(kmTxt).width;
      ctx.fillStyle = "#C9CAD6"; ctx.font = "600 40px system-ui, sans-serif";
      ctx.fillText(" km", 60 + kmW + 8, H - 200);

      const cells: [string, string][] = [
        [it.pace ? `${it.pace}` : "—", "pace /km"],
        [`${it.duration_min}`, "min"],
      ];
      if (it.avg_hr != null) cells.push([`${it.avg_hr}`, "bpm"]);
      const cw = (W - 120) / cells.length;
      cells.forEach(([v, l], i) => {
        const cx = 60 + cw * i;
        ctx.fillStyle = "#FFFFFF"; ctx.font = "800 60px system-ui, sans-serif";
        ctx.fillText(v, cx, H - 110);
        ctx.fillStyle = "#C9CAD6"; ctx.font = "600 28px system-ui, sans-serif";
        ctx.fillText(l, cx, H - 66);
      });
      ctx.fillStyle = "#7C7D8C"; ctx.font = "600 24px system-ui, sans-serif"; ctx.textAlign = "center";
      ctx.fillText("runmind.duckdns.org", W / 2, H - 28); ctx.textAlign = "left";

      await doShare(cv, kmTxt);
    } catch { /* cancelou ou indisponível */ }
    setSharing(false);
  }

  function onPickPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !sel) return;
    const img = new Image();
    img.onload = () => renderCard(sel, track, img);
    img.onerror = () => renderCard(sel, track, null);
    img.src = URL.createObjectURL(file);
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
            <button className="icon-btn" aria-label="Compartilhar" onClick={() => setShareOpen(true)} disabled={sharing}>
              {sharing ? (
                <span style={{ fontSize: 12 }}>…</span>
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.1} strokeLinecap="round" strokeLinejoin="round"><circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" /><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4" /></svg>
              )}
            </button>
          </header>

          <input ref={fileRef} type="file" accept="image/*" hidden onChange={onPickPhoto} />

          {shareOpen && (
            <div className="share-overlay" onClick={() => setShareOpen(false)}>
              <div className="share-sheet" onClick={(e) => e.stopPropagation()}>
                <div className="ss-title">Compartilhar corrida</div>
                <button className="ss-opt" onClick={() => fileRef.current?.click()}>
                  <span className="ss-ic">📷</span>
                  <span><b>Com sua foto</b><small>Stats e trajeto por cima da foto</small></span>
                </button>
                <button className="ss-opt" onClick={() => renderCard(it, track, null)}>
                  <span className="ss-ic">🎨</span>
                  <span><b>Card do Ritmind</b><small>Fundo do app, sem foto</small></span>
                </button>
                <button className="ss-cancel" onClick={() => setShareOpen(false)}>Cancelar</button>
              </div>
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
