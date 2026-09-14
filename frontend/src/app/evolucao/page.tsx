"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import BottomNav from "../bottom-nav";
import { getProgress, type Progress } from "@/lib/api";

function Mark() {
  return (
    <span className="mark" aria-hidden>
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round"><path d="M2 12h4l2.5-7 4 15 2.5-8H22" /></svg>
    </span>
  );
}

function VolumeChart({ data }: { data: { label: string; km: number }[] }) {
  const W = 340, H = 130, padB = 22, padT = 10;
  const max = Math.max(10, ...data.map((d) => d.km));
  const n = data.length;
  const gap = 8;
  const bw = (W - gap * (n - 1)) / n;
  return (
    <div style={{ overflowX: "auto" }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="xMidYMid meet" role="img" aria-label="Volume semanal">
        {data.map((d, i) => {
          const h = d.km > 0 ? ((H - padB - padT) * d.km) / max : 0;
          const x = i * (bw + gap);
          const y = H - padB - h;
          const last = i === n - 1;
          return (
            <g key={i}>
              {d.km > 0 && (
                <text x={x + bw / 2} y={y - 4} textAnchor="middle" fontSize="9" fontFamily="var(--font-mono)" fill="var(--ink-soft)">{d.km}</text>
              )}
              <rect x={x} y={y} width={bw} height={Math.max(h, 1)} rx="3"
                fill={last ? "var(--muted)" : "var(--accent)"} opacity={last ? 0.5 : 1} />
              <text x={x + bw / 2} y={H - 7} textAnchor="middle" fontSize="8" fontFamily="var(--font-mono)" fill="var(--muted)">{d.label}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default function EvolucaoPage() {
  const router = useRouter();
  const [p, setP] = useState<Progress | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const data = await getProgress();
      if (!data) { router.replace("/entrar"); return; }
      setP(data);
      setLoading(false);
    })();
  }, [router]);

  if (loading || !p) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
          <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
        </div>
      </main>
    );
  }

  const f = p.fitness;
  const proj: { label: string; value: string | null }[] = [
    { label: "5 km", value: f.projection_5k },
    { label: "10 km", value: f.projection_10k },
    { label: "Meia", value: f.projection_half },
    { label: "Maratona", value: f.projection_marathon },
  ];
  const hasProj = proj.some((x) => x.value);
  const sinceLabel = p.journey.since ? new Date(p.journey.since + "T00:00:00").toLocaleDateString("pt-BR", { month: "short", year: "numeric" }) : null;

  return (
    <main className="stage">
      <div className="phone has-nav">

        <div className="topbar">
          <div className="brand"><Mark /><span className="word">Rit<b>mind</b></span></div>
        </div>

        <div className="greet">
          <h1>Evolução</h1>
        </div>

        {/* jornada */}
        <section className="card">
          <div className="card-head"><span className="eyebrow">Sua jornada no Ritmind</span></div>
          <div className="prog-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
            <div className="stat"><div className="k">Km total</div><div className="big">{p.journey.km_total}</div></div>
            <div className="stat"><div className="k">Treinos</div><div className="big">{p.journey.runs}</div></div>
            <div className="stat"><div className="k">Maior</div><div className="big">{String(p.journey.biggest_km).replace(".", ",")}<small> km</small></div></div>
          </div>
          {sinceLabel && <p className="muted" style={{ margin: "12px 0 0", textTransform: "capitalize" }}>desde {sinceLabel} 🏃</p>}
        </section>

        {/* volume semanal */}
        <section className="card">
          <div className="card-head"><span className="eyebrow">Volume por semana (km)</span></div>
          <VolumeChart data={p.weekly_volume} />
        </section>

        {/* forma: vo2 + fc */}
        {(f.vo2max != null || f.resting_hr != null) && (
          <section className="card">
            <div className="card-head"><span className="eyebrow">Forma</span></div>
            <div className="prog-grid">
              {f.vo2max != null && <div className="stat"><div className="k">VO₂max</div><div className="big">{f.vo2max} <small>ml/kg</small></div></div>}
              {f.resting_hr != null && <div className="stat"><div className="k">FC repouso</div><div className="big">{f.resting_hr} <small>bpm</small></div></div>}
            </div>
          </section>
        )}

        {/* projeções */}
        {hasProj && (
          <section className="card">
            <div className="card-head"><span className="eyebrow">Projeção de prova</span></div>
            <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
              {proj.map((x) => (
                <div key={x.label} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "10px 0", borderBottom: "1px dashed var(--line)" }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{x.label}</span>
                  <span className="font-mono" style={{ fontWeight: 700, fontSize: 18 }}>{x.value ?? "—"}</span>
                </div>
              ))}
            </div>
            <p className="muted" style={{ marginTop: 12, marginBottom: 0 }}>Estimativa do Garmin pro teu ritmo hoje — cai conforme você evolui. 📉</p>
          </section>
        )}

      </div>
      <BottomNav />
    </main>
  );
}
