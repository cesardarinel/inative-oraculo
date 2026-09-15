"""JobLog Recorder — Record & Replay para IBM i (plan §0-§23).

Uso:
  python -m probe.joblog_recorder record --id JOBLOG-0001 --name "crtbndrpg success" --language RPGLE --command "CRTBNDRPG ..."
  python -m probe.joblog_recorder record --fixture conformance/messages/CPF0001.json
  python -m probe.joblog_recorder replay --id JOBLOG-0001
  python -m probe.joblog_recorder list

Sigue el flujo §4:

  INITIAL SNAPSHOT → EXECUTE OPERATION → FINAL SNAPSHOT → DIFF → FIXTURE (raw + normalized)

Cada experimento crea sesión identificable (experiment_id, timestamp, case, operation) §3
y guarda INITIAL/FINAL/DIFF (§4) + JobContext (§5).

Salida sigue §14 y §16:

  fixtures/joblog/
    raw/<ID>/capture.json         (exacto, con timestamps/job numbers reales)
    normalized/<ID>.json          (placeholder dynamic fields)
    manifests/<ID>.json           (cómo fue producido)
  o en modo legacy: esperado/<ID>.json compatible con comparador existente

Este archivo es la "herramienta de investigación/validación" separada del runtime
(internal/joblog es el runtime). No mezclar.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .colectores.job_info import capturar_job_info
from .colectores.joblog_v2 import capturar_joblog_snapshot, diff_snapshots, normalize_messages
from .config import load as load_config
from .conect import ConectarIBMi

RECORDER_VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW_DIR = ROOT / "fixtures" / "joblog" / "raw"
DEFAULT_NORM_DIR = ROOT / "fixtures" / "joblog" / "normalized"
DEFAULT_MANIFEST_DIR = ROOT / "fixtures" / "joblog" / "manifests"
DEFAULT_LEGACY_DIR = ROOT / "esperado"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _ensure_dirs():
    for d in [DEFAULT_RAW_DIR, DEFAULT_NORM_DIR, DEFAULT_MANIFEST_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def _experiment_id(prefix: str = "JOBLOG") -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    # Busca siguiente número en raw/
    n = 1
    if DEFAULT_RAW_DIR.exists():
        existing = [p.name for p in DEFAULT_RAW_DIR.iterdir() if p.is_dir()]
        nums = []
        for name in existing:
            if name.startswith(prefix):
                try:
                    parts = name.split("-")
                    nums.append(int(parts[-1]))
                except Exception:
                    pass
        if nums:
            n = max(nums) + 1
    return f"{prefix}-{n:04d}"

# ---------------------------------------------------------------------------
# Core: record one experiment
# ---------------------------------------------------------------------------

def record_experiment(
    *,
    experiment_id: str,
    name: str,
    language: str,
    category: str,
    command: str,
    program: str = "",
    library: str = "",
    expected_result: str = "unknown",
    source_file: str = "",
    use_initial_snapshot: bool = True,
    env_file: Path | None = None,
    ibmi_version: str | None = None,
) -> dict:
    """Ejecuta workflow INITIAL→EXECUTE→FINAL→DIFF y persiste fixtures.

    Retorna dict con paths generados.
    """
    cfg = load_config(env_file)
    errs = cfg.validate()
    if errs:
        raise SystemExit("Falta configuración: " + ", ".join(errs) + " — copia oracle.env.example a oracle.env")

    _ensure_dirs()
    con = ConectarIBMi(cfg)
    runner = None
    try:
        from .runner_ibmi import RunnerIBMi
        runner = RunnerIBMi(con)
    except Exception:
        pass

    ibmi_ver = ibmi_version or cfg.release or "7.5"

    print(f"[recorder] experiment {experiment_id} :: {name} ({language}/{category})")
    print(f"[recorder] command: {command}")

    # 1) Captura JobContext inicial
    job_ctx = capturar_job_info(con)
    print(f"[recorder] job: {job_ctx.get('job_name')} {job_ctx.get('job_user')}/{job_ctx.get('job_number')} via {job_ctx.get('source')}")

    # 2) INITIAL SNAPSHOT
    initial = None
    if use_initial_snapshot:
        print("[recorder] capturing INITIAL snapshot...")
        initial = capturar_joblog_snapshot(con)
        print(f"[recorder] initial: {initial['count']} messages via {initial['source']}")
        # Pequeña pausa para asegurar timestamp separation
        time.sleep(0.5)
    else:
        initial = {"captured_at": _now_iso(), "messages": [], "count": 0, "source": "SKIPPED"}

    # 3) EXECUTE OPERATION
    result_success = True
    exit_code = 0
    execution_output = ""
    op_extra: dict[str, Any] = {}

    if command and runner is not None:
        print(f"[recorder] executing: {command}")
        # Clasifica comando
        upper = command.strip().upper()
        try:
            if upper.startswith("CALL") or " CALL " in upper:
                res = runner.ejecutar_cl(command)
            elif upper.startswith("CRTBNDRPG") or upper.startswith("CRTRPGMOD") or upper.startswith("CRTPGM") or upper.startswith("CRT"):
                res = runner.compilar_listing(command)
            elif upper.startswith("SNDPGMMSG") or upper.startswith("SNDMSG") or upper.startswith("DSPLY"):
                res = runner.ejecutar_cl(command)
            else:
                # Comando genérico vía QCMDEXC / system
                res = runner.ejecutar_cl(command)
            result_success = bool(res.ok)
            exit_code = int(res.exit_code)
            execution_output = res.listing[:4000]
            op_extra["listing_preview"] = execution_output[:500]
            print(f"[recorder] result: ok={res.ok} exit={res.exit_code}")
        except Exception as e:
            result_success = False
            exit_code = 255
            execution_output = str(e)
            print(f"[recorder] execution error: {e}")
    elif command:
        # Sin runner (dry-run): simula ejecución local batch via ssh directo
        try:
            rc, out, err = con.sshes_raw(f'system "{command}"', timeout=60)
            result_success = rc == 0
            exit_code = rc
            execution_output = (out + err)[:4000]
            print(f"[recorder] raw system rc={rc}")
        except Exception as e:
            print(f"[recorder] raw exec failed: {e}")
            result_success = False

    # Espera mínima para que IBM i asiente el joblog
    time.sleep(0.8)

    # 4) FINAL SNAPSHOT
    print("[recorder] capturing FINAL snapshot...")
    final = capturar_joblog_snapshot(con)
    print(f"[recorder] final: {final['count']} messages via {final['source']}")

    # 5) DIFF — captura también listing stdout (system -b) que es la fuente real de mensajes de compilación/CALL (§9.2/§8)
    delta = diff_snapshots(initial, final)
    # Fallback: si delta vacío pero execution_output contiene mensajes (caso PASE system -b), parsea listing
    if len(delta) == 0 and execution_output.strip():
        try:
            from .colectores.mensajes import parsear_listing as _parse_listing
            from .colectores.joblog import parse_joblog_text as _parse_jl
            parsed = _parse_listing(execution_output)
            # Convierte Mensaje (RNF/RNS/CEE) a formato JobMessage rico
            for m in parsed:
                delta.append({
                    "message_id": m.codigo,
                    "message_type": "ESCAPE" if m.severidad and m.severidad >= 30 else "DIAGNOSTIC" if m.severidad and m.severidad >= 20 else "COMPLETION",
                    "severity": int(m.severidad) if m.severidad else 0,
                    "message_text": m.texto,
                    "message_second_level_text": "",
                    "message_timestamp": "",
                    "ordinal_position": len(delta)+1,
                    "from_library": "", "from_program": "",
                    "to_program": "", "message_key": "", "job_name": "",
                    "id": m.codigo, "sev": int(m.severidad) if m.severidad else 0, "text": m.texto, "ordinal": len(delta)+1,
                })
            # También prueba parse joblog plano (CEE/MCH/CPF sin *) si parsear_listing no capturó
            if not parsed:
                for jl in _parse_jl(execution_output):
                    if not any(d["message_id"]==jl["id"] for d in delta):
                        delta.append({
                            "message_id": jl["id"], "message_type": "ESCAPE" if jl["sev"]>=30 else "DIAGNOSTIC",
                            "severity": jl["sev"], "message_text": jl["text"], "message_second_level_text": "",
                            "message_timestamp": "", "ordinal_position": len(delta)+1,
                            "from_library": "", "from_program": "", "to_program": "", "message_key": "", "job_name": "",
                            "id": jl["id"], "sev": jl["sev"], "text": jl["text"], "ordinal": len(delta)+1,
                        })
            if delta:
                print(f"[recorder] delta vacío via JOBLOG_INFO, pero listing capturó {len(delta)} msgs via stdout")
        except Exception as e:
            print(f"[recorder] listing parse fallback falló: {e}")
    normalized = normalize_messages(delta)
    print(f"[recorder] delta: {len(delta)} messages (normalized {len(normalized)})")
    for i, m in enumerate(delta[:10]):
        print(f"  [{i+1}] {m['message_id']} {m['message_type']} sev={m['severity']} text={m['message_text'][:90]}")
    if len(delta) > 10:
        print(f"  ... +{len(delta)-10} more")

    # 6) Construye fixture (raw + normalized)
    # JobContext normalizado (placeholders)
    job_norm = dict(job_ctx)
    job_norm["job_name"] = "${JOB_NAME}"
    job_norm["job_user"] = "${JOB_USER}"
    job_norm["job_number"] = "${JOB_NUMBER}"
    job_norm["system_name"] = "${SYSTEM_NAME}"

    fixture_raw = {
        "fixture_version": 1,
        "source": f"IBM i {ibmi_ver}",
        "recorder_version": RECORDER_VERSION,
        "experiment": {
            "id": experiment_id,
            "name": name,
            "language": language,
            "operation": command.split()[0] if command else "",
            "category": category,
        },
        "job": job_norm,
        "job_raw": job_ctx,
        "operation": {
            "command": command,
            "program": program,
            "library": library or cfg.lib,
            "extra": op_extra,
        },
        "result": {
            "success": result_success,
            "exit_code": exit_code,
        },
        "joblog": {
            "messages": normalized,
            "raw_messages": delta,
            "initial_count": initial["count"],
            "final_count": final["count"],
            "delta_count": len(delta),
        },
        "raw": {
            "initial_snapshot": initial,
            "final_snapshot": final,
            "delta": delta,
            "ibmi_version": ibmi_ver,
            "captured_at": _now_iso(),
            "host": cfg.host,
        },
        "manifest": {
            "id": experiment_id,
            "language": language,
            "source_file": source_file,
            "command": command,
            "execution": command,
            "expected_result": expected_result,
            "ibmi_version": ibmi_ver,
            "captured_at": _now_iso(),
            "fixture_status": "CAPTURED",
            "recorder_version": RECORDER_VERSION,
            "notes": f"delta {len(delta)} msgs; initial {initial['count']} -> final {final['count']}",
        },
    }

    fixture_normalized = {
        "fixture_version": 1,
        "source": f"IBM i {ibmi_ver}",
        "experiment": fixture_raw["experiment"],
        "job": job_norm,
        "operation": fixture_raw["operation"],
        "result": fixture_raw["result"],
        "joblog": {
            "messages": normalized,
            "initial_count": initial["count"],
            "final_count": final["count"],
            "delta_count": len(delta),
        },
        "manifest": {
            "id": experiment_id,
            "language": language,
            "command": command,
            "expected_result": expected_result,
            "ibmi_version": ibmi_ver,
            "captured_at": fixture_raw["manifest"]["captured_at"],
            "fixture_status": "CAPTURED",
        },
    }

    # 7) Persistencia dual §14
    raw_dir = DEFAULT_RAW_DIR / experiment_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / "capture.json"
    norm_path = DEFAULT_NORM_DIR / f"{experiment_id}.json"
    manifest_path = DEFAULT_MANIFEST_DIR / f"{experiment_id}.json"
    legacy_path = DEFAULT_LEGACY_DIR / f"{experiment_id}.json"

    raw_path.write_text(json.dumps(fixture_raw, ensure_ascii=False, indent=2), encoding="utf-8")
    norm_path.write_text(json.dumps(fixture_normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_path.write_text(json.dumps(fixture_raw["manifest"], ensure_ascii=False, indent=2), encoding="utf-8")

    # Legacy: también escribe en esperado/ para compatibilidad con comparador existente
    # como observable joblog
    legacy_snapshot = {
        "contrato_version": 1,
        "fixture": experiment_id,
        "ibmi": {"host": cfg.host, "release": ibmi_ver, "ccsid": cfg.ccsid, "capturado": _now_iso()},
        "observables": [
            {"kind": "joblog", "name": "mensajes", "value": normalized},
            {"kind": "return", "name": "rc", "value": exit_code},
        ],
    }
    DEFAULT_LEGACY_DIR.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(json.dumps(legacy_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[recorder] raw        → {raw_path}")
    print(f"[recorder] normalized → {norm_path}")
    print(f"[recorder] manifest   → {manifest_path}")
    print(f"[recorder] legacy     → {legacy_path}")

    con.close()

    return {
        "experiment_id": experiment_id,
        "raw": str(raw_path),
        "normalized": str(norm_path),
        "manifest": str(manifest_path),
        "legacy": str(legacy_path),
        "delta_count": len(delta),
        "success": result_success,
    }

# ---------------------------------------------------------------------------
# Replay (sin IBM i)
# ---------------------------------------------------------------------------

def replay_experiment(experiment_id: str) -> dict:
    """Carga fixture normalizado y lo expone como behavior esperado (mock).

    Retorna dict fixture_normalized para que iNative pueda inyectarlo en tests.
    """
    norm_path = DEFAULT_NORM_DIR / f"{experiment_id}.json"
    raw_path = DEFAULT_RAW_DIR / experiment_id / "capture.json"
    target = norm_path if norm_path.exists() else raw_path
    if not target.exists():
        # Busca en legacy
        legacy = DEFAULT_LEGACY_DIR / f"{experiment_id}.json"
        if legacy.exists():
            target = legacy
        else:
            raise SystemExit(f"Fixture no encontrado: {experiment_id} (buscado en {norm_path} y {raw_path})")
    data = json.loads(target.read_text(encoding="utf-8"))
    # Si es legacy format, conviértelo
    if "observables" in data:
        # legacy
        joblog = next((o["value"] for o in data["observables"] if o.get("kind")=="joblog"), [])
        print(f"[replay] {experiment_id}: {len(joblog)} mensajes (legacy)")
        for m in joblog[:10]:
            mid = m.get("message_id") or m.get("id")
            print(f"  {mid} sev={m.get('severity', m.get('sev'))} {m.get('message_text', m.get('text',''))[:80]}")
        return data
    msgs = data.get("joblog", {}).get("messages", []) if isinstance(data.get("joblog"), dict) else []
    print(f"[replay] {experiment_id}: {len(msgs)} mensajes")
    for m in msgs[:15]:
        print(f"  {m['message_id']} {m['message_type']} sev={m['severity']} {m['message_text'][:100]}")
    if len(msgs) > 15:
        print(f"  ... +{len(msgs)-15} more")
    return data

# ---------------------------------------------------------------------------
# Catalog matrix (§6-§13)
# ---------------------------------------------------------------------------

MATRIX = [
    # Nivel 1 — comandos exitosos
    {"id": "CMD-SUCCESS-001", "name": "crtbndrpg success", "language": "RPGLE", "category": "commands/success", "command": "CRTBNDRPG PGM(QTEMP/HELLO) SRCSTMF('/tmp/hello.rpgle')", "expected": "success"},
    # Nivel 2 — errores comandos
    {"id": "CMD-ERR-001", "name": "invalid command", "language": "CMD", "category": "commands/invalid-command", "command": "CRTBNDRPG PGM(QTEMP/X) SRCSTMF('/no/existe.rpgle')", "expected": "error"},
    {"id": "CMD-ERR-002", "name": "object not found CALL", "language": "CMD", "category": "commands/object-not-found", "command": "CALL PGM(QTEMP/NOTEXIST)", "expected": "error"},
    {"id": "CMD-ERR-003", "name": "library not found", "language": "CMD", "category": "commands/library-not-found", "command": "CRTLIB LIB(QTEMP_FAKE_1234)", "expected": "error"},
    # Nivel 3 — compile errors RPG
    {"id": "RPG-COMPILE-001", "name": "variable no declarada", "language": "RPGLE", "category": "rpgle/compile/semantic-error", "command": "CRTBNDRPG PGM(QTEMP/BADVAR) SRCSTMF('/tmp/badvar.rpgle')", "expected": "compile_error"},
    # Nivel 4 — runtime RPG
    {"id": "RPG-RUNTIME-001", "name": "divide by zero", "language": "RPGLE", "category": "rpgle/runtime/divide-by-zero", "command": "CALL PGM(QTEMP/DIVZERO)", "expected": "runtime_error"},
    {"id": "RPG-RUNTIME-002", "name": "file not found", "language": "RPGLE", "category": "rpgle/runtime/file-not-found", "command": "CALL PGM(QTEMP/FILENOTF)", "expected": "runtime_error"},
    # Nivel 5 — File I/O
    {"id": "FILEIO-CHAIN-001", "name": "chain not found", "language": "RPGLE", "category": "fileio/chain", "command": "CALL PGM(QTEMP/CHAIN01)", "expected": "runtime_error"},
    # Nivel 6 — CL
    {"id": "CL-SUCCESS-001", "name": "cl sndpgmmsg", "language": "CL", "category": "cl/message-handling", "command": "SNDPGMMSG MSG('HELLO') TOPGMQ(*PRV)", "expected": "success"},
    {"id": "CL-MONMSG-001", "name": "monmsg cpf", "language": "CL", "category": "cl/monmsg", "command": "MONMSG MSGID(CPF0000) EXEC(DO)", "expected": "success"},
    # Nivel 7 — mensajes program
    {"id": "MSG-SNDPGMMSG-001", "name": "sndpgmmsg informational", "language": "CL", "category": "messages/sndpgmmsg", "command": "SNDPGMMSG MSGID(CPF9897) MSGF(QCPFMSG) MSGTYPE(*INFO)", "expected": "success"},
    # Nivel 8 — diagnostic chain
    {"id": "MSG-DIAG-001", "name": "diagnostic chain", "language": "CMD", "category": "messages/diagnostic", "command": "DLTF FILE(QTEMP/NOTEXIST)", "expected": "error"},
]

def list_matrix():
    print(f"{'ID':<22} {'LANGUAGE':<8} {'CATEGORY':<35} {'COMMAND'}")
    print("-"*120)
    for e in MATRIX:
        print(f"{e['id']:<22} {e['language']:<8} {e['category']:<35} {e['command'][:50]}")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="JobLog Recorder — Record & Replay (iNative Mock Runtime)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("record", help="Captura contra IBM i real (Record mode)")
    p_rec.add_argument("--id", dest="exp_id", help="Experiment ID (ej JOBLOG-0001); si no se da, autoincrementa")
    p_rec.add_argument("--name", default="ad-hoc")
    p_rec.add_argument("--language", default="CMD", help="RPGLE|CL|CMD|FILEIO|MESSAGE")
    p_rec.add_argument("--category", default="commands/success")
    p_rec.add_argument("--command", required=False, help="Comando CL a ejecutar")
    p_rec.add_argument("--fixture", help="Fixture JSON legacy (usa su 'command'/'input')")
    p_rec.add_argument("--source-file", default="")
    p_rec.add_argument("--expected", default="unknown")
    p_rec.add_argument("--env", dest="env_file", help="Ruta oracle.env")
    p_rec.add_argument("--auto-id", action="store_true", help="Genera ID automático aunque se pase --id")
    p_rec.add_argument("--no-initial", action="store_true", help="No captura INITIAL snapshot (solo FINAL)")

    p_rep = sub.add_parser("replay", help="Reproduce fixture sin IBM i (Replay mode)")
    p_rep.add_argument("experiment_id", nargs="?", help="ID a reproducir")
    p_rep.add_argument("--id", dest="replay_id", help="Alias de experiment_id")

    p_list = sub.add_parser("list", help="Lista matriz de experimentos")
    p_list.add_argument("--all", action="store_true")

    p_matrix = sub.add_parser("record-matrix", help="Captura toda la matriz §6-§13 (smoke)")

    args = parser.parse_args()

    if args.cmd == "record":
        exp_id = args.exp_id or _experiment_id()
        if args.auto_id:
            exp_id = _experiment_id()
        # Si se pasa --fixture, extrae comando de ahí
        cmd = args.command or ""
        if args.fixture:
            fp = Path(args.fixture)
            if not fp.exists():
                raise SystemExit(f"Fixture no existe: {fp}")
            data = json.loads(fp.read_text(encoding="utf-8"))
            # Busca comando en input/setup/source
            inputs = data.get("input") or data.get("inputs") or []
            for step in inputs:
                if isinstance(step, dict) and step.get("type") in ("command","cmd"):
                    cmd = step.get("value") or step.get("command") or cmd
                    break
            if not cmd:
                # fallback: usa fixture id como hint
                cmd = f"CALL PGM(QTEMP/{fp.stem[:10].upper()})"
        if not cmd:
            parser.error("--command o --fixture requerido")
        record_experiment(
            experiment_id=exp_id,
            name=args.name,
            language=args.language,
            category=args.category,
            command=cmd,
            expected_result=args.expected,
            source_file=args.source_file,
            env_file=Path(args.env_file) if args.env_file else None,
            use_initial_snapshot=not args.no_initial,
        )

    elif args.cmd == "replay":
        eid = args.experiment_id or args.replay_id
        if not eid:
            # lista disponibles
            print("Fixtures disponibles (normalized):")
            if DEFAULT_NORM_DIR.exists():
                for p in sorted(DEFAULT_NORM_DIR.glob("*.json")):
                    print(f"  {p.stem}")
            if DEFAULT_RAW_DIR.exists():
                for p in sorted(DEFAULT_RAW_DIR.iterdir()):
                    if p.is_dir():
                        print(f"  {p.name} (raw)")
            sys.exit(0)
        replay_experiment(eid)

    elif args.cmd == "list":
        list_matrix()

    elif args.cmd == "record-matrix":
        print("[recorder] capturing smoke matrix (requiere IBM i real)...")
        for e in MATRIX:
            try:
                record_experiment(
                    experiment_id=e["id"],
                    name=e["name"],
                    language=e["language"],
                    category=e["category"],
                    command=e["command"],
                    expected_result=e["expected"],
                )
            except SystemExit as se:
                print(f"[recorder] {e['id']} abortado: {se}")
            except Exception as ex:
                print(f"[recorder] {e['id']} falló: {ex}")

if __name__ == "__main__":
    main()
