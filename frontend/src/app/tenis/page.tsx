"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  addShoe,
  deleteShoe,
  editShoe,
  getShoes,
  type Shoe,
  type ShoeInput,
} from "@/lib/api";

const CATEGORIES = ["dia a dia", "versátil", "rápido"];

function ShoeIcon() {
  return (
    <span className="shoe-ico" aria-hidden>
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="var(--accent-ink)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M2 17h18a2 2 0 0 0 2-2c0-1-.7-1.7-1.7-2L13 10 9.5 6 6 6l-.5 4.5L2 13z" /><path d="M2 13v4" /></svg>
    </span>
  );
}

type FormState = {
  name: string;
  nickname: string;
  category: string;
  km: string;
  threshold: string;
  isDefault: boolean;
};

function emptyForm(): FormState {
  return { name: "", nickname: "", category: "", km: "", threshold: "", isDefault: false };
}

function ShoeForm({
  mode,
  initial,
  saving,
  onCancel,
  onSubmit,
}: {
  mode: "add" | "edit";
  initial: FormState;
  saving: boolean;
  onCancel: () => void;
  onSubmit: (f: FormState) => void;
}) {
  const [f, setF] = useState<FormState>(initial);
  const up = (patch: Partial<FormState>) => setF((s) => ({ ...s, ...patch }));

  return (
    <div className="card" style={{ padding: 16 }}>
      <div className="field" style={{ marginBottom: 12 }}>
        <label>Nome do tênis</label>
        <input value={f.name} onChange={(e) => up({ name: e.target.value })} placeholder="Ex.: Novablast 5" />
      </div>
      <div className="field" style={{ marginBottom: 12 }}>
        <label>Apelido (opcional)</label>
        <input value={f.nickname} onChange={(e) => up({ nickname: e.target.value })} placeholder="Como você chama ele" />
      </div>

      <div style={{ marginBottom: 12 }}>
        <label className="fld-label">Categoria</label>
        <div className="chips">
          {CATEGORIES.map((c) => (
            <button key={c} type="button" className={`chip-btn${f.category === c ? " on" : ""}`}
              onClick={() => up({ category: f.category === c ? "" : c })}>{c}</button>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
        <div className="field" style={{ flex: 1 }}>
          <label>{mode === "add" ? "Km já rodados" : "Km atual (total)"}</label>
          <input type="number" inputMode="decimal" value={f.km} onChange={(e) => up({ km: e.target.value })} placeholder="0" />
        </div>
        <div className="field" style={{ flex: 1 }}>
          <label>Trocar em (km)</label>
          <input type="number" inputMode="decimal" value={f.threshold} onChange={(e) => up({ threshold: e.target.value })} placeholder="700" />
        </div>
      </div>

      <label className="row-toggle">
        <input type="checkbox" checked={f.isDefault} onChange={(e) => up({ isDefault: e.target.checked })} />
        <span>É o meu tênis do dia a dia</span>
      </label>

      <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
        <button className="btn-ghost" style={{ flex: 1 }} onClick={onCancel} disabled={saving}>Cancelar</button>
        <button className="btn-primary" style={{ flex: 1 }} disabled={saving || !f.name.trim()} onClick={() => onSubmit(f)}>
          {saving ? "Salvando…" : mode === "add" ? "Adicionar" : "Salvar"}
        </button>
      </div>
    </div>
  );
}

export default function TenisPage() {
  const router = useRouter();
  const [shoes, setShoes] = useState<Shoe[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function reload() {
    setShoes(await getShoes());
  }

  useEffect(() => {
    (async () => {
      const s = await getShoes();
      if (s === null) { router.replace("/entrar"); return; }
      setShoes(s);
      setLoading(false);
    })();
  }, [router]);

  async function onAdd(f: FormState) {
    setSaving(true); setErr(null);
    const body: ShoeInput = {
      name: f.name.trim(),
      nickname: f.nickname.trim() || null,
      category: f.category || null,
      initial_km: f.km ? Number(f.km) : null,
      alert_threshold_km: f.threshold ? Number(f.threshold) : null,
      is_default: f.isDefault,
    };
    const res = await addShoe(body);
    setSaving(false);
    if (!res.ok) { setErr(res.message ?? "Não consegui adicionar."); return; }
    setAdding(false);
    await reload();
  }

  async function onEdit(id: string, f: FormState) {
    setSaving(true); setErr(null);
    const res = await editShoe(id, {
      name: f.name.trim(),
      nickname: f.nickname.trim() || null,
      category: f.category || null,
      total_km: f.km !== "" ? Number(f.km) : undefined,
      alert_threshold_km: f.threshold ? Number(f.threshold) : undefined,
      is_default: f.isDefault,
    });
    setSaving(false);
    if (!res.ok) { setErr(res.message ?? "Não consegui salvar."); return; }
    setEditId(null);
    await reload();
  }

  async function onRetire(s: Shoe) {
    setSaving(true);
    await editShoe(s.id, { retired: !s.retired });
    setSaving(false);
    setEditId(null);
    await reload();
  }

  async function onDelete(s: Shoe) {
    if (!confirm(`Remover "${s.label}" do armário? Isso apaga a rodagem registrada dele.`)) return;
    setSaving(true);
    await deleteShoe(s.id);
    setSaving(false);
    setEditId(null);
    await reload();
  }

  if (loading || !shoes) {
    return (
      <main className="stage">
        <div className="phone center" style={{ justifyContent: "center", flex: 1 }}>
          <p className="auth-sub" style={{ margin: 0 }}>Carregando…</p>
        </div>
      </main>
    );
  }

  const active = shoes.filter((s) => !s.retired);
  const retired = shoes.filter((s) => s.retired);

  return (
    <main className="stage">
      <div className="phone">
        <header className="appbar">
          <button className="icon-btn" aria-label="Voltar" onClick={() => router.push("/inicio")}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <div className="title"><div className="t">Armário de tênis</div></div>
          <span style={{ width: 34 }} />
        </header>

        {err && <div className="notice err">{err}</div>}

        {!adding && (
          <button className="btn-primary" style={{ marginBottom: 4 }} onClick={() => { setAdding(true); setEditId(null); setErr(null); }}>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14" /></svg>
            Adicionar tênis
          </button>
        )}

        {adding && (
          <ShoeForm mode="add" initial={emptyForm()} saving={saving}
            onCancel={() => { setAdding(false); setErr(null); }} onSubmit={onAdd} />
        )}

        {shoes.length === 0 && !adding && (
          <div className="card center">
            <p className="muted" style={{ margin: 0 }}>Seu armário está vazio. Adiciona teu primeiro par pra começar a contar a rodagem. 👟</p>
          </div>
        )}

        {active.map((s) =>
          editId === s.id ? (
            <div key={s.id}>
              <ShoeForm mode="edit" saving={saving}
                initial={{ name: s.name, nickname: s.nickname ?? "", category: s.category ?? "", km: String(s.total_km), threshold: String(s.alert_threshold_km), isDefault: s.is_default }}
                onCancel={() => { setEditId(null); setErr(null); }}
                onSubmit={(f) => onEdit(s.id, f)} />
              <div style={{ display: "flex", gap: 10, margin: "-4px 2px 8px" }}>
                <button className="btn-ghost" style={{ flex: 1 }} disabled={saving} onClick={() => onRetire(s)}>Aposentar</button>
                <button className="btn-ghost danger" style={{ flex: 1 }} disabled={saving} onClick={() => onDelete(s)}>Excluir</button>
              </div>
            </div>
          ) : (
            <ShoeCard key={s.id} s={s} onEdit={() => { setEditId(s.id); setAdding(false); setErr(null); }} />
          )
        )}

        {retired.length > 0 && (
          <>
            <div className="topbar" style={{ marginTop: 8 }}><span className="eyebrow">Aposentados</span></div>
            {retired.map((s) =>
              editId === s.id ? (
                <div key={s.id}>
                  <ShoeForm mode="edit" saving={saving}
                    initial={{ name: s.name, nickname: s.nickname ?? "", category: s.category ?? "", km: String(s.total_km), threshold: String(s.alert_threshold_km), isDefault: false }}
                    onCancel={() => { setEditId(null); setErr(null); }}
                    onSubmit={(f) => onEdit(s.id, f)} />
                  <div style={{ display: "flex", gap: 10, margin: "-4px 2px 8px" }}>
                    <button className="btn-ghost" style={{ flex: 1 }} disabled={saving} onClick={() => onRetire(s)}>Reativar</button>
                    <button className="btn-ghost danger" style={{ flex: 1 }} disabled={saving} onClick={() => onDelete(s)}>Excluir</button>
                  </div>
                </div>
              ) : (
                <ShoeCard key={s.id} s={s} onEdit={() => { setEditId(s.id); setAdding(false); setErr(null); }} />
              )
            )}
          </>
        )}
      </div>
    </main>
  );
}

function ShoeCard({ s, onEdit }: { s: Shoe; onEdit: () => void }) {
  return (
    <section className={`card tap${s.retired ? " faded" : ""}`} onClick={onEdit}>
      <div className="shoe">
        <ShoeIcon />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="n">{s.label}</span>
            {s.is_default && <span className="tag ok">em uso</span>}
            {s.worn && !s.retired && <span className="tag warn">trocar</span>}
          </div>
          <div className="km">
            {String(s.total_km).replace(".", ",")} / {s.alert_threshold_km} km
            {s.category ? ` · ${s.category}` : ""}
            {!s.retired && !s.worn ? ` · faltam ~${s.remaining_km} km` : ""}
          </div>
          <div className="wear"><i style={{ width: `${s.pct}%` }} /></div>
        </div>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M9 6l6 6-6 6" /></svg>
      </div>
    </section>
  );
}
