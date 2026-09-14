"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getProfile, logout, saveProfile, type Profile } from "@/lib/api";

const SEX_PT: Record<string, string> = { M: "Masculino", F: "Feminino" };

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="prow">
      <span className="pl">{label}</span>
      <span className="pv">{value}</span>
    </div>
  );
}

type Form = {
  first_name: string;
  last_name: string;
  email: string;
  age: string;
  weight: string;
  height: string;
  sex: string;
};

function toForm(p: Profile): Form {
  return {
    first_name: p.first_name ?? "",
    last_name: p.last_name ?? "",
    email: p.email ?? "",
    age: p.age ? String(p.age) : "",
    weight: p.weight ? String(p.weight) : "",
    height: p.height ? String(p.height) : "",
    sex: p.sex ?? "",
  };
}

export default function PerfilPage() {
  const router = useRouter();
  const [p, setP] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [f, setF] = useState<Form | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const data = await getProfile();
      if (!data) { router.replace("/entrar"); return; }
      setP(data);
      setLoading(false);
    })();
  }, [router]);

  async function onLogout() {
    await logout();
    router.replace("/entrar");
  }

  function startEdit() {
    if (!p) return;
    setF(toForm(p));
    setErr(null);
    setEditing(true);
  }

  async function onSave() {
    if (!f) return;
    setSaving(true); setErr(null);
    const res = await saveProfile({
      first_name: f.first_name.trim(),
      last_name: f.last_name.trim(),
      email: f.email.trim() || null,
      age: f.age ? Number(f.age) : undefined,
      weight: f.weight ? Number(f.weight.replace(",", ".")) : undefined,
      height: f.height ? Number(f.height.replace(",", ".")) : undefined,
      sex: f.sex || null,
    });
    setSaving(false);
    if (!res.ok) { setErr(res.message ?? "Não consegui salvar."); return; }
    if (res.profile) setP(res.profile);
    setEditing(false);
  }

  if (loading || !p) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
          <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
        </div>
      </main>
    );
  }

  // TELA: editar dados pessoais
  if (editing && f) {
    const up = (patch: Partial<Form>) => setF((s) => (s ? { ...s, ...patch } : s));
    return (
      <main className="stage">
        <div className="phone">
          <header className="appbar">
            <button className="icon-btn" aria-label="Voltar" onClick={() => { setEditing(false); setErr(null); }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
            </button>
            <div className="title"><div className="t">Editar dados</div></div>
            <span style={{ width: 34 }} />
          </header>

          {err && <div className="notice err">{err}</div>}

          <div className="card" style={{ padding: 16 }}>
            <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
              <div className="field" style={{ flex: 1 }}>
                <label>Nome</label>
                <input value={f.first_name} onChange={(e) => up({ first_name: e.target.value })} />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>Sobrenome</label>
                <input value={f.last_name} onChange={(e) => up({ last_name: e.target.value })} />
              </div>
            </div>

            <div className="field" style={{ marginBottom: 12 }}>
              <label>E-mail (login)</label>
              <input type="email" value={f.email} onChange={(e) => up({ email: e.target.value })} placeholder="voce@email.com" />
            </div>

            <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
              <div className="field" style={{ flex: 1 }}>
                <label>Idade</label>
                <input type="number" inputMode="numeric" value={f.age} onChange={(e) => up({ age: e.target.value })} placeholder="anos" />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>Peso (kg)</label>
                <input type="number" inputMode="decimal" step="0.1" value={f.weight} onChange={(e) => up({ weight: e.target.value })} placeholder="kg" />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>Altura (m)</label>
                <input type="number" inputMode="decimal" step="0.01" value={f.height} onChange={(e) => up({ height: e.target.value })} placeholder="1,75" />
              </div>
            </div>

            <div>
              <label className="fld-label">Sexo</label>
              <div className="chips">
                {(["M", "F"] as const).map((s) => (
                  <button key={s} type="button" className={`chip-btn${f.sex === s ? " on" : ""}`}
                    onClick={() => up({ sex: f.sex === s ? "" : s })}>{SEX_PT[s]}</button>
                ))}
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
              <button className="btn-ghost" style={{ flex: 1 }} disabled={saving} onClick={() => { setEditing(false); setErr(null); }}>Cancelar</button>
              <button className="btn-primary" style={{ flex: 1 }} disabled={saving} onClick={onSave}>{saving ? "Salvando…" : "Salvar"}</button>
            </div>
          </div>

          <p className="muted center" style={{ marginTop: 4, fontSize: 12 }}>
            Meta, dias de treino e prova você ajusta conversando com o coach 💬
          </p>
        </div>
      </main>
    );
  }

  const initials = (p.first_name?.[0] ?? "") + (p.last_name?.[0] ?? "");

  return (
    <main className="stage">
      <div className="phone">

        <header className="appbar">
          <button className="icon-btn" aria-label="Voltar" onClick={() => router.push("/inicio")}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <div className="title"><div className="t">Perfil</div></div>
          <span style={{ width: 34 }} />
        </header>

        {/* cabeçalho */}
        <section className="card" style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span className="avatar-lg">{initials || "🏃"}</span>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: 20 }}>{p.name}</div>
            {p.email && <div className="muted" style={{ fontSize: 13 }}>{p.email}</div>}
          </div>
        </section>

        {/* dados pessoais */}
        <section className="card">
          <div className="card-head">
            <span className="eyebrow">Dados</span>
            <a className="link" onClick={startEdit}>Editar</a>
          </div>
          <Row label="Nome" value={p.first_name || "—"} />
          <Row label="Sobrenome" value={p.last_name || "—"} />
          <Row label="E-mail" value={p.email || "—"} />
          <Row label="Idade" value={p.age ? `${p.age} anos` : "—"} />
          <Row label="Peso" value={p.weight ? `${String(p.weight).replace(".", ",")} kg` : "—"} />
          <Row label="Altura" value={p.height ? `${String(p.height).replace(".", ",")} m` : "—"} />
          <Row label="Sexo" value={p.sex ? (SEX_PT[p.sex] ?? p.sex) : "—"} />
        </section>

        {/* treino */}
        <section className="card">
          <div className="card-head"><span className="eyebrow">Treino</span></div>
          <Row label="Objetivo" value={p.goal || "—"} />
          <Row label="Dias por semana" value={p.weekly_training_days ? `${p.weekly_training_days}x` : "—"} />
          <Row label="Dias preferidos" value={p.preferred_running_days.length ? p.preferred_running_days.join(", ") : "—"} />
          {p.target_race && <Row label="Prova" value={p.target_race} />}
          {p.race_date && <Row label="Data da prova" value={new Date(p.race_date + "T00:00:00").toLocaleDateString("pt-BR")} />}
          {p.target_time && <Row label="Tempo-alvo" value={p.target_time} />}
          <p className="muted" style={{ margin: "10px 2px 0", fontSize: 12 }}>Isso é dinâmico — ajuste com o coach. 💬</p>
        </section>

        <button className="btn-danger" onClick={onLogout}>Sair da conta</button>

        <p className="muted center" style={{ marginTop: 4 }}>Ritmind</p>

      </div>
    </main>
  );
}
