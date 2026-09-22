"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getStrengthLibrary, getStrengthRoutine, type StrengthExercise, type StrengthLibrary, type StrengthRoutine } from "@/lib/api";

// Demonstração: alterna os 2 quadros (início/fim) do movimento = um "GIF"
// simples. Se a imagem não carregar (CDN fora/off-line), mostra um selo neutro.
function ExerciseDemo({ images, alt }: { images: string[]; alt: string }) {
  const [frame, setFrame] = useState(0);
  const [broken, setBroken] = useState(false);
  const two = images.length >= 2 && !broken;

  useEffect(() => {
    if (!two) return;
    const id = setInterval(() => setFrame((f) => (f === 0 ? 1 : 0)), 850);
    return () => clearInterval(id);
  }, [two]);

  if (broken || images.length === 0) {
    return (
      <div className="ex-demo ex-demo-ph" aria-label={alt}>
        <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="var(--muted)" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round"><path d="M6 10v4M18 10v4M4 12h2M18 12h2M8 9h1a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2H8zM16 9h-1a2 2 0 0 0-2 2v2a2 2 0 0 0 2 2h1" /></svg>
      </div>
    );
  }
  return (
    <div className="ex-demo">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={images[two ? frame : 0]} alt={alt} onError={() => setBroken(true)} />
    </div>
  );
}

function ExerciseCard({ ex, prescription }: { ex: StrengthExercise; prescription?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="card ex-card">
      <button className="ex-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <ExerciseDemo images={ex.images} alt={ex.name} />
        <div className="ex-info">
          <div className="ex-name">{ex.name}</div>
          <div className="ex-meta"><span>{ex.target}</span></div>
          <div className="ex-badges">
            <span className="ex-badge">{ex.equipment}</span>
            <span className="ex-badge reps">{prescription ?? ex.reps}</span>
          </div>
        </div>
        <svg className={`ex-chev${open ? " open" : ""}`} viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M6 9l6 6 6-6" /></svg>
      </button>
      {open && (
        <div className="ex-body">
          <p className="ex-why">{ex.why}</p>
          <div className="ex-cues-t">Como fazer</div>
          <ol className="ex-cues">
            {ex.cues.map((c, i) => <li key={i}>{c}</li>)}
          </ol>
          {ex.breathing && <p className="ex-breath">🌬️ {ex.breathing}</p>}
          {ex.feel_where && <div className="ex-tip feel"><b>🎯 Onde sentir</b><span>{ex.feel_where}</span></div>}
          {ex.common_mistake && <div className="ex-tip mistake"><b>⚠️ Erro comum</b><span>{ex.common_mistake}</span></div>}
          {(ex.regression || ex.progression) && (
            <div className="ex-levels">
              {ex.regression && <div className="lvl"><span className="lvl-t">Mais fácil</span>{ex.regression}</div>}
              {ex.progression && <div className="lvl"><span className="lvl-t">Mais difícil</span>{ex.progression}</div>}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export default function FortalecimentoPage() {
  const router = useRouter();
  const [lib, setLib] = useState<StrengthLibrary | null>(null);
  const [routine, setRoutine] = useState<StrengthRoutine | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        // rotina do coach é best-effort (não derruba a tela se faltar sessão)
        const [data, rout] = await Promise.all([getStrengthLibrary(), getStrengthRoutine()]);
        if (!alive) return;
        if (!data) { setFailed(true); setLoading(false); return; }
        setLib(data);
        setRoutine(rout);
        setLoading(false);
      } catch {
        if (alive) { setFailed(true); setLoading(false); }
      }
    })();
    return () => { alive = false; };
  }, [attempt]);

  if (failed) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1, gap: 14 }}>
          <p className="auth-sub" style={{ margin: 0, textAlign: "center" }}>Não consegui carregar os exercícios agora.</p>
          <button className="btn-primary" onClick={() => { setFailed(false); setLoading(true); setAttempt((n) => n + 1); }}>Tentar de novo</button>
        </div>
      </main>
    );
  }

  if (loading || !lib) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
          <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
        </div>
      </main>
    );
  }

  return (
    <main className="stage">
      <div className="phone">
        <header className="appbar">
          <button className="icon-btn" aria-label="Voltar" onClick={() => router.push("/inicio")}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <div className="title"><div className="t">Fortalecimento</div></div>
          <span style={{ width: 34 }} />
        </header>

        {routine && routine.exercises.length > 0 && (
          <div className="routine-block">
            <div className="routine-head">
              <span className="eyebrow">Sua rotina · o coach montou</span>
              <div className="routine-days">
                {routine.days_pt.map((d) => <span key={d} className="rday">{d}</span>)}
                <span className="rfreq">{routine.frequency}x/semana</span>
              </div>
            </div>
            <p className="routine-note">{routine.note}</p>
            {routine.exercises.map((ex) => (
              <ExerciseCard key={ex.id} ex={ex} prescription={ex.prescription} />
            ))}
          </div>
        )}

        <div className="card intro-card">
          <div className="lib-t">Biblioteca completa</div>
          <p style={{ margin: 0 }}>Todos os exercícios de força pra quem corre — <b>glúteo, core, pernas e panturrilha</b>. Peso do corpo ou faixa, dá pra fazer em casa. Toque pra ver como fazer. 💪</p>
        </div>

        {lib.categories.map((cat) => {
          const list = lib.exercises.filter((e) => e.category === cat);
          if (!list.length) return null;
          return (
            <div key={cat} className="ex-cat">
              <div className="ex-cat-t">{cat}</div>
              {list.map((ex) => <ExerciseCard key={ex.id} ex={ex} />)}
            </div>
          );
        })}

        <p className="muted center" style={{ fontSize: 11.5, marginTop: 4 }}>{lib.credit}</p>
      </div>
    </main>
  );
}
