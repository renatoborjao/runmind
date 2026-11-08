"""AUDITORIA DE PLANOS + CUSTO — roda na VM, SÓ LEITURA, ZERO chamada de IA.

Responde, com dado real:
  1. De onde veio o gasto de um dia (por atleta × rótulo × modelo, em chamadas,
     tokens e custo-sombra), pra achar o que queimou crédito.
  2. Como foi a sequência de planos de cada atleta: volume planejado semana a
     semana x km REALMENTE corridos, o que o coach disse sobre cada corte
     (deload/ajuste), e a repetição dos treinos (variedade).

    cd ~/runmind/backend && .venv/bin/python /tmp/plan_audit.py [--day 2026-11-06]
(normalmente via ops/plan_audit.sh, que traz o relatório pro repo local)"""

import argparse
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

STORAGE = Path("storage")
USD_BRL = 5.40
# preços de lista (USD/1M tokens): (entrada, saída) — igual report_tokens.py
PRICING = {
    "gemini-3.6-flash": (0.15, 0.60),
    "gemini-3.5-flash-lite": (0.075, 0.30),
    "gemini-3.1-pro-preview": (1.25, 10.00),
    "_default": (0.15, 0.60),
}


def jload(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def cost(model, rec) -> float:
    pin, pout = PRICING.get(model, PRICING["_default"])
    in_t = rec.get("in") or 0
    out_t = (rec.get("out") or 0) + (rec.get("thoughts") or 0)
    return (in_t * pin + out_t * pout) / 1_000_000 * USD_BRL


def usage_section(day: str):
    print(f"## 1. Consumo de IA em {day}\n")
    rows = []
    for f in sorted((STORAGE / "token_usage").glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            rows.append(r)
    if not rows:
        print("(sem registros de token)\n")
        return
    keys = sorted(rows[0].keys())
    print(f"campos do registro: {keys}\n")
    by_day = defaultdict(lambda: [0, 0.0])
    for r in rows:
        d = (r.get("ts") or "")[:10]
        by_day[d][0] += 1
        by_day[d][1] += cost(r.get("model", "?"), r)
    print("Últimos 10 dias (chamadas · custo-sombra R$):")
    for d in sorted(by_day)[-10:]:
        print(f"  {d}: {by_day[d][0]:>5} chamadas · R$ {by_day[d][1]:.2f}")
    print()
    sel = [r for r in rows if (r.get("ts") or "").startswith(day)]
    agg = defaultdict(lambda: [0, 0.0])
    hours = Counter()
    for r in sel:
        k = (r.get("profile", "?"), r.get("label", "?"), r.get("model", "?"))
        agg[k][0] += 1
        agg[k][1] += cost(r.get("model", "?"), r)
        hours[(r.get("ts") or "")[11:13]] += 1
    print(f"{day}: {len(sel)} chamadas. Maiores (atleta · rótulo · modelo):")
    for k, (n, c) in sorted(agg.items(), key=lambda x: -x[1][1])[:25]:
        print(f"  R$ {c:6.2f} · {n:>4}× · {k[0]} · {k[1]} · {k[2]}")
    print("\nChamadas por hora UTC:", dict(sorted(hours.items())))
    print()


def monday(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return (d - timedelta(days=d.weekday())).isoformat()


def real_km_by_week(profile: str) -> dict:
    out = defaultdict(float)
    acts = jload(STORAGE / "activities" / f"{profile}.json") or []
    kept = []
    for a in sorted(acts, key=lambda x: x.get("start_date") or ""):
        try:
            t = datetime.fromisoformat((a.get("start_date") or "").replace("Z", "+00:00"))
        except Exception:
            continue
        d = a.get("distance") or 0
        dup = any(
            abs((t - kt).total_seconds()) <= 4 * 3600 and abs(d - kd) <= 0.05 * max(d, kd, 1)
            for kt, kd in kept
        )
        if not dup:
            kept.append((t, d))
            a["_ded"] = True
    for a in acts:
        if not a.get("_ded"):
            continue
        if (a.get("sport") or "Run") not in ("Run", "TrailRun", "VirtualRun"):
            continue
        sd = (a.get("start_date") or "")[:10]
        if sd:
            out[monday(sd)] += (a.get("distance") or 0) / 1000
    return out


def plans_section():
    print("## 2. Sequência de planos por atleta\n")
    profiles = sorted(
        p.stem for p in (STORAGE / "plans").glob("*.json") if p.stem != "runner_profile"
    )
    for prof in profiles:
        cur = jload(STORAGE / "plans" / f"{prof}.json")
        hist = jload(STORAGE / "plans" / "history" / f"{prof}.json") or []
        entries = {e["week_start"]: e for e in hist}
        if cur:
            entries[cur["week_start"]] = cur
        if not entries:
            continue
        real = real_km_by_week(prof)
        print(f"### {prof} — {cur.get('athlete_name') if cur else ''}")
        if cur:
            print(f"objetivo: {cur.get('objective')}")
        print()
        print("semana       | plan km | real km | deload | fonte    | sessões (tipo km)")
        prev_types = None
        repeats = 0
        types_all = Counter()
        weeks = sorted(entries)
        for w in weeks:
            e = entries[w]
            ses = [s for s in e.get("sessions", []) if s.get("kind", "run") == "run"]
            desc = " · ".join(
                f"{(s.get('workout_type') or '?')[:18]} {s.get('planned_distance_km') or s.get('estimated_distance_km') or '-'}"
                for s in ses
            )
            ts = tuple(sorted((s.get("workout_type") or "?") for s in ses))
            if prev_types is not None and ts == prev_types:
                repeats += 1
            prev_types = ts
            for s in ses:
                types_all[s.get("workout_type") or "?"] += 1
            print(
                f"{w} | {str(e.get('weekly_volume')):>7} | {real.get(w, 0):7.1f} | "
                f"{'SIM' if e.get('is_deload') else '   '}    | {str(e.get('source'))[:8]:8} | {desc}"
            )
        print(f"\nsemanas com a MESMA combinação de tipos da anterior: {repeats} de {max(0, len(weeks) - 1)}")
        print("tipos mais frequentes:", dict(types_all.most_common(6)))
        print("\nPor que o coach cortou/ajustou (últimas semanas):")
        for w in weeks[-6:]:
            e = entries[w]
            why = e.get("deload_why") or ""
            wo = e.get("weekly_objective") or ""
            rn = e.get("route_note") or ""
            print(f"- {w}: deload={bool(e.get('is_deload'))} {why[:300]}")
            if rn:
                print(f"    rota: {rn[:400]}")
            if wo:
                print(f"    objetivo da semana: {wo[:300]}")
        print("\nEstrutura dos treinos nas 3 últimas semanas (variedade real):")
        for w in weeks[-3:]:
            for ses_ in entries[w].get("sessions", []):
                if ses_.get("kind", "run") != "run":
                    continue
                st = (ses_.get("structure") or "").replace("\n", " | ")[:170]
                print(f"  {w} {ses_.get('day','')[:3]} {ses_.get('workout_type')}: {st}")
        if cur and cur.get("route"):
            print("\nRota planejada até a prova (km faixa / vol):")
            for rw in cur["route"].get("weeks", [])[:8]:
                print(f"  {rw.get('w')} {rw.get('ph')} faixa {rw.get('km')} vol {rw.get('vol')} longão {rw.get('long')}")
        print("\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2026-11-06")
    ap.add_argument("--more-days", default="")
    a = ap.parse_args()
    print(f"# Auditoria de planos e custo — gerada {datetime.now():%Y-%m-%d %H:%M}\n")
    for d in [a.day] + [x for x in a.more_days.split(",") if x]:
        usage_section(d)
    plans_section()


if __name__ == "__main__":
    main()
