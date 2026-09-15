"""Colector objects — lista objetos de una biblioteca vía DSPOBJD."""
from __future__ import annotations

import re


def capturar_objects(con, lib: str = "", *, obj_filter: str = "*ALL", obj_type: str = "*ALL") -> list[str]:
    """Captura objetos como ["LIB/NAME *TYPE"].

    Si lib=="", usa con.cfg.lib. Intenta ODBC QSYS2.OBJECT_STATISTICS,
    fallback a DSPOBJD *OUTFILE.
    """
    lib = (lib or con.cfg.lib or "QTEMP").upper()
    # 1) ODBC QSYS2.OBJECT_STATISTICS
    db = con.try_odbc() if hasattr(con, "try_odbc") else None
    if db is not None:
        try:
            cur = db.cursor()
            # OBJECT_STATISTICS es más portable que SYSTABLES
            cur.execute(
                "SELECT OBJNAME, OBJTYPE FROM QSYS2.OBJECT_STATISTICS "
                "WHERE OBJSCHEMA = ? ORDER BY OBJNAME",
                (lib,),
            )
            rows = cur.fetchall()
            db.close()
            if rows:
                out = [f"{lib}/{str(r[0]).strip().upper()} *{str(r[1]).strip().upper()}" for r in rows if r[0]]
                if out:
                    return out
        except Exception:
            try:
                db.close()
            except Exception:
                pass
        # Fallback SYSTABLES/SYSVIEWS
        db2 = con.try_odbc() if hasattr(con, "try_odbc") else None
        if db2 is not None:
            try:
                cur = db2.cursor()
                cur.execute("SELECT TABLE_NAME, TABLE_TYPE FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = ? ORDER BY TABLE_NAME", (lib,))
                rows = cur.fetchall()
                db2.close()
                if rows:
                    return [f"{lib}/{str(r[0]).strip().upper()} *FILE" for r in rows if r[0]]
            except Exception:
                try:
                    db2.close()
                except Exception:
                    pass

    # 2) Fallback DSPOBJD OUTPUT(*OUTFILE)
    try:
        con.sshes("system -s \"CRTPF FILE(QTEMP/OBJLST) RCDLEN(132) SIZE(*NOMAX)\"", timeout=30)
        cmd = f"DSPOBJD OBJ({lib}/{obj_filter}) OBJTYPE({obj_type}) OUTPUT(*OUTFILE) OUTFILE(QTEMP/OBJLST)"
        con.sshes(f"system -s \"{cmd}\"", timeout=30)
        rc, _, _ = con.sshes(
            "system -s \"CPYTOIMPF FROMFILE(QTEMP/OBJLST) TOSTMF('/tmp/objlst.txt') MBROPT(*REPLACE) RCDDLM(*CRLF)\"",
            timeout=30,
        )
        if rc == 0 and con.existe_ifs("/tmp/objlst.txt"):
            txt = con.leer_ifs("/tmp/objlst.txt")
            out: list[str] = []
            for line in txt.splitlines():
                line = line.strip()
                if not line or line.startswith("*"):
                    continue
                # Intenta parsear LIB/NAME *TYPE
                m = re.search(r"([A-Z0-9_]{1,10})/([A-Z0-9_]{1,10})\s+\*([A-Z]{2,10})", line.upper())
                if m:
                    lib_, name, typ = m.groups()
                    entry = f"{lib_}/{name} *{typ}"
                    if entry not in out:
                        out.append(entry)
            if out:
                return sorted(out)
    except Exception:
        pass

    # 3) Último fallback: DSPLIB + parse? vacío
    try:
        _, out, _ = con.sshes(f"system -s \"DSPOBJD OBJ({lib}/*ALL) OBJTYPE(*ALL)\"", timeout=30)
        entries: list[str] = []
        for line in out.splitlines():
            m = re.search(r"([A-Z0-9_]{1,10})/([A-Z0-9_]{1,10})\s+\*([A-Z]{2,10})", line.upper())
            if m:
                lib_, name, typ = m.groups()
                entries.append(f"{lib_}/{name} *{typ}")
        if entries:
            return sorted(set(entries))
    except Exception:
        pass

    return []


def to_observable(objects: list[str], *, name: str = "objects") -> dict:
    return {"kind": "objects", "name": name, "value": sorted(objects)}
