"""Colector JobLog v2 — captura rica para el JobLog Recorder.

Implementa el plan "IBM i JobLog Recorder → iNative Mock Runtime" (§1-§19):

- Captura todos los campos semánticos de QSYS2.JOBLOG_INFO:
  MESSAGE_ID, MESSAGE_TYPE, SEVERITY, MESSAGE_TEXT,
  MESSAGE_SECOND_LEVEL_TEXT, MESSAGE_TIMESTAMP,
  ORDINAL_POSITION, FROM_*, TO_*, JOB_NAME/USER/NUMBER, MESSAGE_KEY
- Soporta workflow INITIAL → EXECUTE → FINAL → DIFF (§4)
- Separa raw vs normalized y marca campos dinámicos (§14-15)
- Preserva orden completo (diagnostic → escape) (§13, §8)
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

_MSG_RE = re.compile(
    r"^\s*(?P<id>[A-Z]{2,3}\d{4})\s+(?:(?P<sev>\d{1,2})\s+)?(?P<text>.+?)\s*$",
    re.MULTILINE,
)

# Campos dinámicos §15
DYNAMIC_FIELDS = {"job_name", "job_user", "job_number", "job_type", "job_subtype", "system_name", "timestamp", "message_key", "message_timestamp"}

# Columnas ricas intentadas en orden (primero las más completas)
_RICH_QUERIES = [
    # Intento 1: esquema completo documentado 7.3+ con SECOND_LEVEL
    (
        "SELECT ORDINAL_POSITION, MESSAGE_ID, MESSAGE_TYPE, SEVERITY, "
        "MESSAGE_TEXT, MESSAGE_SECOND_LEVEL_TEXT, MESSAGE_TIMESTAMP, "
        "FROM_LIBRARY, FROM_PROGRAM, FROM_MODULE, FROM_PROCEDURE, "
        "TO_LIBRARY, TO_PROGRAM, MESSAGE_KEY, JOB_NAME "
        "FROM TABLE(QSYS2.JOBLOG_INFO('*')) ORDER BY ORDINAL_POSITION"
    ),
    # Intento 2: sin second level pero con timestamp
    (
        "SELECT ORDINAL_POSITION, MESSAGE_ID, MESSAGE_TYPE, SEVERITY, "
        "MESSAGE_TEXT, MESSAGE_TIMESTAMP, FROM_PROGRAM, TO_PROGRAM, "
        "MESSAGE_KEY, JOB_NAME "
        "FROM TABLE(QSYS2.JOBLOG_INFO('*')) ORDER BY ORDINAL_POSITION"
    ),
    # Intento 3: mínimo viable QSYS2.JOBLOG_INFO (existe en 7.4+)
    (
        "SELECT MESSAGE_ID, MESSAGE_TYPE, SEVERITY, MESSAGE_TEXT "
        "FROM QSYS2.JOBLOG_INFO ORDER BY ORDINAL_POSITION FETCH FIRST 1000 ROWS ONLY"
    ),
    # Intento 4: vista legacy via QSYS2
    (
        "SELECT ORDINAL_POSITION, MESSAGE_ID, MESSAGE_TYPE, SEVERITY, MESSAGE_TEXT "
        "FROM QSYS2.JOBLOG_INFO ORDER BY ORDINAL_POSITION"
    ),
]

def _normalize_type(raw: str | None) -> str:
    if not raw:
        return "UNKNOWN"
    u = raw.strip().upper().lstrip("*")
    mapping = {
        "COMP": "COMPLETION", "COMPLETION": "COMPLETION",
        "DIAG": "DIAGNOSTIC", "DIAGNOSTIC": "DIAGNOSTIC",
        "ESCAPE": "ESCAPE",
        "INFO": "INFORMATIONAL", "INFORMATIONAL": "INFORMATIONAL",
        "INQ": "INQUIRY", "INQUIRY": "INQUIRY",
        "NOTIFY": "NOTIFY", "RQS": "REQUEST", "REQUEST": "REQUEST",
        "STATUS": "STATUS", "SENDER_COPY": "SENDER_COPY",
    }
    return mapping.get(u, u)


def _row_to_msg(row: tuple, col_names: list[str]) -> dict[str, Any]:
    """Convierte una fila ODBC con nombres de columna a dict canónico JobMessage."""
    d = {col_names[i].upper(): val for i, val in enumerate(row)}
    # helpers case-insensitive
    def get(*keys):
        for k in keys:
            if k.upper() in d:
                return d[k.upper()]
        return None

    ordinal = get("ORDINAL_POSITION")
    try:
        ordinal = int(ordinal) if ordinal is not None else 0
    except Exception:
        ordinal = 0
    mid = str(get("MESSAGE_ID") or "").strip().upper() or "CPF0000"
    mtype = _normalize_type(str(get("MESSAGE_TYPE") or ""))
    # Heurística: si type es vacío y mid es CPF/CPC/CPD, inferir
    if mtype == "UNKNOWN" and mid:
        if mid.startswith("CPC"):
            mtype = "COMPLETION"
        elif mid.startswith("CPD"):
            mtype = "DIAGNOSTIC"
        elif mid.startswith("CPF") or mid.startswith("CEE") or mid.startswith("RNQ"):
            # severity decide; lo dejamos como ESCAPE si sev>=30, pero lo marcamos DIAGNOSTIC por defecto
            sev_tmp = get("SEVERITY")
            try:
                sev_tmp = int(sev_tmp) if sev_tmp is not None else 0
            except Exception:
                sev_tmp = 0
            mtype = "ESCAPE" if sev_tmp >= 30 else "DIAGNOSTIC"

    sev = get("SEVERITY")
    try:
        sev = int(sev) if sev is not None else 0
    except Exception:
        sev = 0

    text = str(get("MESSAGE_TEXT") or "").strip()
    second = str(get("MESSAGE_SECOND_LEVEL_TEXT") or get("SECOND_LEVEL_TEXT") or "").strip()
    ts_raw = get("MESSAGE_TIMESTAMP", "TIMESTAMP")
    ts = ""
    if ts_raw is not None:
        try:
            ts = str(ts_raw)
            # Intenta parse a ISO
            if "T" not in ts and " " in ts:
                # DB2 timestamp "2026-09-05-10.00.00.000000"
                ts = ts.replace("-", " ").replace(".", ":")  # best-effort
        except Exception:
            ts = str(ts_raw)

    return {
        "message_id": mid,
        "message_type": mtype,
        "severity": sev,
        "message_text": text,
        "message_second_level_text": second,
        "message_timestamp": ts,
        "ordinal_position": ordinal,
        "from_library": str(get("FROM_LIBRARY") or "").strip(),
        "from_program": str(get("FROM_PROGRAM") or "").strip(),
        "from_module": str(get("FROM_MODULE") or "").strip(),
        "from_procedure": str(get("FROM_PROCEDURE") or "").strip(),
        "to_library": str(get("TO_LIBRARY") or "").strip(),
        "to_program": str(get("TO_PROGRAM") or "").strip(),
        "message_key": str(get("MESSAGE_KEY") or "").strip(),
        "job_name": str(get("JOB_NAME") or "").strip(),
        # Compat con colector antiguo
        "id": mid,
        "sev": sev,
        "text": text,
        "type": mtype,
        "ordinal": ordinal,
    }


# ---------------------------------------------------------------------------
# Captura
# ---------------------------------------------------------------------------

def capturar_joblog_snapshot(con, *, max_rows: int = 2000) -> dict:
    """Captura un snapshot completo con metadata.

    Retorna dict {job, messages, captured_at, raw_rows} con job context embebido.
    Intenta QSYS2.JOBLOG_INFO por ODBC en orden rico→básico; fallback a spool.
    """
    ts = datetime.now().isoformat()
    # Intenta ODBC rico
    db = con.try_odbc() if hasattr(con, "try_odbc") else None
    if db is not None:
        for sql in _RICH_QUERIES:
            try:
                cur = db.cursor()
                cur.execute(sql)
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description] if cur.description else []
                db.close()
                if rows is not None:
                    msgs = [_row_to_msg(r, cols) for r in rows]
                    # Filtra vacíos
                    msgs = [m for m in msgs if m["message_id"]]
                    # Asegura ordinal si es 0
                    for i, m in enumerate(msgs):
                        if not m["ordinal_position"]:
                            m["ordinal_position"] = i + 1
                            m["ordinal"] = i + 1
                    return {
                        "captured_at": ts,
                        "messages": msgs,
                        "count": len(msgs),
                        "source": "QSYS2.JOBLOG_INFO",
                        "sql": sql,
                    }
            except Exception as e:
                try:
                    db.close()
                except Exception:
                    pass
                # Reintenta con nueva conexión para siguiente query
                db = con.try_odbc() if hasattr(con, "try_odbc") else None
                if db is None:
                    break
                continue
        try:
            db.close()
        except Exception:
            pass

    # Fallback spool: DSPJOBLOG *PRINT
    try:
        from .joblog import parse_joblog_text
        # Intenta DSPJOBLOG OUTPUT(*PRINT) + CPYSPLF (legacy)
        con.sshes("system -s \"DSPJOBLOG OUTPUT(*PRINT)\"", timeout=30)
        con.sshes("system -s \"CRTPF FILE(QTEMP/JOBLOGPRT) RCDLEN(132) SIZE(*NOMAX)\"", timeout=30)
        rc, _, _ = con.sshes(
            "system -s \"CPYSPLF FILE(QPJOBLOG) TOFILE(QTEMP/JOBLOGPRT) SPLNBR(*LAST) CTLCHAR(*FC)\"",
            timeout=30,
        )
        text = ""
        if rc == 0:
            db2 = con.try_odbc() if hasattr(con, "try_odbc") else None
            if db2 is not None:
                try:
                    cur = db2.cursor()
                    cur.execute("SELECT * FROM QTEMP.JOBLOGPRT")
                    rows = cur.fetchall()
                    text = "\n".join(" ".join(str(c) for c in row if c) for row in rows)
                    db2.close()
                except Exception:
                    try: db2.close()
                    except Exception: pass
            if not text:
                rc2, _, _ = con.sshes(
                    "system -s \"CPYTOIMPF FROMFILE(QTEMP/JOBLOGPRT) TOSTMF('/tmp/joblog.txt') MBROPT(*REPLACE) RCDDLM(*CRLF)\"",
                    timeout=30,
                )
                if rc2 == 0 and con.existe_ifs("/tmp/joblog.txt"):
                    text = con.leer_ifs("/tmp/joblog.txt")
        if text:
            parsed = parse_joblog_text(text)
            msgs = []
            for i, p in enumerate(parsed):
                msgs.append({
                    "message_id": p["id"],
                    "message_type": "UNKNOWN",
                    "severity": p["sev"],
                    "message_text": p["text"],
                    "message_second_level_text": "",
                    "message_timestamp": "",
                    "ordinal_position": i + 1,
                    "from_program": "", "from_library": "",
                    "to_program": "", "to_library": "",
                    "message_key": "", "job_name": "",
                    "id": p["id"], "sev": p["sev"], "text": p["text"], "ordinal": i+1,
                })
            return {"captured_at": ts, "messages": msgs, "count": len(msgs), "source": "DSPJOBLOG_SPOOL", "sql": "DSPJOBLOG OUTPUT(*PRINT)"}
    except Exception:
        pass

    # Último fallback: DSPJOBLOG stdout
    try:
        from .joblog import parse_joblog_text
        _, out, _ = con.sshes("system -s \"DSPJOBLOG\"", timeout=30)
        parsed = parse_joblog_text(out)
        msgs = []
        for i, p in enumerate(parsed):
            msgs.append({
                "message_id": p["id"], "message_type": "UNKNOWN", "severity": p["sev"],
                "message_text": p["text"], "message_second_level_text": "",
                "message_timestamp": "", "ordinal_position": i+1,
                "from_program": "", "from_library": "", "to_program": "", "to_library": "",
                "message_key": "", "job_name": "",
                "id": p["id"], "sev": p["sev"], "text": p["text"], "ordinal": i+1,
            })
        return {"captured_at": ts, "messages": msgs, "count": len(msgs), "source": "DSPJOBLOG_STDOUT", "sql": "DSPJOBLOG"}
    except Exception:
        pass

    return {"captured_at": ts, "messages": [], "count": 0, "source": "NONE", "sql": ""}


def diff_snapshots(before: dict, after: dict) -> list[dict]:
    """Calcula delta: mensajes en 'after' no presentes en 'before' (por ordinal+id+text).

    Preserva orden completo (diagnostic chain).
    """
    before_msgs = before.get("messages", [])
    after_msgs = after.get("messages", [])

    def key(m):
        return (m.get("message_id","").strip().upper(), m.get("message_text","").strip())
    seen = {key(m) for m in before_msgs}
    # También index por ordinal para capturar reimpresiones
    seen_ord = {(m.get("ordinal_position",0), m.get("message_id","").upper()) for m in before_msgs}

    delta = []
    for m in after_msgs:
        k = key(m)
        ok = (m.get("ordinal_position",0), m.get("message_id","").upper())
        if k not in seen and ok not in seen_ord:
            delta.append(m)
    # Fallback si diff vacío pero after tiene más mensajes: toma cola
    if not delta and len(after_msgs) > len(before_msgs):
        delta = after_msgs[len(before_msgs):]
    return delta


def normalize_messages(messages: list[dict]) -> list[dict]:
    """Normaliza: colapsa espacios, upper id, placeholders para campos dinámicos."""
    out = []
    for m in messages:
        nm = dict(m)
        nm["message_id"] = str(nm.get("message_id","")).strip().upper()
        nm["message_type"] = str(nm.get("message_type","")).strip().upper() or "UNKNOWN"
        try:
            nm["severity"] = int(nm.get("severity",0))
        except Exception:
            nm["severity"] = 0
        # Colapsa whitespace en textos pero preserva case
        for k in ("message_text","message_second_level_text"):
            if k in nm and isinstance(nm[k], str):
                nm[k] = re.sub(r"\s+", " ", nm[k]).strip()
                if k == "message_text":
                    nm["text"] = nm[k]
        # Stripa dinámicos para replay
        nm["message_timestamp"] = "${TIMESTAMP}"
        nm["job_name"] = "${JOB_NAME}"
        nm["message_key"] = ""
        out.append(nm)
    return out


def to_observable_delta(delta: list[dict], *, name: str = "mensajes") -> dict:
    return {"kind": "joblog", "name": name, "value": delta}
