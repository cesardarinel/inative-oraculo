"""Colector db — captura contenido de tablas vía ODBC o RUNSQLSTM."""
from __future__ import annotations

from typing import Any


def capturar_db(con, lib: str, tabla: str, *, order_by: str | None = None, limit: int = 1000) -> list[dict[str, Any]]:
    """Captura SELECT * FROM lib.tabla ORDER BY order_by.

    Retorna lista de dicts (una por fila). Si no hay ODBC, intenta RUNSQLSTM + IFS.
    """
    lib = (lib or con.cfg.lib or "QTEMP").upper()
    tabla = tabla.upper()
    qname = f"{lib}.{tabla}"

    # 1) ODBC
    db = con.try_odbc() if hasattr(con, "try_odbc") else None
    if db is not None:
        try:
            cur = db.cursor()
            sql = f"SELECT * FROM {qname}"
            if order_by:
                sql += f" ORDER BY {order_by}"
            sql += f" FETCH FIRST {limit} ROWS ONLY"
            cur.execute(sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall()
            db.close()
            out: list[dict[str, Any]] = []
            for r in rows:
                d: dict[str, Any] = {}
                for i, c in enumerate(cols):
                    v = r[i]
                    # Normaliza bytes/decimales
                    if isinstance(v, bytes):
                        try:
                            v = v.decode("utf-8")
                        except Exception:
                            v = v.hex()
                    d[str(c).lower()] = v
                out.append(d)
            return out
        except Exception:
            try:
                db.close()
            except Exception:
                pass

    # 2) Fallback RUNSQLSTM vía IFS
    try:
        sql_text = f"SELECT * FROM {qname}"
        if order_by:
            sql_text += f" ORDER BY {order_by}"
        sql_text += ";"
        con.escribir_ifs("/tmp/qry.sql", sql_text)
        # Crea archivo de salida
        rc, out, err = con.sshes(
            f"system -s \"RUNSQLSTM SRCSTMF('/tmp/qry.sql') DFTRDBCOL({lib}) OUTPUT(*PRINT)\"",
            timeout=30,
        )
        # Intenta CPYSPLF si generó spool
        con.sshes("system -s \"CRTPF FILE(QTEMP/DBPRT) RCDLEN(132) SIZE(*NOMAX)\"", timeout=30)
        con.sshes("system -s \"CPYSPLF FILE(QSYSPRT) TOFILE(QTEMP/DBPRT) SPLNBR(*LAST)\"", timeout=30)
        db2 = con.try_odbc() if hasattr(con, "try_odbc") else None
        if db2 is not None:
            try:
                cur = db2.cursor()
                cur.execute("SELECT * FROM QTEMP.DBPRT")
                rows = cur.fetchall()
                db2.close()
                # Parse simple: si no hay parsing estructurado, devuelve texto crudo
                if rows:
                    text = "\n".join(" ".join(str(c) for c in row if c) for row in rows)
                    # Si no podemos parsear columnas, devuelve una fila con texto
                    return [{"raw": text[:4000]}] if text.strip() else []
            except Exception:
                try:
                    db2.close()
                except Exception:
                    pass
    except Exception:
        pass

    return []


def capturar_db_multi(con, tablas: list[tuple[str, str, str | None]]) -> list[dict[str, Any]]:
    """Captura múltiples tablas; tablas = [(lib, tabla, order_by), ...]."""
    out: list[dict[str, Any]] = []
    for lib, tabla, order_by in tablas:
        rows = capturar_db(con, lib, tabla, order_by=order_by)
        if rows:
            out.append({"table": f"{lib.upper()}.{tabla.upper()}", "rows": rows})
    return out


def ejecutar_sql(con, sql: str) -> list[dict[str, Any]]:
    db = getattr(con, "try_odbc", lambda: None)()
    if db is None:
        return []
    try:
        cur = db.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        db.close()
        out = []
        for r in rows:
            d = {}
            for i, c in enumerate(cols):
                v = r[i]
                if isinstance(v, bytes):
                    try: v = v.decode("utf-8")
                    except: v = v.hex()
                d[str(c).lower()] = v
            out.append(d)
        return out
    except Exception:
        try: db.close()
        except: pass
        return []

def to_observable(db_rows: list[dict[str, Any]], *, name: str = "db") -> dict:
    return {"kind": "db", "name": name, "value": db_rows}
