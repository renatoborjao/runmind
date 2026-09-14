"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getRecordedRun,
  getRecordedRuns,
  type RecordedRunDetail,
  type RecordedRunSummary,
} from "@/lib/api";

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}

function fmtTime(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function fmtDur(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = Math.floor(s % 60);
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${String(ss).padStart(2, "0")}` : `${m}:${String(ss).padStart(2, "0")}`;
}

function km(m: number): string {
  return (m / 1000).toFixed(2).replace(".", ",");
}

// Traçado do GPS como polyline (sem mapa base — só a forma do percurso).
function TrackMap({ points }: { points: { lat: number; lon: number }[] }) {
  const pts = points.filter((p) => p.lat && p.lon);
  if (pts.length < 2) return null;
  const lats = pts.map((p) => p.lat), lons = pts.map((p) => p.lon);
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const minLon = Math.min(...lons), maxLon = Math.max(...lons);
  const meanLat = (minLat + maxLat) / 2;
  const kx = Math.cos((meanLat * Math.PI) / 180); // corrige longitude pela latitude
  const W = 320, H = 200, pad = 16;
  const spanX = (maxLon - minLon) * kx || 1e-6;
  const spanY = (maxLat - minLat) || 1e-6;
  const scale = Math.min((W - 2 * pad) / spanX, (H - 2 * pad) / spanY);
  const ox = (W - spanX * scale) / 2;
  const oy = (H - spanY * scale) / 2;
  const X = (lon: number) => ox + (lon - minLon) * kx * scale;
  const Y = (lat: number) => H - (oy + (lat - minLat) * scale); // inverte y
  const d = pts.map((p) => `${X(p.lon).toFixed(1)},${Y(p.lat).toFixed(1)}`).join(" ");
  const first = pts[0], last = pts[pts.length - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label="Traçado da corrida" style={{ display: "block" }}>
      <polyline points={d} fill="none" stroke="var(--accent)" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={X(first.lon)} cy={Y(first.lat)} r="5" fill="var(--accent)" stroke="var(--surface)" strokeWidth="2" />
      <circle cx={X(last.lon)} cy={Y(last.lat)} r="5" fill="var(--rose)" stroke="var(--surface)" strokeWidth="2" />
    </svg>
  );
}

export default function CorridasPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<RecordedRunSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<RecordedRunDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    (async () => {
      const r = await getRecordedRuns();
      if (r === null) { router.replace("/entrar"); return; }
      setRuns(r);
      setLoading(false);
    })();
  }, [router]);

  async function open(id: string) {
    setLoadingDetail(true);
    setDetail(await getRecordedRun(id));
    setLoadingDetail(false);
  }

  if (loading || !runs) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
          <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
        </div>
      </main>
    );
  }

  // TELA: detalhe da corrida
  if (detail || loadingDetail) {
    const d = detail;
    const maxPace = d ? Math.max(...d.splits.map((s) => s.sec / (s.partial_km || 1)), 1) : 1;
    return (
      <main className="stage">
        <div className="phone">
          <header className="appbar">
            <button className="icon-btn" aria-label="Voltar" onClick={() => setDetail(null)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
            </button>
            <div className="title"><div className="t">{d ? fmtDate(d.started_at ?? d.saved_at) : "Corrida"}</div></div>
            <span style={{ width: 34 }} />
          </header>

          {!d ? (
            <div className="card center"><p className="auth-sub" style={{ margin: 0 }}>Carregando…</p></div>
          ) : (
            <>
              <div className="qstats">
                <div className="qstat"><div className="v">{km(d.distance_m)}<small> km</small></div><div className="k">Distância</div></div>
                <div className="qstat"><div className="v">{fmtDur(d.duration_s)}</div><div className="k">Tempo</div></div>
                <div className="qstat"><div className="v">{d.avg_pace ?? "—"}<small>{d.avg_pace ? "/km" : ""}</small></div><div className="k">Pace médio</div></div>
              </div>

              {d.points.length >= 2 && (
                <section className="card" style={{ padding: 12 }}>
                  <TrackMap points={d.points} />
                </section>
              )}

              {d.splits.length > 0 && (
                <section className="card">
                  <div className="card-head"><span className="eyebrow">Parciais por km</span></div>
                  <div className="splits">
                    {d.splits.map((s, i) => {
                      const paceSec = s.sec / (s.partial_km || 1);
                      const w = Math.max(8, Math.round((maxPace ? (paceSec / maxPace) : 1) * 100));
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

              <p className="muted center" style={{ marginTop: 2, fontSize: 12 }}>Gravada no app · {fmtTime(d.started_at ?? d.saved_at)}</p>
            </>
          )}
        </div>
      </main>
    );
  }

  // TELA: lista
  return (
    <main className="stage">
      <div className="phone">
        <header className="appbar">
          <button className="icon-btn" aria-label="Voltar" onClick={() => router.push("/inicio")}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <div className="title"><div className="t">Minhas corridas</div></div>
          <span style={{ width: 34 }} />
        </header>

        <button className="btn-primary" style={{ marginBottom: 4 }} onClick={() => router.push("/correr")}>
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><polygon points="10 8 16 12 10 16 10 8" fill="currentColor" stroke="none" /></svg>
          Correr agora (GPS)
        </button>

        {runs.length === 0 ? (
          <div className="card center">
            <p className="muted" style={{ margin: 0 }}>Você ainda não gravou nenhuma corrida pelo app. Toca em <b>Correr agora</b> pra começar. 🏃</p>
          </div>
        ) : (
          runs.map((r) => (
            <section key={r.id} className="card tap" onClick={() => open(r.id)}>
              <div className="run-row">
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="rr-date">{fmtDate(r.started_at ?? r.saved_at)} · {fmtTime(r.started_at ?? r.saved_at)}</div>
                  <div className="rr-km">{km(r.distance_m)} km</div>
                  <div className="rr-meta">{fmtDur(r.duration_s)} · {r.avg_pace ?? "—"}/km</div>
                </div>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M9 6l6 6-6 6" /></svg>
              </div>
            </section>
          ))
        )}
      </div>
    </main>
  );
}
