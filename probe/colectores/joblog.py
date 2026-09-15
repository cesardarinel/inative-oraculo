"""Colector joblog — captura mensajes del job vía DSPJOBLOG *PRINT + CPYSPLF."""
from __future__ import annotations

import re
from typing import Any


# CPF1234 / RNQ / CPC / CPD / CEE / MCH — con o sin ":" (PASE system -b usa ":")
_MSG_RE = re.compile(
    r"^\s*(?P<id>[A-Z]{2,3}\d{4})\s*:?\s*(?:(?P<sev>\d{1,2})\s+)?(?P<text>.+?)\s*$",
    re.MULTILINE,
)


def parse_joblog_text(text: str) -> list[dict[str, Any]]:
    """Parsea texto de joblog (spool) a lista [{id, sev, text}]."""
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        # Filtra cabeceras de spool
        upper = line.upper()
        if any(h in upper for h in ["JOB LOG", "DISPLAY JOB LOG", "PAGE", "5722SS1", "QSYS"]):
            # Pero si la línea contiene CPF dentro, igual la parseamos abajo
            if not re.search(r"[A-Z]{2,3}\d{4}", line):
                continue
        m = _MSG_RE.match(line.strip())
        if m:
            mid = m.group("id").upper()
            sev_raw = m.group("sev")
            sev = int(sev_raw) if sev_raw and sev_raw.isdigit() else 0
            # Severidad por familia si no viene explícita
            if not sev_raw:
                if mid.startswith("CPF") or mid.startswith("CPD"):
                    sev = 30
                elif mid.startswith("MCH") or mid.startswith("CEE") or mid.startswith("RNQ") or mid.startswith("RNS"):
                    sev = 40
                elif mid.startswith("CPC"):
                    sev = 0
            out.append({"id": mid, "sev": sev, "text": m.group("text").strip()})
        else:
            # Línea de continuación: apéndice al último mensaje
            if out and line.strip() and not line.strip().startswith("*"):
                out[-1]["text"] += " " + line.strip()
    return out


def capturar_joblog(con, *, max_lines: int = 500) -> list[dict[str, Any]]:
    """Captura joblog completo vía DSPJOBLOG OUTPUT(*PRINT) + CPYSPLF.

    Retorna lista ordenada cronológicamente.
    """
    # 1) Intenta QSYS2.JOBLOG_INFO por ODBC (más determinista)
    db = con.try_odbc() if hasattr(con, "try_odbc") else None
    if db is not None:
        try:
            cur = db.cursor()
            # IntentaVista QSYS2.JOBLOG_INFO si existe (7.3+)
            cur.execute(
                "SELECT MESSAGE_ID, MESSAGE_TYPE, SEVERITY, MESSAGE_TEXT "
                "FROM QSYS2.JOBLOG_INFO ORDER BY ORDINAL_POSITION FETCH FIRST 500 ROWS ONLY"
            )
            rows = cur.fetchall()
            db.close()
            if rows:
                out: list[dict[str, Any]] = []
                for r in rows:
                    mid = str(r[0]).strip().upper() if r[0] else "CPF0000"
                    sev = int(r[2]) if r[2] is not None else 0
                    text = str(r[3]).strip() if r[3] else ""
                    out.append({"id": mid, "sev": sev, "text": text})
                if out:
                    return out
        except Exception:
            try:
                db.close()
            except Exception:
                pass

    # 2) Fallback spool: DSPJOBLOG *PRINT
    try:
        con.sshes("system -s \"DSPJOBLOG OUTPUT(*PRINT)\"", timeout=30)
        con.sshes("system -s \"CRTPF FILE(QTEMP/JOBLOGPRT) RCDLEN(132) SIZE(*NOMAX)\"", timeout=30)
        rc, _, _ = con.sshes(
            "system -s \"CPYSPLF FILE(QPJOBLOG) TOFILE(QTEMP/JOBLOGPRT) SPLNBR(*LAST) CTLCHAR(*FC)\"",
            timeout=30,
        )
        if rc == 0:
            db2 = con.try_odbc() if hasattr(con, "try_odbc") else None
            if db2 is not None:
                try:
                    cur = db2.cursor()
                    cur.execute("SELECT * FROM QTEMP.JOBLOGPRT")
                    rows = cur.fetchall()
                    text = "\n".join(" ".join(str(c) for c in row if c) for row in rows)
                    db2.close()
                    parsed = parse_joblog_text(text)
                    if parsed:
                        return parsed
                except Exception:
                    try:
                        db2.close()
                    except Exception:
                        pass
            # Fallback IFS
            rc2, _, _ = con.sshes(
                "system -s \"CPYTOIMPF FROMFILE(QTEMP/JOBLOGPRT) TOSTMF('/tmp/joblog.txt') MBROPT(*REPLACE) RCDDLM(*CRLF)\"",
                timeout=30,
            )
            if rc2 == 0 and con.existe_ifs("/tmp/joblog.txt"):
                txt = con.leer_ifs("/tmp/joblog.txt")
                parsed = parse_joblog_text(txt)
                if parsed:
                    return parsed
    except Exception:
        pass

    # 3) Último fallback: intenta DSPJOBLOG sin PRINT (solo por si system lo devuelve)
    try:
        _, out, _ = con.sshes("system -s \"DSPJOBLOG\"", timeout=30)
        parsed = parse_joblog_text(out)
        if parsed:
            return parsed
    except Exception:
        pass

    return []


def to_observable(joblog: list[dict[str, Any]], *, name: str = "mensajes") -> dict:
    return {"kind": "joblog", "name": name, "value": joblog}
