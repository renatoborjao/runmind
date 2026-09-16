"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { addRace, deleteRace, getRaces, type Race } from "@/lib/api";

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

export default function ProvasPage() {
  const router = useRouter();
  const [races, setRaces] = useState<Race[] | null>(null);
  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
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
    setSaving(true);
    const res = await addRace({ name: name.trim(), date, target_time: time.trim() || null });
    setSaving(false);
    if (res.ok) {
      setName(""); setDate(""); setTime("");
      load();
    } else {
      setErr(res.message || "Não consegui cadastrar.");
    }
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
                      {r.target_time ? ` · alvo ${r.target_time}` : ""}
                      {du != null && du >= 0 && !r.past ? ` · faltam ${du} dia${du === 1 ? "" : "s"}` : ""}
                    </div>
                    {r.is_anchor && <span className="race-badge">🎯 alvo do plano</span>}
                    {r.past && <span className="race-badge" style={{ color: "var(--muted)", background: "var(--surface-2)" }}>realizada</span>}
                  </div>
                  <button className="race-del" aria-label="Remover" onClick={() => onDelete(r.id, r.name)}>×</button>
                </div>
              );
            })}
          </div>
        )}

        <p className="muted center" style={{ fontSize: 12, margin: "16px 0 24px" }}>
          A prova futura mais próxima ancora seu plano. Mudanças valem a partir do próximo domingo — sua semana atual não vira de cabeça pra baixo.
        </p>
      </div>
    </main>
  );
}
