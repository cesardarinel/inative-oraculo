"""Colector libl — captura library list del job vía SSH/ODBC.

Intenta QSYS2.LIBRARY_LIST_INFO por ODBC (determinista), fallback a
DSPLIBL OUTPUT(*PRINT) + CPYSPLF + IFS.
"""
from __future__ import annotations

import re
from pathlib import Path


def _parse_dsplibl_output(text: str) -> list[str]:
    """Parsea salida de DSPLIBL (texto de spool o stdout de system)."""
    # Si el texto contiene un error CPF/SQL, no es LIBL
    up = text.upper()
    if any(p in up for p in ["IS NOT", "IDENTIFIER", "CPF", "SQL", "ERROR", "NOT AUTHORIZED", "NOT FOUND"]):
        # Si el output parece un mensaje de error y no una lista, retorna vacío para forzar fallback
        # Pero intenta extraer libs solo si hay líneas que no son el mensaje de error
        lines = [l for l in text.splitlines() if l.strip() and not any(x in l.upper() for x in [" IS NOT ", " IDENTIFIER ", "CPF", "SQL"])]
        if not lines:
            return []
        text = "\n".join(lines)
    libs: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("*") or line.startswith("-"):
            continue
        if any(h in line.upper() for h in ["LIBRARY LIST", "BIBLIOTECA", "CURRENT LIBRARY", "SYSTEM"]):
            continue
        # Ignora líneas que son mensajes de error completas
        if line.upper().startswith("IS ") or " NOT " in line.upper() and len(line.split()) <= 4:
            continue
        tokens = re.split(r"\s+", line)
        for tok in tokens:
            tok = tok.strip().upper()
            if re.match(r"^[A-Z][A-Z0-9_]{0,9}$", tok) and tok not in ("LIBRARY", "LIST", "IS", "NOT", "AN", "IDENTIFIER"):
                if tok not in libs:
                    libs.append(tok)
    return libs


def capturar_libl(con, *, via: str = "auto") -> list[str]:
    """Captura LIBL. via=auto|odbc|print. Devuelve lista ordenada.

    Intenta ODBC primero, luego PRINT.
    """
    # 1) ODBC QSYS2.LIBRARY_LIST_INFO
    if via in ("auto", "odbc"):
        db = con.try_odbc() if hasattr(con, "try_odbc") else None
        if db is not None:
            try:
                cur = db.cursor()
                # QSYS2.LIBRARY_LIST_INFO es tabla; si no existe, fallback
                cur.execute("SELECT SCHEMA_NAME FROM QSYS2.LIBRARY_LIST_INFO ORDER BY ORDINAL_POSITION")
                rows = cur.fetchall()
                if rows:
                    libs = [str(r[0]).strip().upper() for r in rows if r[0]]
                    db.close()
                    if libs:
                        return libs
                db.close()
            except Exception:
                try:
                    db.close()
                except Exception:
                    pass

        # Intenta RTVJOBA vía SQL si lo anterior falló
        db2 = con.try_odbc() if hasattr(con, "try_odbc") else None
        if db2 is not None:
            try:
                cur = db2.cursor()
                # QSYS2.JOB_INFO alternativa
                cur.execute("SELECT CURRENT_SCHEMA FROM SYSIBM.SYSDUMMY1")
                r = cur.fetchone()
                db2.close()
            except Exception:
                try:
                    db2.close()
                except Exception:
                    pass

    # 2) Fallback: DSPLIBL OUTPUT(*PRINT) -> spool -> IFS
    # Usa QSH system para generar spool y luego CPYSPLF
    try:
        # Genera spool
        con.sshes("system -s \"DSPLIBL OUTPUT(*PRINT)\"", timeout=30)
        # Copia último spool QSYSPRT a QTEMP/LIBLFILE
        # Primero crea archivo físico temporal
        con.sshes("system -s \"CRTPF FILE(QTEMP/LIBLPRT) RCDLEN(132) SIZE(*NOMAX)\"", timeout=30)
        # CPYSPLF del último spool de DSPLIBL
        rc, out, err = con.sshes(
            "system -s \"CPYSPLF FILE(QSYSPRT) TOFILE(QTEMP/LIBLPRT) SPLNBR(*LAST) CTLCHAR(*FC)\"", timeout=30
        )
        if rc == 0:
            # Descarga vía ODBC o leyendo IFS convertido
            # Intenta leer via RUNSQL: SELECT * FROM QTEMP.LIBLPRT
            db3 = con.try_odbc() if hasattr(con, "try_odbc") else None
            if db3 is not None:
                try:
                    cur = db3.cursor()
                    cur.execute("SELECT * FROM QTEMP.LIBLPRT")
                    rows = cur.fetchall()
                    text = "\n".join(" ".join(str(c) for c in row) for row in rows)
                    db3.close()
                    libs = _parse_dsplibl_output(text)
                    if libs:
                        return libs
                except Exception:
                    try:
                        db3.close()
                    except Exception:
                        pass
            # Fallback: intenta leer IFS si se usó CPYTOSTMF
            rc2, out2, _ = con.sshes(
                "system -s \"CPYTOIMPF FROMFILE(QTEMP/LIBLPRT) TOSTMF('/tmp/libl.txt') MBROPT(*REPLACE) RCDDLM(*CRLF)\"", timeout=30
            )
            if rc2 == 0 and con.existe_ifs("/tmp/libl.txt"):
                txt = con.leer_ifs("/tmp/libl.txt")
                libs = _parse_dsplibl_output(txt)
                if libs:
                    return libs
    except Exception:
        pass

    # 3) Último fallback: parsea stdout de DSPLIBL directo (aunque system -s no siempre lo devuelve)
    try:
        _, out, _ = con.sshes("system -s \"DSPLIBL\"", timeout=30)
        libs = _parse_dsplibl_output(out)
        if libs:
            return libs
    except Exception:
        pass

    return []


def to_observable(libl: list[str], *, name: str = "libl") -> dict:
    return {"kind": "libl", "name": name, "value": libl}
