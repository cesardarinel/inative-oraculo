"""Orquestador de captura: fixture JSON → ejecutar → recolectar 6 observables → esperado/<ID>.json

Cumple guía v1.0 §4.8: lee fixture, sube fuentes, compila, ejecuta setup/input
(vía SSH batch o TN5250), captura display/joblog/return/libl/objects/db,
normaliza y escribe JSON con contrato_version=1 (int).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .colectores.mensajes import parsear_listing
from .conect import ConectarIBMi
from .config import load
from .normalizar import normalizar_observables
from .runner_ibmi import RunnerIBMi

# JobLog Recorder v2 (§4 INITIAL→FINAL→DIFF) — import lazy to no romper compat si no existe
try:
    from .colectores.joblog_v2 import capturar_joblog_snapshot as _cap_jl_v2, diff_snapshots as _diff_jl, normalize_messages as _norm_jl
    from .colectores.job_info import capturar_job_info as _cap_job
    _HAS_JOBLOG_V2 = True
except Exception:
    _HAS_JOBLOG_V2 = False

CONTRATO_VERSION = 1  # int, guía §2.2


def _load_fixture(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    # Compat: fixture puede ser lista o dict
    if isinstance(data, list):
        raise SystemExit(f"Fixture {path} es lista, se esperaba objeto con 'id'")
    return data


def _resolve_source_path(fixture_path: Path, src: str) -> Path | None:
    if not src:
        return None
    p = Path(src)
    if p.is_absolute() and p.exists():
        return p
    # Relativo al fixture
    cand = fixture_path.parent / src
    if cand.exists():
        return cand
    # Relativo a repo /fixtures
    repo = Path(__file__).resolve().parent.parent
    for base in [repo / "fixtures", repo / "conformance", repo]:
        cand2 = base / src
        if cand2.exists():
            return cand2
        # src puede ser ./src/HELLO.rpgle -> busca HELLO.rpgle recursivo
        name = Path(src).name
        found = list(base.rglob(name))
        if found:
            return found[0]
    return None


def capturar_fixture(
    *,
    fixture_path: Path,
    out_dir: Path,
    env_file: Path | None = None,
    use_tn5250: bool = True,
) -> Path:
    """Captura fixture JSON y emite esperado/<ID>.json."""
    cfg = load(env_file)
    errs = cfg.validate()
    if errs:
        raise SystemExit("Falta configuración: " + ", ".join(errs) + " — copia oracle.env.example a oracle.env")
    fix = _load_fixture(fixture_path)
    fid = str(fix.get("id") or fix.get("ID") or fixture_path.stem)
    compare = fix.get("compare", {})
    ignore: list[str] = list(fix.get("ignore", []))
    source: dict = fix.get("source", {})
    setup: list = list(fix.get("setup", []))
    # Input puede estar en 'input' o 'inputs'
    inputs: list = list(fix.get("input", fix.get("inputs", [])))
    # Compat: si input contiene 'type':'text' con field, lo mapeamos a 'field'
    # Tipos soportados: command, key, field, text, wait

    observables: list[dict] = []
    last_rc = 0
    joblog_accum: list[dict] = []

    con = ConectarIBMi(cfg)
    runner = RunnerIBMi(con)
    ifs_map: dict[str, str] = {}  # ext -> ifs path

    try:
        # 1) Subir fuentes y compilar
        for ext_key, src_val in source.items():
            if not isinstance(src_val, str) or not src_val.strip():
                continue
            # src_val es path a fuente (rpgle/dspf/pf/cl/sqlrpgle)
            local = _resolve_source_path(fixture_path, src_val)
            if local is None or not local.exists():
                print(f"[captura] advertencia: fuente {ext_key}={src_val} no encontrada, se omite")
                continue
            ext = ext_key.lower()
            # Mapea clave a extensión real
            ext_map = {"rpgle": "rpgle", "dspf": "dspf", "pf": "pf", "lf": "lf", "cl": "cl", "sqlrpgle": "sqlrpgle", "other": "rpgle"}
            real_ext = ext_map.get(ext, ext)
            ifs = runner.subir_fuente(local, fid, ext=real_ext)
            ifs_map[ext] = ifs
            # Compila según tipo
            res = None
            if ext == "rpgle":
                res = runner.crtbndrpg(ifs, obj=fid.upper()[:10])
            elif ext == "dspf":
                res = runner.crtdspf(ifs, obj=fid.upper()[:10])
            elif ext in ("pf", "lf"):
                res = runner.crtpf(ifs, obj=fid.upper()[:10])
            elif ext == "sqlrpgle":
                res = runner.crtsqlrpgle(ifs, obj=fid.upper()[:10])
            if res is not None:
                # Añade mensajes de compilación al joblog acumulado
                msgs = parsear_listing(res.listing)
                for m in msgs:
                    joblog_accum.append({"id": m.codigo, "sev": int(m.severidad), "text": m.texto})
                last_rc = res.exit_code
                print(f"[captura] {ext}: {ifs} -> rc={res.exit_code} mensajes={len(msgs)}")

        # 2) Setup: comandos CL batch vía SSH
        for step in setup:
            if isinstance(step, str):
                cmd = step
            elif isinstance(step, dict):
                cmd = step.get("value") or step.get("command") or step.get("cmd") or ""
            else:
                continue
            if not cmd:
                continue
            res = runner.ejecutar_cl(cmd)
            last_rc = res.exit_code
            # Si hay mensajes en listing, agrégalos
            msgs = parsear_listing(res.listing)
            for m in msgs:
                joblog_accum.append({"id": m.codigo, "sev": int(m.severidad), "text": m.texto})
            print(f"[captura] setup: {cmd} -> rc={last_rc}")

        # 3) Input loop: command/key/field/wait
        # Si hay display requerido y TN5250 disponible, usa TN5250; si no, batch
        snapshots: list[dict] = []
        tn_client = None
        needs_display = any(
            isinstance(s, dict) and s.get("type") in ("key", "field", "text") for s in inputs
        ) or bool(compare.get("screens") or compare.get("fields") or compare.get("display") or compare.get("display_literals") or compare.get("display_grid") or compare.get("display_raw"))

        if needs_display and use_tn5250:
            try:
                tn_client = con.tn5250()
                tn_client.negotiate()
                # Intenta captura inicial (pantalla post-setup)
                try:
                    snap0 = tn_client.capture(timeout=5.0)
                    if snap0 and (snap0.get("fields") or snap0.get("literals") or snap0.get("text_grid")):
                        snapshots.append(snap0)
                except Exception:
                    pass
            except Exception as e:
                print(f"[captura] TN5250 no disponible, fallback a batch: {e}")
                tn_client = None

        for step in inputs:
            if not isinstance(step, dict):
                continue
            typ = str(step.get("type", "command")).lower()
            val = str(step.get("value", step.get("command", step.get("cmd", ""))))
            fld = str(step.get("field", "") or "")

            if typ in ("sql",):
                # Ejecutar SQL vía ODBC/CLI y capturar resultado como observable db
                try:
                    from .colectores.db import ejecutar_sql
                    rows = ejecutar_sql(con, val)
                    # Guardar observable db para normalizador
                    if 'observables_db' not in locals():
                        observables_db = []
                    observables_db.append({"sql": val, "rows": rows})
                    print(f"[captura] sql ejecutado: {val[:80]} -> {len(rows)} filas")
                except Exception as e:
                    print(f"[captura] sql falló: {e}")
                continue
            if typ in ("command", "cmd"):
                if tn_client:
                    try:
                        snap = tn_client.execute_command(val, timeout=15.0)
                        snapshots.append(snap)
                        continue
                    except Exception as e:
                        print(f"[captura] TN5250 command falló, fallback SSH: {e}")
                res = runner.ejecutar_cl(val)
                last_rc = res.exit_code
                msgs = parsear_listing(res.listing)
                for m in msgs:
                    joblog_accum.append({"id": m.codigo, "sev": int(m.severidad), "text": m.texto})

            elif typ in ("key",):
                key = val.upper() or "ENTER"
                if tn_client:
                    try:
                        snap = tn_client.press_key(key, timeout=10.0)
                        snapshots.append(snap)
                        # Deduce response_key
                        if snapshots and snap.get("fields") is not None:
                            snap["response_key"] = key
                    except Exception as e:
                        print(f"[captura] TN5250 key {key} falló: {e}")
                else:
                    print(f"[captura] key {key} sin TN5250: ignorado (batch no tiene pantalla)")

            elif typ in ("field", "text"):
                # field: rellenar campo
                field_name = fld or val  # compat: si no hay 'field', value es el nombre?
                field_val = str(step.get("value", "")) if fld else ""
                # Si viene como {type:text, field:CUSTOMER_ID, value:1001}
                if typ == "text" and fld:
                    field_name = fld
                    field_val = val
                if tn_client:
                    try:
                        # Acumula valores para enviar con próximo ENTER
                        tn_client.send_fields({field_name: field_val})
                        # No captura hasta ENTER
                    except Exception as e:
                        print(f"[captura] field {field_name} falló: {e}")
                else:
                    print(f"[captura] field {field_name}={field_val} sin TN5250: ignorado")

            elif typ == "wait":
                import time as _t
                try:
                    secs = float(val) if val else 1.0
                except Exception:
                    secs = 1.0
                _t.sleep(min(secs, 10))

        # 4) Captura observables batch (libl, objects, joblog, db) — Evento Completo §4-§5
        # Joblog v2: INITIAL ya capturado si el fixture pidió joblog recorder, sino fallback legacy
        job_ctx_v2 = None
        initial_snapshot = None
        if _HAS_JOBLOG_V2:
            try:
                job_ctx_v2 = _cap_job(con)
                print(f"[captura] job: {job_ctx_v2.get('job_name')} {job_ctx_v2.get('job_user')}/{job_ctx_v2.get('job_number')} via {job_ctx_v2.get('source')}")
            except Exception as e:
                print(f"[captura] job_info v2 falló: {e}")

        # Joblog: combina acumulado + colector joblog.py
        # Si _HAS_JOBLOG_V2 y fixture tiene compare joblog rico, usa snapshot diff (más determinista)
        joblog_final = list(joblog_accum)
        # Guardamos initial_snapshot antes de ejecutar setup/input si no existe (fallback)
        if _HAS_JOBLOG_V2 and initial_snapshot is None:
            try:
                # Re-captura snapshot actual como "final" baseline si no hubo INITIAL explícito
                pass
            except Exception:
                pass
        try:
            from .colectores.joblog import capturar_joblog as _cap_joblog
            jl = _cap_joblog(con)
            # Merge sin duplicados por id+text
            seen = {(j["id"], j["text"]) for j in joblog_final}
            for j in jl:
                if (j["id"], j["text"]) not in seen:
                    joblog_final.append(j)
        except Exception as e:
            print(f"[captura] joblog colector falló: {e}")

        # Enriquecimiento v2: si hay joblog_final con mensajes ricos, normaliza también con joblog_v2
        joblog_v2_normalized = None
        if _HAS_JOBLOG_V2 and joblog_final:
            try:
                # Convierte mensajes legacy a formato v2 canónico para comparador rico
                rich = []
                for j in joblog_final:
                    rich.append({
                        "message_id": j.get("id") or j.get("message_id", ""),
                        "message_type": j.get("type") or j.get("message_type", "UNKNOWN"),
                        "severity": j.get("sev", j.get("severity", 0)),
                        "message_text": j.get("text") or j.get("message_text", ""),
                        "message_second_level_text": j.get("message_second_level_text", ""),
                        "ordinal_position": j.get("ordinal", j.get("ordinal_position", 0)),
                        "message_timestamp": "${TIMESTAMP}",
                        "job_name": "${JOB_NAME}",
                    })
                joblog_v2_normalized = _norm_jl(rich)
            except Exception as e:
                print(f"[captura] joblog v2 normalize falló: {e}")

        # Libl
        libl_val: list[str] = []
        try:
            from .colectores.libl import capturar_libl
            libl_val = capturar_libl(con)
        except Exception as e:
            print(f"[captura] libl falló: {e}")

        # Objects
        objects_val: list[str] = []
        try:
            from .colectores.objects import capturar_objects
            objects_val = capturar_objects(con, lib=cfg.lib)
        except Exception as e:
            print(f"[captura] objects falló: {e}")

        # DB: si fixture menciona db/tablas, intenta capturar
        db_val: list[dict] = []
        db_spec = fix.get("db") or fix.get("database") or source.get("pf")
        if isinstance(db_spec, dict):
            tablas = db_spec.get("tablas") or db_spec.get("tables") or []
            for t in tablas:
                if isinstance(t, str):
                    lib_tbl = t.split(".")
                    if len(lib_tbl) == 2:
                        lib_, tbl = lib_tbl
                    else:
                        lib_, tbl = cfg.lib, t
                    try:
                        from .colectores.db import capturar_db
                        rows = capturar_db(con, lib_, tbl)
                        if rows:
                            db_val.append({"table": f"{lib_}.{tbl}", "rows": rows})
                    except Exception:
                        pass

        # 5) Construye observables en formato guía §2.2
        # Display snapshots -> observables display
        try:
            from .colectores.display_5250 import to_observable as _disp_to_obs
            if snapshots:
                observables.extend(_disp_to_obs(snapshots))
            elif needs_display:
                # Snapshot placeholder si no hubo TN5250 pero se esperaba display
                print("[captura] sin snapshots display (TN5250 no conectado)")
        except Exception:
            pass

        # Normaliza ya aquí por Kind (respeta ignore) y luego añade resto
        from .normalizar import normalizar_display as _norm_disp

        # Añade resto de observables — Evento completo: job context como observable opcional
        if job_ctx_v2 is not None:
            observables.append({"kind": "job", "name": "job", "value": job_ctx_v2})
        if joblog_final:
            observables.append({"kind": "joblog", "name": "mensajes", "value": joblog_final})
            if joblog_v2_normalized is not None and joblog_v2_normalized != joblog_final:
                observables.append({"kind": "joblog_v2", "name": "mensajes_ricos", "value": joblog_v2_normalized})
        observables.append({"kind": "return", "name": "rc", "value": int(last_rc)})
        if libl_val:
            observables.append({"kind": "libl", "name": "libl", "value": libl_val})
        if objects_val:
            observables.append({"kind": "objects", "name": "objects", "value": objects_val})
        if db_val:
            observables.append({"kind": "db", "name": "db", "value": db_val})

        # Si no hay observables (solo compilación vertical 1 compat), usa mensajes como antes
        if not observables and joblog_final:
            observables = [{"kind": "joblog", "name": "mensajes", "value": joblog_final}]

        # Normaliza por Kind
        observables = normalizar_observables(observables, ignore)

    finally:
        con.close()

    # 6) Escribe esperado/<ID>.json
    snapshot = {
        "contrato_version": CONTRATO_VERSION,
        "fixture": fid,
        "ibmi": {
            "host": cfg.host,
            "release": cfg.release,
            "ccsid": cfg.ccsid,
            "capturado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "observables": observables,
    }
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    destino = out_dir / f"{fid}.json"
    destino.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[captura] {fid}: {len(observables)} observables -> {destino}")
    for obs in observables:
        k = obs.get("kind")
        v = obs.get("value")
        if k == "display":
            flds = v.get("fields", []) if isinstance(v, dict) else []
            lits = v.get("literals", []) if isinstance(v, dict) else []
            print(f"  display: {len(flds)} fields, {len(lits)} literals, cursor={v.get('cursor')}")
        elif k == "display_literals":
            print(f"  display_literals: {len(v) if isinstance(v, list) else 0} literales")
        elif k == "display_grid":
            print(f"  display_grid: {len(v) if isinstance(v, list) else 0} filas")
        elif k == "display_raw":
            print(f"  display_raw: {len(str(v))} hex chars")
        elif k == "joblog":
            print(f"  joblog: {len(v) if isinstance(v, list) else 0} mensajes")
        elif k == "libl":
            print(f"  libl: {v}")
        elif k == "objects":
            print(f"  objects: {len(v) if isinstance(v, list) else 0}")
        elif k == "db":
            print(f"  db: {len(v) if isinstance(v, list) else 0} tablas")
        elif k == "return":
            print(f"  return: {v}")
    return destino


# Compatibilidad con firma antigua: capturar(fixture, nombre, out_dir)
def capturar(*, fixture: Path, nombre: str, out_dir: Path, env_file: Path | None = None) -> Path:
    """Compat: firma antigua usada por tests vertical 1."""
    # Si fixture es .rpgle directo, crea fixture sintético
    if fixture.suffix.lower() == ".rpgle":
        from .colectores.mensajes import parsear_listing
        from .config import load as _load
        from .normalizar import normalizar_observable as _norm_obs
        cfg = _load(env_file)
        if not cfg.host or not cfg.user:
            raise SystemExit("Falta configuración: copia oracle.env.example a oracle.env")
        con = ConectarIBMi(cfg)
        try:
            runner = RunnerIBMi(con)
            ifs = runner.subir_fuente(fixture, nombre)
            resultado = runner.crtbndrpg(ifs)
        finally:
            con.close()
        mensajes = parsear_listing(resultado.listing)
        snapshot = {
            "contrato_version": CONTRATO_VERSION,
            "fixture": nombre,
            "ibmi": {
                "host": cfg.host,
                "release": cfg.release,
                "ccsid": cfg.ccsid,
                "capturado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "exit_code": resultado.exit_code,
                "ok": resultado.ok,
            },
            "observables": [_norm_obs(m.observables()) for m in mensajes],
        }
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        destino = out_dir / f"{nombre}.json"
        destino.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        if snapshot.get("observables"):
            print(f"[captura] {nombre}: {len(mensajes)} mensajes -> {destino}")
        else:
            print(f"[captura] {nombre}: sin mensajes (exit={resultado.exit_code}) -> {destino}")
        return destino
    # Si es JSON, delega a capturar_fixture
    return capturar_fixture(fixture_path=Path(fixture), out_dir=Path(out_dir), env_file=env_file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Oráculo — captura fixture contra IBM i")
    parser.add_argument("fixture", nargs="?", help="Ruta a fixture JSON o fuente .rpgle (compat)")
    parser.add_argument("nombre", nargs="?", help="Nombre salida (compat, sin .json)")
    parser.add_argument("--fixture", dest="fixture_opt", help="Ruta a fixture JSON")
    parser.add_argument("--out", dest="out_dir", default="esperado", help="Directorio salida")
    parser.add_argument("--env", dest="env_file", help="Ruta a oracle.env")
    parser.add_argument("--no-tn5250", action="store_true", help="Desactiva TN5250, solo batch")
    args = parser.parse_args()

    # Compat: positional <rpgle> <nombre>
    if args.fixture and args.nombre and not args.fixture_opt:
        # Detecta si es modo compat (rpgle)
        if args.fixture.lower().endswith(".rpgle"):
            raiz = Path(__file__).resolve().parent.parent
            capturar(fixture=Path(args.fixture), nombre=args.nombre, out_dir=raiz / "esperado")
            return
        # Si son dos posicionales pero no rpgle, trata primero como fixture json
        fixture_path = Path(args.fixture)
        out = Path(args.out_dir) if args.out_dir else Path(__file__).resolve().parent.parent / "esperado"
        capturar_fixture(
            fixture_path=fixture_path,
            out_dir=out,
            env_file=Path(args.env_file) if args.env_file else None,
            use_tn5250=not args.no_tn5250,
        )
        return

    fixture_path = Path(args.fixture_opt or args.fixture or "")
    if not fixture_path or str(fixture_path) == "":
        parser.print_help()
        raise SystemExit(2)
    if not fixture_path.exists():
        raise SystemExit(f"Fixture no existe: {fixture_path}")

    raiz = Path(__file__).resolve().parent.parent
    out = Path(args.out_dir) if args.out_dir != "esperado" else raiz / "esperado"
    # Si out_dir es relativo y no existe, resuélvelo relativo a cwd
    capturar_fixture(
        fixture_path=fixture_path,
        out_dir=out,
        env_file=Path(args.env_file) if args.env_file else None,
        use_tn5250=not args.no_tn5250,
    )


if __name__ == "__main__":
    main()
