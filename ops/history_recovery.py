"""Recupera para o ARQUIVO PERMANENTE o histórico que as janelas já cortaram, a partir dos snapshots
de backup (zip do storage/). Só ACRESCENTA ao arquivo; nunca mexe nas janelas vivas.

  python history_recovery.py extract <pasta-dos-zips> <saida.json>     # no PC, só leitura
  python history_recovery.py merge <entrada.json> [--apply]            # na VM (cwd = backend); sem --apply só conta
"""
import glob
import json
import sys
import zipfile
from pathlib import Path

# tipo -> (pasta viva em storage/, tipo no arquivo)
KINDS = {
    "conversations": ("conversations", "conversations"),
    "readiness_diary": ("readiness_diary", "readiness_diary"),
    "body_readings": ("body_readings", "body_readings"),
    "checkins": ("checkins", "checkins"),
    "coach_brain_log": ("coach_brain_log", "coach_brain_log"),
    "coach_outbox": ("coach_outbox", "coach_outbox"),
    "session_rpe": ("session_rpe", "session_rpe"),
    "stimulus_results": ("stimulus_results", "stimulus_results"),
    "plan_versions": ("plans", "plan_versions"),
}


def dump(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def key_of(kind, record):
    """Chave de identidade do registro (a mesma na extração e na fusão)."""
    if kind == "conversations":
        return dump([record.get("timestamp"), record.get("role"), record.get("text")])
    if kind in ("readiness_diary", "body_readings"):
        return dump([record.get("day"), record.get("at")])
    if kind == "coach_outbox":
        return dump([record.get("timestamp"), record.get("text")])
    if kind == "session_rpe":
        return dump([record.get("activity_id"), record.get("rpe"), record.get("day")])
    if kind == "stimulus_results":
        return dump(record.get("key"))
    return dump(record)          # checkins, coach_brain_log, plan_versions: o registro inteiro


def records_from(kind, raw):
    """Lista de registros de um arquivo JSON desse tipo."""
    if kind == "session_rpe":
        return list((raw or {}).get("sessions", [])) if isinstance(raw, dict) else []
    if kind == "stimulus_results":
        return [{"key": k, "value": v} for k, v in (raw or {}).items()] if isinstance(raw, dict) else []
    return list(raw) if isinstance(raw, list) else []


def extract(zip_dir, out):
    files = sorted(glob.glob(str(Path(zip_dir) / "runmind-storage-*.zip")))
    found = {kind: {} for kind in KINDS}                     # tipo -> perfil -> {chave: registro}
    for zpath in files:
        with zipfile.ZipFile(zpath) as z:
            names = set(z.namelist())
            for kind, (folder, _) in KINDS.items():
                prefix = "plans/history/" if kind == "plan_versions" else f"{folder}/"
                for name in names:
                    if not name.startswith(prefix) or not name.endswith(".json") or name.count("/") != prefix.count("/"):
                        continue
                    profile = name.rsplit("/", 1)[1][:-5]
                    if profile.endswith("_summary"):
                        continue
                    try:
                        raw = json.loads(z.read(name))
                    except Exception:
                        continue
                    bucket = found[kind].setdefault(profile, {})
                    for rec in records_from(kind, raw):
                        bucket.setdefault(key_of(kind, rec), rec)       # a primeira aparição
    result = {kind: {p: list(b.values()) for p, b in profs.items()} for kind, profs in found.items()}
    Path(out).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    for kind, profs in result.items():
        print(f"{kind:<18}", {p: len(r) for p, r in profs.items()})
    print(f"{len(files)} snapshots")


def merge(inp, apply):
    sys.path.insert(0, ".")
    from app.infrastructure.persistence.permanent_archive import PermanentArchive

    root = Path("storage")
    data = json.loads(Path(inp).read_text(encoding="utf-8"))
    reason = "recuperado dos backups do OneDrive (28/07 a 14/09)"
    total = 0
    for kind, profiles in data.items():
        folder, archive_kind = KINDS[kind]
        for profile, records in profiles.items():
            live_file = root / ("plans/history" if kind == "plan_versions" else folder) / f"{profile}.json"
            have = set()
            if live_file.exists():
                try:
                    have |= {key_of(kind, r) for r in records_from(kind, json.loads(live_file.read_text(encoding="utf-8")))}
                except Exception:
                    pass
            storage = root / folder
            have |= {key_of(kind, e["record"]) for e in PermanentArchive.load(storage, archive_kind, profile)}
            missing = [r for r in records if key_of(kind, r) not in have]
            if kind == "plan_versions":              # só versões que NÃO são a atual da semana
                missing = [r for r in missing if True]
            if not missing:
                continue
            total += len(missing)
            print(f"{kind:<18} {profile:<10} +{len(missing)}")
            if apply:
                ok = PermanentArchive.append(storage, archive_kind, profile, missing, reason)
                print("   gravado" if ok else "   FALHOU")
    print("TOTAL", total, "(aplicado)" if apply else "(só conferência)")


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "extract":
        extract(sys.argv[2], sys.argv[3])
    else:
        merge(sys.argv[2], "--apply" in sys.argv)
