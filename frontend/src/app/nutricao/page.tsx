"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  generateNutritionPlan,
  getNutrition,
  readBodyPhoto,
  saveBodyReading,
  saveNutritionSettings,
  type BodyReading,
  type NutritionState,
} from "@/lib/api";

const FIELDS: { key: keyof BodyReading; label: string; step?: string }[] = [
  { key: "weight_kg", label: "Peso (kg)" },
  { key: "body_fat_pct", label: "Gordura (%)" },
  { key: "lean_mass_kg", label: "Massa magra (kg)" },
  { key: "muscle_mass_kg", label: "Massa muscular (kg)" },
  { key: "fat_mass_kg", label: "Massa de gordura (kg)" },
  { key: "water_pct", label: "Água (%)" },
  { key: "visceral_fat", label: "Gordura visceral" },
  { key: "bmr_kcal", label: "Metabolismo basal (kcal)" },
];

type Form = Record<string, string>;

function toForm(r: Partial<BodyReading> | null): Form {
  const f: Form = {};
  for (const { key } of FIELDS) {
    const v = r?.[key];
    f[key] = v === null || v === undefined ? "" : String(v);
  }
  return f;
}

function num(v: string): number | null {
  const n = parseFloat(v.replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

// reduz a foto (lado maior ≤ 1600px, JPEG) antes de enviar
function compressImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const max = 1600;
      const scale = Math.min(1, max / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * scale);
      c.height = Math.round(img.height * scale);
      c.getContext("2d")?.drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Imagem inválida")); };
    img.src = url;
  });
}

export default function NutricaoPage() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [st, setSt] = useState<NutritionState | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<Form>(toForm(null));
  const [goals, setGoals] = useState<string[]>(["performance"]);
  const [targetWeight, setTargetWeight] = useState("");
  const [meals, setMeals] = useState(5);
  const [restrictions, setRestrictions] = useState("");
  const [dislikes, setDislikes] = useState("");
  const [busy, setBusy] = useState<"" | "photo" | "save" | "plan">("");
  const [err, setErr] = useState("");
  const [dayIdx, setDayIdx] = useState(0);

  async function load() {
    try {
      const s = await getNutrition();
      if (!s) { setFailed(true); return; }
      setSt(s);
      setGoals(s.settings.goals?.length ? s.settings.goals : ["performance"]);
      setTargetWeight(s.settings.target_weight_kg ? String(s.settings.target_weight_kg) : "");
      setMeals(s.settings.meals_per_day ?? 5);
      setRestrictions(s.settings.restrictions ?? "");
      setDislikes(s.settings.dislikes ?? "");
      setForm(toForm(s.reading));
      setEditing(!s.reading);
      // abre no dia de hoje (0 = segunda)
      setDayIdx((new Date().getDay() + 6) % 7);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function onPhoto(file: File | undefined) {
    if (!file) return;
    setErr("");
    setBusy("photo");
    try {
      const data = await compressImage(file);
      const r = await readBodyPhoto(data);
      setForm(toForm(r));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Não consegui ler a foto.");
    } finally {
      setBusy("");
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function saveReading(): Promise<boolean> {
    const body: Record<string, number | null | string> = {};
    for (const { key } of FIELDS) body[key] = num(form[key]);
    if (body.weight_kg === null) { setErr("Informe ao menos o peso."); return false; }
    body.source = "app";
    await saveBodyReading(body as Partial<BodyReading>);
    return true;
  }

  function toggleGoal(k: string) {
    setGoals((cur) => {
      if (cur.includes(k)) return cur.length > 1 ? cur.filter((g) => g !== k) : cur;
      // "manter o peso" não combina com mudar de corpo
      if (k === "maintain") return ["maintain"];
      const next = [...cur.filter((g) => g !== "maintain"), k];
      return next.slice(-3);
    });
  }

  async function onSaveOnly() {
    setErr("");
    setBusy("save");
    try {
      if (await saveReading()) { setEditing(false); await load(); }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Não consegui salvar.");
    } finally {
      setBusy("");
    }
  }

  async function onGenerate() {
    setErr("");
    try {
      if (editing) {
        setBusy("save");
        if (!(await saveReading())) { setBusy(""); return; }
      }
      await saveNutritionSettings({ goals, target_weight_kg: num(targetWeight) ?? 0, meals_per_day: meals, restrictions, dislikes });
      setBusy("plan");
      await generateNutritionPlan();
      setEditing(false);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Algo deu errado.");
    } finally {
      setBusy("");
    }
  }

  if (failed) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1, gap: 14 }}>
          <p className="auth-sub" style={{ margin: 0, textAlign: "center" }}>Não consegui carregar a nutrição agora.</p>
          <button className="btn-primary" onClick={() => { setFailed(false); setLoading(true); load(); }}>Tentar de novo</button>
        </div>
      </main>
    );
  }
  if (loading || !st) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
          <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
        </div>
      </main>
    );
  }

  const plan = st.plan;
  const menuDay = plan?.menu.days[dayIdx];
  const tgtDay = plan?.targets.days[dayIdx];
  const planning = busy === "plan";
  const curWeight = num(form.weight_kg ?? "") ?? st.reading?.weight_kg ?? st.profile_weight;
  const tw = num(targetWeight);
  const weeksPreview = (() => {
    if (!tw || !curWeight || Math.abs(tw - curWeight) < 0.5) return "";
    const diff = tw - curWeight;
    const weeks = Math.max(1, Math.round(Math.abs(diff) / (diff < 0 ? 0.5 : 0.25)));
    return `${diff < 0 ? "Perder" : "Ganhar"} ${Math.abs(diff).toFixed(1).replace(".", ",")} kg em ritmo saudável: cerca de ${weeks} semanas.`;
  })();
  // editando medição nova pode liberar o plano (o servidor decide de verdade)
  const gateOpen = st.plan_gate.allowed || (editing && !!plan && !st.plan_gate.next_date);

  return (
    <main className="stage">
      <div className="phone">
        <header className="appbar">
          <button className="icon-btn" aria-label="Voltar" onClick={() => router.push("/inicio")}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <div className="title"><div className="t">Nutrição</div></div>
          <span style={{ width: 34 }} />
        </header>

        {/* BIOIMPEDÂNCIA */}
        <section className="card">
          <div className="card-head">
            <span className="eyebrow">Sua bioimpedância</span>
            {st.reading && !editing && <a className="link" onClick={() => setEditing(true)}>Atualizar</a>}
          </div>

          {editing ? (
            <>
              <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => onPhoto(e.target.files?.[0])} />
              <button className="cta-btn" style={{ marginTop: 0, marginBottom: 14 }} disabled={busy !== ""} onClick={() => fileRef.current?.click()}>
                {busy === "photo" ? "Lendo a foto…" : "📷 Ler de uma foto do laudo"}
              </button>
              <div className="nut-grid">
                {FIELDS.map(({ key, label }) => (
                  <div className="field" key={key}>
                    <label>{label}</label>
                    <input inputMode="decimal" value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
                  </div>
                ))}
              </div>
              <p className="auth-sub" style={{ margin: "10px 0 0", fontSize: 12.5 }}>Confira os números lidos. Só o peso é obrigatório; quanto mais dados, mais certeira a meta.</p>
            </>
          ) : (
            st.reading && (
              <>
                <div className="nut-macros" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
                  <div><b>{st.reading.weight_kg ?? "–"}</b><span>kg</span></div>
                  <div><b>{st.reading.body_fat_pct ?? "–"}{st.reading.body_fat_pct ? "%" : ""}</b><span>gordura</span></div>
                  <div><b>{st.reading.lean_mass_kg ?? st.reading.muscle_mass_kg ?? "–"}</b><span>{st.reading.lean_mass_kg ? "massa magra" : "músculo"}</span></div>
                </div>
                {st.readings.length > 1 && (
                  <div>
                    {[...st.readings].reverse().slice(0, 5).map((r, i) => (
                      <div className="nut-hist" key={i}>
                        <span>{r.date ? r.date.split("-").reverse().join("/") : ""}</span>
                        <span>{r.weight_kg ?? "–"} kg · {r.body_fat_pct ?? "–"}% gord.</span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )
          )}
        </section>

        {/* OBJETIVO E PREFERÊNCIAS */}
        <section className="card">
          <div className="card-head"><span className="eyebrow">Objetivo e preferências</span></div>
          <div className="field"><label>O que você quer (escolha até 3)</label></div>
          <div className="chips" style={{ marginBottom: 10 }}>
            {Object.entries(st.goals).map(([k, label]) => (
              <button key={k} className={`chip-btn${goals.includes(k) ? " on" : ""}`} onClick={() => toggleGoal(k)}>{label}</button>
            ))}
          </div>
          {goals.includes("lose_fat") && goals.includes("gain_muscle") && (
            <p className="nut-note">Perder gordura e ganhar massa juntos é recomposição corporal: déficit leve e proteína alta, com o treino sustentando o músculo. Progresso mais lento, porém mais certeiro.</p>
          )}
          {(goals.includes("lose_fat") || goals.includes("gain_muscle")) && (
            <div className="field" style={{ marginBottom: 14 }}>
              <label>Peso que você quer atingir (kg)</label>
              <input inputMode="decimal" value={targetWeight} onChange={(e) => setTargetWeight(e.target.value)} placeholder={curWeight ? `Hoje: ${curWeight} kg` : "Ex.: 72"} />
              {weeksPreview && <p className="auth-sub" style={{ margin: "8px 0 0", fontSize: 12.5 }}>{weeksPreview}</p>}
            </div>
          )}
          <div className="field">
            <label>Refeições por dia</label>
            <div className="seg">
              {[3, 4, 5, 6].map((n) => <button key={n} className={meals === n ? "on" : ""} onClick={() => setMeals(n)}>{n}</button>)}
            </div>
          </div>
          <div className="field" style={{ marginTop: 12 }}>
            <label>Restrições / alergias</label>
            <textarea className="nut-ta" rows={2} value={restrictions} onChange={(e) => setRestrictions(e.target.value)} placeholder="Ex.: intolerância a lactose, vegetariano" />
          </div>
          <div className="field" style={{ marginTop: 12 }}>
            <label>O que você não come</label>
            <textarea className="nut-ta" rows={2} value={dislikes} onChange={(e) => setDislikes(e.target.value)} placeholder="Ex.: peixe, fígado, coentro" />
          </div>
          {err && <p className="nut-err">{err}</p>}
          {gateOpen ? (
            <button className="cta-btn" disabled={busy !== ""} onClick={onGenerate}>
              {planning ? "Montando seu cardápio… (até 1 min)" : busy === "save" ? "Salvando…" : plan ? "Gerar plano com a nova medição" : "Gerar meu plano alimentar"}
            </button>
          ) : (
            <>
              <p className="nut-note" style={{ marginTop: 14 }}>🔒 {st.plan_gate.reason}</p>
              {editing && (
                <button className="cta-btn" style={{ marginTop: 0 }} disabled={busy !== ""} onClick={onSaveOnly}>
                  {busy === "save" ? "Salvando…" : "Salvar medição"}
                </button>
              )}
            </>
          )}
        </section>

        {/* PLANO */}
        {plan && menuDay && tgtDay && (
          <>
            <section className="card">
              <div className="card-head">
                <span className="eyebrow">Seu plano · {plan.targets.goal_pt}{plan.targets.target_weight_kg ? ` → ${plan.targets.target_weight_kg} kg` : ""}</span>
              </div>
              <div className="nut-days">
                {plan.targets.days.map((d, i) => (
                  <button key={d.day} className={`nut-day${i === dayIdx ? " on" : ""}`} onClick={() => setDayIdx(i)}>
                    {d.day_pt.slice(0, 3)}<small>{d.type_pt}</small>
                  </button>
                ))}
              </div>
              <div className="nut-macros">
                <div><b>{tgtDay.kcal}</b><span>kcal</span></div>
                <div><b>{tgtDay.protein_g}</b><span>prot g</span></div>
                <div><b>{tgtDay.carb_g}</b><span>carb g</span></div>
                <div><b>{tgtDay.fat_g}</b><span>gord g</span></div>
              </div>
              {tgtDay.workout && <p className="nut-note">🏃 {tgtDay.workout}{tgtDay.distance_km ? ` · ${tgtDay.distance_km} km` : ""}{tgtDay.duration_min ? ` · ~${tgtDay.duration_min} min` : ""}{tgtDay.training_kcal ? ` · ~${tgtDay.training_kcal} kcal gastas` : ""}</p>}
              {menuDay.note && <p className="nut-note">💡 {menuDay.note}</p>}
              {menuDay.meals.map((m, i) => (
                <div className="nut-meal" key={i}>
                  <div className="nut-meal-h">
                    <span className="nut-meal-n">
                      {m.name}
                      {m.tag && <span className="nut-tag">{m.tag === "pre_treino" ? "pré-treino" : "pós-treino"}</span>}
                    </span>
                    <span className="nut-meal-t">{m.time}</span>
                  </div>
                  <ul className="nut-items">
                    {m.items.map((it, j) => <li key={j}>{it.food} — {it.qty}</li>)}
                  </ul>
                  <div className="nut-meal-m">{m.kcal} kcal · P {m.protein_g} · C {m.carb_g} · G {m.fat_g}</div>
                </div>
              ))}
              <div className="nut-meal-m" style={{ marginTop: 10 }}>
                Total do dia: {menuDay.totals.kcal} kcal · P {menuDay.totals.protein_g} · C {menuDay.totals.carb_g} · G {menuDay.totals.fat_g}
              </div>
            </section>

            {plan.menu.tips.length > 0 && (
              <section className="card">
                <div className="card-head"><span className="eyebrow">Dicas do coach</span></div>
                <ul className="nut-tips">{plan.menu.tips.map((t, i) => <li key={i}>{t}</li>)}</ul>
                <p className="nut-meal-m" style={{ marginTop: 12 }}>
                  Metabolismo basal {plan.targets.bmr_kcal} kcal ({plan.targets.bmr_method}). As metas acompanham o seu plano de treino: se a semana mudar, refaça o plano.
                </p>
              </section>
            )}
          </>
        )}
      </div>
    </main>
  );
}
