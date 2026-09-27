"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { completeOnboarding, getMe, getProfile, stravaConnectUrl, type OnboardingPayload } from "@/lib/api";

const DAYS = [
  { i: 0, label: "Seg" },
  { i: 1, label: "Ter" },
  { i: 2, label: "Qua" },
  { i: 3, label: "Qui" },
  { i: 4, label: "Sex" },
  { i: 5, label: "Sáb" },
  { i: 6, label: "Dom" },
];

type Form = {
  name: string;
  age: string;
  sex: "M" | "F" | null;
  weight: string;
  height: string;
  runsToday: boolean | null;
  runsPerWeek: string;
  typicalKm: string;
  paceDist: string;
  paceMin: string;
  mobility: "walker" | "run_walker" | "runner" | null;
  goalKind: "health" | "race" | null;
  race: string;
  targetTime: string;
  raceDate: string;
  days: number[];
  externalCoach: boolean | null;
};

const EMPTY: Form = {
  name: "", age: "", sex: null, weight: "", height: "",
  runsToday: null, runsPerWeek: "", typicalKm: "", paceDist: "", paceMin: "",
  mobility: null, goalKind: null, race: "", targetTime: "", raceDate: "",
  days: [], externalCoach: null,
};

// passos: cada um valida pra liberar o "Próximo"
const STEPS = ["nome", "corpo", "experiencia", "objetivo", "dias", "treinador", "strava", "revisao"] as const;
type StepKey = (typeof STEPS)[number];

// Rascunho do cadastro: conectar o Strava sai do app (OAuth) e volta — sem
// isso o atleta perderia tudo que já preencheu. Best-effort (modo privado etc.).
const DRAFT_KEY = "ritmind_onboarding_draft";

function loadDraft(): { f: Form; i: number } | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}
function saveDraft(f: Form, i: number) {
  try { localStorage.setItem(DRAFT_KEY, JSON.stringify({ f, i })); } catch { /* sem storage: segue */ }
}
function clearDraft() {
  try { localStorage.removeItem(DRAFT_KEY); } catch { /* idem */ }
}

export default function OnboardingPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [i, setI] = useState(0);
  const [f, setF] = useState<Form>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [strava, setStrava] = useState(false);

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((p) => ({ ...p, [k]: v }));

  // guarda: precisa estar logado; se já completou, vai pro início
  useEffect(() => {
    (async () => {
      const me = await getMe();
      if (!me) { router.replace("/entrar"); return; }
      if (me.onboarding_complete) { clearDraft(); router.replace("/inicio"); return; }
      const draft = loadDraft();
      if (draft?.f) {
        setF({ ...EMPTY, ...draft.f });
        setI(Math.min(Math.max(draft.i ?? 0, 0), STEPS.length - 1));
      } else if (me.name) {
        setF((p) => ({ ...p, name: p.name || me.name }));
      }
      // volta do Strava: ?strava=ok|erro (limpa a URL depois de ler)
      const result = new URLSearchParams(window.location.search).get("strava");
      if (result) {
        if (result === "erro") setErr("Não consegui conectar o Strava. Tenta de novo ou pula por agora.");
        router.replace("/onboarding");
      }
      const prof = await getProfile();
      setStrava(!!prof?.strava_connected || result === "ok");
      setReady(true);
    })();
  }, [router]);

  // guarda o rascunho a cada passo/resposta
  useEffect(() => { if (ready) saveDraft(f, i); }, [ready, f, i]);

  const step: StepKey = STEPS[i];

  const canNext = useMemo(() => {
    const ageN = parseInt(f.age);
    const wN = parseFloat(f.weight.replace(",", "."));
    const hN = parseFloat(f.height.replace(",", "."));
    switch (step) {
      case "nome": return f.name.trim().length >= 2;
      case "corpo":
        return ageN >= 10 && ageN <= 100 && f.sex != null
          && wN >= 30 && wN <= 250 && hN >= 1.2 && hN <= 2.3;
      case "experiencia":
        if (f.runsToday == null) return false;
        if (f.runsToday) {
          const d = parseFloat(f.paceDist.replace(",", "."));
          const m = parseFloat(f.paceMin.replace(",", "."));
          return parseInt(f.runsPerWeek) >= 1 && parseFloat(f.typicalKm.replace(",", ".")) > 0 && d > 0 && m > 0;
        }
        return f.mobility != null;
      case "objetivo":
        if (f.goalKind == null) return false;
        if (f.goalKind === "race") return f.race.trim().length >= 2;
        return true;
      case "dias": return f.days.length >= 1;
      case "treinador": return f.externalCoach != null;
      case "strava": return true; // opcional: dá pra pular
      case "revisao": return true;
    }
  }, [step, f]);

  function next() {
    setErr("");
    if (i < STEPS.length - 1) setI(i + 1);
  }
  function back() {
    setErr("");
    if (i > 0) setI(i - 1);
  }

  function toggleDay(d: number) {
    set("days", f.days.includes(d) ? f.days.filter((x) => x !== d) : [...f.days, d].sort((a, b) => a - b));
  }

  async function finish() {
    setSaving(true);
    setErr("");
    const num = (s: string) => parseFloat(s.replace(",", "."));
    const goal = f.goalKind === "race"
      ? (f.targetTime.trim() ? `${f.race.trim()} em ${f.targetTime.trim()}` : f.race.trim())
      : "saúde e condicionamento";
    const payload: OnboardingPayload = {
      name: f.name.trim(),
      age: parseInt(f.age),
      sex: f.sex,
      weight: num(f.weight),
      height: num(f.height),
      days: f.days,
      goal,
      target_race: f.goalKind === "race" ? f.race.trim() : null,
      target_time: f.goalKind === "race" && f.targetTime.trim() ? f.targetTime.trim() : null,
      race_date: f.goalKind === "race" && f.raceDate ? f.raceDate : null,
      runs_today: !!f.runsToday,
      runs_per_week: f.runsToday ? parseInt(f.runsPerWeek) : null,
      typical_km: f.runsToday ? num(f.typicalKm) : null,
      pace_distance_km: f.runsToday ? num(f.paceDist) : null,
      pace_minutes: f.runsToday ? num(f.paceMin) : null,
      mobility: f.runsToday ? null : f.mobility,
      external_coach: !!f.externalCoach,
    };
    const res = await completeOnboarding(payload);
    if (res.ok) {
      clearDraft();
      router.replace("/inicio");
    } else {
      setErr(res.error || "Não consegui finalizar.");
      setSaving(false);
    }
  }

  if (!ready) {
    return (
      <main className="stage">
        <div className="phone" style={{ justifyContent: "center", flex: 1 }}>
          <div className="card center"><p className="auth-sub" style={{ margin: 0 }}>Carregando…</p></div>
        </div>
      </main>
    );
  }

  const firstName = (f.name.trim().split(" ")[0]) || "corredor";

  return (
    <main className="stage">
      <div className="phone" style={{ flex: 1, maxWidth: 440 }}>
        <div className="card" style={{ marginTop: 18 }}>
          <div className="wz-prog"><i style={{ width: `${((i + 1) / STEPS.length) * 100}%` }} /></div>
          <div className="wz-k">Passo {i + 1} de {STEPS.length}</div>

          {step === "nome" && (
            <>
              <h1 className="wz-h">Bora montar seu treino. Como te chamo?</h1>
              <p className="wz-sub">Seu primeiro nome já resolve.</p>
              <div className="field">
                <label htmlFor="name">Seu nome</label>
                <input id="name" value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="Ex.: Renato" autoFocus />
              </div>
            </>
          )}

          {step === "corpo" && (
            <>
              <h1 className="wz-h">Prazer, {firstName}! Uns dados rápidos.</h1>
              <p className="wz-sub">É pra calibrar a intensidade dos treinos.</p>
              <div className="wz-row">
                <div className="field">
                  <label htmlFor="age">Idade</label>
                  <input id="age" inputMode="numeric" value={f.age} onChange={(e) => set("age", e.target.value)} placeholder="30" />
                </div>
                <div className="field">
                  <label>Sexo</label>
                  <div className="wz-chips">
                    <button type="button" className={`wz-chip ${f.sex === "M" ? "sel" : ""}`} onClick={() => set("sex", "M")}>Homem</button>
                    <button type="button" className={`wz-chip ${f.sex === "F" ? "sel" : ""}`} onClick={() => set("sex", "F")}>Mulher</button>
                  </div>
                </div>
              </div>
              <div className="wz-row">
                <div className="field">
                  <label htmlFor="w">Peso (kg)</label>
                  <input id="w" inputMode="decimal" value={f.weight} onChange={(e) => set("weight", e.target.value)} placeholder="72" />
                </div>
                <div className="field">
                  <label htmlFor="h">Altura (m)</label>
                  <input id="h" inputMode="decimal" value={f.height} onChange={(e) => set("height", e.target.value)} placeholder="1,75" />
                </div>
              </div>
            </>
          )}

          {step === "experiencia" && (
            <>
              <h1 className="wz-h">Você já corre hoje?</h1>
              <p className="wz-sub">Sem julgamento — é só pra começar no ponto certo.</p>
              <div className="wz-opts">
                <button type="button" className={`wz-opt ${f.runsToday === true ? "sel" : ""}`} onClick={() => set("runsToday", true)}>
                  <span className="wz-emo">🏃</span><span>Já corro<small>Faço treinos com alguma regularidade</small></span>
                </button>
                <button type="button" className={`wz-opt ${f.runsToday === false ? "sel" : ""}`} onClick={() => set("runsToday", false)}>
                  <span className="wz-emo">🌱</span><span>Tô começando<small>Caminho ou corro pouco ainda</small></span>
                </button>
              </div>

              {f.runsToday === true && (
                <div style={{ marginTop: 16 }}>
                  <div className="wz-row">
                    <div className="field">
                      <label htmlFor="rpw">Vezes/semana</label>
                      <input id="rpw" inputMode="numeric" value={f.runsPerWeek} onChange={(e) => set("runsPerWeek", e.target.value)} placeholder="3" />
                    </div>
                    <div className="field">
                      <label htmlFor="tk">Km por treino</label>
                      <input id="tk" inputMode="decimal" value={f.typicalKm} onChange={(e) => set("typicalKm", e.target.value)} placeholder="8" />
                    </div>
                  </div>
                  <p className="wz-sub" style={{ margin: "4px 0 8px" }}>Um treino recente pra eu pegar seu ritmo:</p>
                  <div className="wz-row">
                    <div className="field">
                      <label htmlFor="pd">Distância (km)</label>
                      <input id="pd" inputMode="decimal" value={f.paceDist} onChange={(e) => set("paceDist", e.target.value)} placeholder="8" />
                    </div>
                    <div className="field">
                      <label htmlFor="pm">Tempo (min)</label>
                      <input id="pm" inputMode="decimal" value={f.paceMin} onChange={(e) => set("paceMin", e.target.value)} placeholder="48" />
                    </div>
                  </div>
                </div>
              )}

              {f.runsToday === false && (
                <div className="wz-opts" style={{ marginTop: 16 }}>
                  <button type="button" className={`wz-opt ${f.mobility === "walker" ? "sel" : ""}`} onClick={() => set("mobility", "walker")}>
                    <span className="wz-emo">🚶</span><span>Caminho<small>Consigo caminhar, correr ainda cansa</small></span>
                  </button>
                  <button type="button" className={`wz-opt ${f.mobility === "run_walker" ? "sel" : ""}`} onClick={() => set("mobility", "run_walker")}>
                    <span className="wz-emo">🏃‍♂️</span><span>Trote e caminhada<small>Intercalo trotar e caminhar</small></span>
                  </button>
                  <button type="button" className={`wz-opt ${f.mobility === "runner" ? "sel" : ""}`} onClick={() => set("mobility", "runner")}>
                    <span className="wz-emo">💪</span><span>Corro pouco, mas contínuo<small>Aguento alguns minutos sem parar</small></span>
                  </button>
                </div>
              )}
            </>
          )}

          {step === "objetivo" && (
            <>
              <h1 className="wz-h">Qual seu objetivo?</h1>
              <p className="wz-sub">Isso ancora todo o seu plano.</p>
              <div className="wz-opts">
                <button type="button" className={`wz-opt ${f.goalKind === "health" ? "sel" : ""}`} onClick={() => set("goalKind", "health")}>
                  <span className="wz-emo">❤️</span><span>Saúde e condicionamento<small>Correr melhor, com constância</small></span>
                </button>
                <button type="button" className={`wz-opt ${f.goalKind === "race" ? "sel" : ""}`} onClick={() => set("goalKind", "race")}>
                  <span className="wz-emo">🏁</span><span>Uma prova ou marca<small>Ex.: 10 km em 55 min, uma corrida</small></span>
                </button>
              </div>

              {f.goalKind === "race" && (
                <div style={{ marginTop: 16 }}>
                  <div className="field">
                    <label htmlFor="race">Prova / distância</label>
                    <input id="race" value={f.race} onChange={(e) => set("race", e.target.value)} placeholder="Ex.: 10 km, meia maratona" />
                  </div>
                  <div className="wz-row">
                    <div className="field">
                      <label htmlFor="tt">Tempo-alvo (opcional)</label>
                      <input id="tt" value={f.targetTime} onChange={(e) => set("targetTime", e.target.value)} placeholder="55 min" />
                    </div>
                    <div className="field">
                      <label htmlFor="rd">Data (opcional)</label>
                      <input id="rd" type="date" value={f.raceDate} onChange={(e) => set("raceDate", e.target.value)} />
                    </div>
                  </div>
                </div>
              )}
            </>
          )}

          {step === "dias" && (
            <>
              <h1 className="wz-h">Quais dias você pode correr?</h1>
              <p className="wz-sub">Toca nos dias. Dá pra mudar depois.</p>
              <div className="wz-chips">
                {DAYS.map((d) => (
                  <button key={d.i} type="button" className={`wz-chip ${f.days.includes(d.i) ? "sel" : ""}`} onClick={() => toggleDay(d.i)}>
                    {d.label}
                  </button>
                ))}
              </div>
            </>
          )}

          {step === "treinador" && (
            <>
              <h1 className="wz-h">Você já tem um treinador ou planilha?</h1>
              <p className="wz-sub">Se sim, eu só acompanho os treinos dele — não mudo nada.</p>
              <div className="wz-opts">
                <button type="button" className={`wz-opt ${f.externalCoach === false ? "sel" : ""}`} onClick={() => set("externalCoach", false)}>
                  <span className="wz-emo">🤖</span><span>Não, monta pra mim<small>O Ritmind é seu treinador</small></span>
                </button>
                <button type="button" className={`wz-opt ${f.externalCoach === true ? "sel" : ""}`} onClick={() => set("externalCoach", true)}>
                  <span className="wz-emo">📋</span><span>Já tenho<small>Você acompanha meu plano atual</small></span>
                </button>
              </div>
            </>
          )}

          {step === "strava" && (
            <>
              <h1 className="wz-h">Você usa o Strava?</h1>
              <p className="wz-sub">
                {f.externalCoach
                  ? "Conectando, eu acompanho e analiso cada treino seu automaticamente."
                  : "Conectando agora, eu leio seu histórico real e monto um plano do seu tamanho — não um genérico."}
              </p>
              {strava ? (
                <p className="notice ok" style={{ marginTop: 6 }}>✅ Strava conectado! Já estou lendo seus treinos.</p>
              ) : (
                <>
                  <a className="btn btn-strava" href={stravaConnectUrl("onboarding")} onClick={() => saveDraft(f, i)}>
                    Conectar com Strava
                  </a>
                  <p className="muted" style={{ fontSize: 12.5, marginTop: 10 }}>
                    Não usa? Tudo bem — toca em <b>Próximo</b>. Dá pra conectar depois no Perfil.
                  </p>
                </>
              )}
            </>
          )}

          {step === "revisao" && (
            <>
              <h1 className="wz-h">Tudo certo, {firstName}?</h1>
              <p className="wz-sub">
                {f.externalCoach
                  ? "Vou registrar seu cadastro. Depois é só mandar o plano do seu treinador no coach."
                  : "Vou montar seu plano agora, com base no que você me contou."}
              </p>
              <div className="wz-opts">
                <div className="wz-opt" style={{ cursor: "default" }}>
                  <span className="wz-emo">🎯</span>
                  <span>
                    {f.goalKind === "race" ? (f.race || "Prova") : "Saúde e condicionamento"}
                    <small>{f.days.length} dia(s) por semana · {f.runsToday ? "já corre" : "começando"}</small>
                  </span>
                </div>
              </div>
              {!strava && (
                <p className="wz-sub" style={{ marginTop: 14 }}>
                  💡 Pra eu acompanhar seus treinos automaticamente, conecta o
                  Strava depois, na aba <b>Perfil</b>.
                </p>
              )}
            </>
          )}

          {err && <p className="notice err" style={{ marginTop: 14 }}>{err}</p>}

          <div className="wz-nav">
            {i > 0 && <button className="btn-ghost" onClick={back} disabled={saving}>Voltar</button>}
            {step !== "revisao" ? (
              <button className="btn" onClick={next} disabled={!canNext}>Próximo</button>
            ) : (
              <button className="btn" onClick={finish} disabled={saving}>
                {saving ? "Montando seu plano…" : f.externalCoach ? "Concluir cadastro" : "Montar meu plano"}
              </button>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
