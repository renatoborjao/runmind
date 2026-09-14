"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getDayDetail, type DayDetail } from "@/lib/api";

function fmtDur(min: number): string {
  const h = Math.floor(min / 60);
  const mm = min % 60;
  return h > 0 ? `${h}h${String(mm).padStart(2, "0")}` : `${mm} min`;
}

function RealizadoInner() {
  const router = useRouter();
  const params = useSearchParams();
  const dateIso = params.get("date");

  const [detail, setDetail] = useState<DayDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!dateIso) { setLoading(false); return; }
    (async () => {
      const d = await getDayDetail(dateIso);
      if (!d) { router.replace("/entrar"); return; }
      setDetail(d);
      setLoading(false);
    })();
  }, [dateIso, router]);

  if (loading) return <div className="card center"><p className="auth-sub" style={{ margin: 0 }}>Carregando…</p></div>;
  if (!detail) return <div className="card center"><p className="muted" style={{ margin: 0 }}>Treino não encontrado.</p></div>;

  const ex = detail.executed;
  const pl = detail.planned;
  const dnum = detail.date_iso.slice(-2);

  const kmDelta = ex && pl?.distance_km != null ? Math.round((ex.km - pl.distance_km) * 10) / 10 : null;

  return (
    <>
      <header className="appbar">
        <button className="icon-btn" aria-label="Voltar" onClick={() => router.push("/treino")}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
        </button>
        <div className="title"><div className="k">{detail.day_pt} · {dnum}</div><div className="t">{ex ? "Realizado" : "Planejado"}</div></div>
        <span style={{ width: 34 }} />
      </header>

      {!ex ? (
        <div className="card center">
          <p className="muted" style={{ margin: 0 }}>Nenhum treino registrado neste dia.</p>
        </div>
      ) : (
        <>
          <div>
            <div className="kicker">
              <span className="pill" style={{ color: "var(--accent-ink)", background: "var(--accent-wash)" }}>
                {ex.is_ours ? "Treino Ritmind" : "Treino avulso"}
              </span>
            </div>
            <h1>{ex.name.replace(/^.*(ritmind|runmind)\s*·?\s*/i, "").trim() || ex.name}</h1>
          </div>

          {/* o que foi feito */}
          <div className="qstats">
            <div className="qstat"><div className="v">{ex.km.toString().replace(".", ",")}<small> km</small></div><div className="k">Distância</div></div>
            <div className="qstat"><div className="v">{ex.pace ?? "—"}<small>{ex.pace ? "/km" : ""}</small></div><div className="k">Pace</div></div>
            <div className="qstat"><div className="v">{fmtDur(ex.duration_min)}</div><div className="k">Tempo</div></div>
          </div>
          <div className="qstats">
            <div className="qstat"><div className="v">{ex.avg_hr ?? "—"}<small>{ex.avg_hr ? " bpm" : ""}</small></div><div className="k">FC média</div></div>
            <div className="qstat"><div className="v">{ex.elevation_gain ?? "—"}<small>{ex.elevation_gain ? " m" : ""}</small></div><div className="k">Elevação</div></div>
            <div className="qstat"><div className="v">✓</div><div className="k">Concluído</div></div>
          </div>

          {/* planejado × executado */}
          {pl ? (
            <section className="card">
              <div className="card-head"><span className="eyebrow">Planejado × Executado</span></div>
              <div className="cmp">
                <div className="cmp-row cmp-head">
                  <span></span><span>Planejado</span><span>Feito</span>
                </div>
                <div className="cmp-row">
                  <span className="cl">Distância</span>
                  <span className="mono">{pl.distance_km != null ? `${String(pl.distance_km).replace(".", ",")} km` : "—"}</span>
                  <span className="mono">
                    {ex.km.toString().replace(".", ",")} km
                    {kmDelta !== null && kmDelta !== 0 && (
                      <b style={{ color: kmDelta > 0 ? "var(--accent-ink)" : "var(--muted)", marginLeft: 5 }}>
                        {kmDelta > 0 ? "+" : ""}{String(kmDelta).replace(".", ",")}
                      </b>
                    )}
                  </span>
                </div>
                <div className="cmp-row">
                  <span className="cl">Pace</span>
                  <span className="mono">{pl.pace_min && pl.pace_max ? `${pl.pace_min}–${pl.pace_max}` : "—"}</span>
                  <span className="mono">{ex.pace ?? "—"}</span>
                </div>
                <div className="cmp-row">
                  <span className="cl">Tipo</span>
                  <span>{pl.workout_type}</span>
                  <span>{ex.is_ours ? "✓" : "—"}</span>
                </div>
              </div>
            </section>
          ) : (
            <section className="card">
              <p className="muted" style={{ margin: 0 }}>Este treino não estava no plano da semana (avulso). 🎯</p>
            </section>
          )}
        </>
      )}
    </>
  );
}

export default function RealizadoPage() {
  return (
    <main className="stage">
      <div className="phone treino-screen">
        <Suspense fallback={<div className="card center"><p className="auth-sub" style={{ margin: 0 }}>Carregando…</p></div>}>
          <RealizadoInner />
        </Suspense>
      </div>
    </main>
  );
}
