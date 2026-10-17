"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  addRace, deleteRace, getRaces, updateRace, RACE_PRIORITY_LABEL,
  type Race, type RacePriority,
} from "@/lib/api";

const MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

function fmtDate(iso: string): { d: string; m: string; full: string } {
  const dt = new Date(iso + "T00:00:00");
  if (isNaN(dt.getTime())) return { d: "—", m: "", full: iso };
  return {
    d: String(dt.getDate()).padStart(2, "0"),
    m: MONTHS[dt.getMonth()],
    full: dt.toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" }),
  };
}

function daysUntil(iso: string): number | null {
  const dt = new Date(iso + "T00:00:00");
  if (isNaN(dt.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((dt.getTime() - today.getTime()) / 86400000);
}

const PRIORITIES: RacePriority[] = ["A", "B", "C"];

function fmtKm(km: number): string {
  return `${Number.isInteger(km) ? km : km.toFixed(1).replace(".", ",")} km`;
}

export default function ProvasPage() {
  const router = useRouter();
  const [races, setRaces] = useState<Race[] | null>(null);
  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [km, setKm] = useState("");
  const [priority, setPriority] = useState<RacePriority | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    const r = await getRaces();
    if (r === null) { router.replace("/entrar"); return; }
    setRaces(r);
  }

  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function onAdd(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!name.trim() || !date) { setErr("Preencha nome e data."); return; }
    const kmNum = km.trim() ? Number(km.trim().replace(",", ".")) : null;
    if (kmNum !== null && (!isFinite(kmNum) || kmNum < 0.4 || kmNum > 500)) {
      setErr("Distância inválida (use km, ex.: 21,1).");
      return;
    }
    setSaving(true);
    const res = await addRace({
      name: name.trim(), date, target_time: time.trim() || null,
      distance_km: kmNum, priority,
    });
    setSaving(false);
    if (res.ok) {
      setName(""); setDate(""); setTime(""); setKm(""); setPriority(null);
      load();
    } else {
      setErr(res.message || "Não consegui cadastrar.");
    }
  }

  async function onPriority(id: string, p: RacePriority) {
    // otimista: a tela muda na hora; o servidor confirma no reload
    setRaces((rs) => (rs ? rs.map((r) => (r.id === id ? { ...r, priority: p, priority_effective: p } : r)) : rs));
    const res = await updateRace(id, { priority: p });
    if (!res.ok) setErr(res.message || "Não consegui atualizar o papel.");
    load();
  }

  async function onDelete(id: string, raceName: string) {
    // confirma antes de apagar — evita sumir com a prova num toque sem querer
    const ok = window.confirm(`Apagar a prova "${raceName}"? Isso não dá pra desfazer.`);
    if (!ok) return;
    setRaces((rs) => (rs ? rs.filter((r) => r.id !== id) : rs));
    await deleteRace(id);
    load();
  }

  return (
    <main className="stage">
      <div className="phone">
        <header className="appbar">
          <button className="icon-btn" aria-label="Voltar" onClick={() => router.push("/perfil")}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <div className="title"><div className="t">Minhas provas</div></div>
          <span style={{ width: 34 }} />
        </header>

        {/* adicionar */}
        <section className="card">
          <div className="card-head"><span className="eyebrow">Cadastrar prova</span></div>
          <form onSubmit={onAdd}>
            <div className="field">
              <label htmlFor="rn">Nome da prova</label>
              <input id="rn" type="text" placeholder="Ex.: Maratona de São Paulo" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <div className="field" style={{ flex: 1 }}>
                <label htmlFor="rd">Data</label>
                <input id="rd" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label htmlFor="rt">Tempo-alvo (opcional)</label>
                <input id="rt" type="text" inputMode="numeric" placeholder="0:50:00" value={time} onChange={(e) => setTime(e.target.value)} />
              </div>
            </div>
            <div className="field">
              <label htmlFor="rk">Distância em km (opcional)</label>
              <input id="rk" type="text" inputMode="decimal" placeholder="Pelo nome eu descubro: 10 km, meia…" value={km} onChange={(e) => setKm(e.target.value)} />
            </div>
            <div className="field">
              <label>Papel dessa prova (opcional)</label>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {PRIORITIES.map((p) => (
                  <button key={p} type="button" className={`chip-btn${priority === p ? " on" : ""}`}
                    style={{ textTransform: "none" }}
                    onClick={() => setPriority(priority === p ? null : p)}>
                    {RACE_PRIORITY_LABEL[p]}
                  </button>
                ))}
              </div>
              <p className="muted" style={{ fontSize: 11.5, margin: "6px 0 0" }}>
                Principal: seu plano mira ela. Preparatória: marco no caminho, sem polimento pesado. De treino: corre sem parar o plano. Sem escolha, eu sugiro.
              </p>
            </div>
            {err && <p className="notice err" style={{ marginTop: 0 }}>{err}</p>}
            <button className="btn" type="submit" disabled={saving}>{saving ? "Salvando…" : "Adicionar prova"}</button>
          </form>
        </section>

        {/* lista */}
        {races === null ? (
          <p className="auth-sub center">Carregando…</p>
        ) : races.length === 0 ? (
          <div className="empty-state">
            <div className="emoji">🏁</div>
            <p>Nenhuma prova cadastrada. Adicione uma acima — a mais próxima vira o alvo do seu plano.</p>
          </div>
        ) : (
          <div className="notif-list">
            {races.map((r) => {
              const dd = fmtDate(r.date);
              const du = daysUntil(r.date);
              return (
                <div key={r.id} className={`race-row${r.is_anchor ? " anchor" : ""}${r.past ? " past" : ""}`}>
                  <div className="race-cal"><div className="d">{dd.d}</div><div className="m">{dd.m}</div></div>
                  <div className="race-info">
                    <div className="n">{r.name}</div>
                    <div className="meta">
                      {dd.full}
                      {r.distance_km ? ` · ${fmtKm(r.distance_km)}` : ""}
                      {r.target_time ? ` · alvo ${r.target_time}` : ""}
                      {du != null && du >= 0 && !r.past ? ` · faltam ${du} dia${du === 1 ? "" : "s"}` : ""}
                    </div>
                    {r.is_anchor && <span className="race-badge">🎯 próxima do plano</span>}
                    {!r.past && (
                      <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 7, alignItems: "center" }}>
                        {PRIORITIES.map((p) => (
                          <button key={p} type="button"
                            className={`chip-btn${r.priority_effective === p ? " on" : ""}`}
                            style={{ padding: "4px 10px", fontSize: 11.5, textTransform: "none" }}
                            onClick={() => onPriority(r.id, p)}>
                            {RACE_PRIORITY_LABEL[p]}
                          </button>
                        ))}
                        {!r.priority && r.priority_suggested && (
                          <span className="muted" style={{ fontSize: 11 }}>sugerido · toque pra confirmar</span>
                        )}
                      </div>
                    )}
                    {r.past && <span className="race-badge" style={{ color: "var(--muted)", background: "var(--surface-2)" }}>realizada</span>}
                  </div>
                  <button className="race-del" aria-label="Remover" onClick={() => onDelete(r.id, r.name)}>×</button>
                </div>
              );
            })}
          </div>
        )}

        <p className="muted center" style={{ fontSize: 12, margin: "16px 0 24px" }}>
          O papel de cada prova diz ao coach como se organizar: a principal é o grande alvo; a preparatória é um marco no caminho; a de treino não muda o plano. Mudanças valem a partir do próximo domingo — sua semana atual não vira de cabeça pra baixo.
        </p>
      </div>
    </main>
  );
}
