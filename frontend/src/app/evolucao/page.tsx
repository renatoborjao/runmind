"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import BottomNav from "../bottom-nav";
import { getHome, type HomeSummary } from "@/lib/api";

function Mark() {
  return (
    <span className="mark" aria-hidden>
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round">
        <path d="M2 12h4l2.5-7 4 15 2.5-8H22" />
      </svg>
    </span>
  );
}

export default function EvolucaoPage() {
  const router = useRouter();
  const [home, setHome] = useState<HomeSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const h = await getHome();
      if (!h) {
        router.replace("/entrar");
        return;
      }
      setHome(h);
      setLoading(false);
    })();
  }, [router]);

  if (loading || !home) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
          <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
        </div>
      </main>
    );
  }

  const f = home.fitness;
  const projections: { label: string; value: string | null }[] = [
    { label: "5 km", value: f?.projection_5k ?? null },
    { label: "10 km", value: f?.projection_10k ?? null },
    { label: "Meia (21k)", value: f?.projection_half ?? null },
  ];
  const hasProj = projections.some((p) => p.value);

  return (
    <main className="stage">
      <div className="phone has-nav">

        <div className="topbar">
          <div className="brand"><Mark /><span className="word">Rit<b>mind</b></span></div>
        </div>

        <div className="greet">
          <h1>Evolução</h1>
          <p>O que teu corpo entrega hoje, na estimativa do Garmin.</p>
        </div>

        {f?.vo2max != null && (
          <section className="card">
            <div className="card-head"><span className="eyebrow">Potência aeróbica</span></div>
            <div className="stat" style={{ background: "transparent", padding: 0 }}>
              <div className="k">VO₂max</div>
              <div className="big" style={{ fontSize: 40 }}>{f.vo2max} <small>ml/kg/min</small></div>
            </div>
          </section>
        )}

        {hasProj && (
          <section className="card">
            <div className="card-head"><span className="eyebrow">Projeção de prova</span></div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {projections.map((p) => (
                <div key={p.label} style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", borderBottom: "1px dashed var(--line)", paddingBottom: 10 }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{p.label}</span>
                  <span className="font-mono" style={{ fontWeight: 700, fontSize: 20 }}>{p.value ?? "—"}</span>
                </div>
              ))}
            </div>
            <p className="muted" style={{ marginTop: 12, marginBottom: 0 }}>
              Estimativa de ritmo pro dia da prova com base no teu treino recente. Cai conforme você evolui. 📉
            </p>
          </section>
        )}

        {!f?.vo2max && !hasProj && (
          <section className="card center">
            <p className="muted" style={{ margin: 0 }}>
              Ainda não temos projeções — elas aparecem conforme o Garmin acumula teus treinos.
            </p>
          </section>
        )}

      </div>
      <BottomNav />
    </main>
  );
}
