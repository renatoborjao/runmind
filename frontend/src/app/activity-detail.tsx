"use client";

// Corpo do detalhe de uma atividade (mapa + stats + zonas de FC + gráficos +
// parciais), COMPARTILHADO entre a minha atividade (/atividades) e a de um amigo
// (/atleta/atividade). A análise do coach NÃO mora aqui — ela é privada de cada
// atleta e entra só na minha tela, via `analysisSlot`. Assim o amigo vê a corrida
// igual Strava, sem nunca ver a leitura do coach.

import { useEffect, useRef, useState } from "react";
import type { FeedItem, TrackData } from "@/lib/api";

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

export function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}
export function fmtTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}
export function km(v: number): string {
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

/** Miniatura do traçado (só a linha, sem mapa base) pros cards do feed — usa o
 * `route_preview` leve que o backend manda junto, sem puxar o traçado completo.
 * Estilo Strava: silhueta do percurso num relance. */
export function RouteThumb({ route, className }: { route?: [number, number][] | null; className?: string }) {
  if (!route || route.length < 2) return null;
  const lats = route.map((p) => p[0]), lons = route.map((p) => p[1]);
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const minLon = Math.min(...lons), maxLon = Math.max(...lons);
  const kx = Math.cos(((minLat + maxLat) / 2 * Math.PI) / 180);
  const W = 120, H = 72, pad = 8;
  const spanX = (maxLon - minLon) * kx || 1e-6;
  const spanY = (maxLat - minLat) || 1e-6;
  const scale = Math.min((W - 2 * pad) / spanX, (H - 2 * pad) / spanY);
  const ox = (W - spanX * scale) / 2, oy = (H - spanY * scale) / 2;
  const X = (lon: number) => ox + (lon - minLon) * kx * scale;
  const Y = (lat: number) => H - (oy + (lat - minLat) * scale);
  const d = route.map((p) => `${X(p[1]).toFixed(1)},${Y(p[0]).toFixed(1)}`).join(" ");
  const first = route[0], last = route[route.length - 1];
  return (
    <svg className={className} viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label="Percurso" preserveAspectRatio="xMidYMid meet">
      <polyline points={d} fill="none" stroke="var(--accent)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={X(first[1])} cy={Y(first[0])} r="3.2" fill="var(--accent)" />
      <circle cx={X(last[1])} cy={Y(last[0])} r="3.2" fill="var(--rose)" />
    </svg>
  );
}

/** Corpo do detalhe da atividade — igual pra minha corrida e pra do amigo.
 * `analysisSlot` é injetado só na MINHA tela (a análise do coach é privada). */
export function ActivityDetailBody({ item, track, loadingTrack, analysisSlot, photoUrl }: {
  item: FeedItem;
  track: TrackData | null;
  loadingTrack: boolean;
  analysisSlot?: React.ReactNode;
  photoUrl?: string | null;
}) {
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

  // GRID principal: só 3 tiles glanceáveis (além de dist/tempo/ritmo).
  const primary: { v: string; unit: string; k: string }[] = [];
  if (item.avg_hr != null) primary.push({ v: String(item.avg_hr), unit: " bpm", k: "FC média" });
  if (m?.avg_cadence) primary.push({ v: String(m.avg_cadence), unit: " spm", k: "Cadência" });
  if (item.elevation_gain != null) primary.push({ v: String(item.elevation_gain), unit: " m", k: "Ganho" });
  if (primary.length < 3 && m?.calories) primary.push({ v: String(m.calories), unit: " kcal", k: "Calorias" });
  if (primary.length < 3 && m?.avg_power) primary.push({ v: String(m.avg_power), unit: " W", k: "Potência" });

  // DETALHES: lista compacta (rótulo — valor), só o que existe
  const details: [string, string][] = [];
  if (item.max_hr != null) details.push(["FC máxima", `${item.max_hr} bpm`]);
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
  const temp = item.air_temp_c ?? m?.avg_temperature;
  if (temp != null) details.push(["Temperatura", `${temp} °C`]);

  return (
    <>
      {/* FOTO do atleta (herói), quando houver — estilo Strava */}
      {photoUrl && (
        // eslint-disable-next-line @next/next/no-img-element
        <img className="act-photo" src={photoUrl} alt="Foto da corrida" />
      )}

      {/* MAPA no topo (herói), estilo Strava */}
      {item.has_track && track && track.points.length >= 2 && (
        <section className="map-section map-hero"><MapView points={track.points} /></section>
      )}

      <div className="qstats">
        <div className="qstat"><div className="v">{km(item.distance_km)}<small> km</small></div><div className="k">Distância</div></div>
        <div className="qstat"><div className="v">{item.duration_min}<small> min</small></div><div className="k">Tempo</div></div>
        <div className="qstat"><div className="v">{item.pace ?? "—"}<small>{item.pace ? "/km" : ""}</small></div><div className="k">Pace</div></div>
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

      {analysisSlot}

      {item.hr_zones && <HrZones zones={item.hr_zones} />}

      {item.has_track ? (
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

      <p className="det-src">Fonte: {item.source === "app" ? "GPS do app" : "Strava/Garmin"}</p>
    </>
  );
}
