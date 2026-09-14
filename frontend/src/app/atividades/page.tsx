"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import BottomNav from "../bottom-nav";
import {
  getFeed,
  getTrack,
  type FeedItem,
  type TrackData,
} from "@/lib/api";

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

// Traçado do GPS como polyline (sem mapa base — só a forma do percurso).
function TrackMap({ points }: { points: { lat: number; lon: number }[] }) {
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

export default function AtividadesPage() {
  const router = useRouter();
  const [feed, setFeed] = useState<FeedItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [sel, setSel] = useState<FeedItem | null>(null);
  const [track, setTrack] = useState<TrackData | null>(null);
  const [loadingTrack, setLoadingTrack] = useState(false);

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
            <span style={{ width: 34 }} />
          </header>

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
                  <section className="card" style={{ padding: 12 }}><TrackMap points={track.points} /></section>
                )}
                {track.splits.length > 0 && (
                  <section className="card">
                    <div className="card-head"><span className="eyebrow">Parciais por km</span></div>
                    <div className="splits">
                      {track.splits.map((s, i) => {
                        const paceSec = s.sec / (s.partial_km || 1);
                        const w = Math.max(8, Math.round((paceSec / maxPace) * 100));
                        return (
                          <div className="split" key={i}>
                            <span className="sk">{s.km ?? `${String(s.partial_km).replace(".", ",")}`}<small>{s.km ? "" : " km"}</small></span>
                            <span className="sbar"><i style={{ width: `${w}%` }} /></span>
                            <span className="sp">{s.pace ?? "—"}<small>/km</small></span>
                          </div>
                        );
                      })}
                    </div>
                  </section>
                )}
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
