"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getProfile, logout, type Profile } from "@/lib/api";

const SEX_PT: Record<string, string> = { M: "Masculino", F: "Feminino" };

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="prow">
      <span className="pl">{label}</span>
      <span className="pv">{value}</span>
    </div>
  );
}

export default function PerfilPage() {
  const router = useRouter();
  const [p, setP] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

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

  if (loading || !p) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
          <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
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
          <div className="card-head"><span className="eyebrow">Dados</span></div>
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
        </section>

        <button className="btn-danger" onClick={onLogout}>Sair da conta</button>

        <p className="muted center" style={{ marginTop: 4 }}>Ritmind</p>

      </div>
    </main>
  );
}
