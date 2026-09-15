"""Colector job context — captura estado del job actual para §5.

Captura vía QSYS2.JOB_INFO / JOBLOG_INFO o vía DSPJOB / RTVJOBA por SSH.
"""
from __future__ import annotations

import re
from typing import Any


def capturar_job_info(con) -> dict[str, Any]:
    """Retorna dict {job_name, job_user, job_number, job_type, job_subtype, system_name, library_list, current_library, ccsid}."""
    # Intento 1: QSYS2.JOB_INFO por ODBC
    db = con.try_odbc() if hasattr(con, "try_odbc") else None
    if db is not None:
        queries = [
            "SELECT JOB_NAME, JOB_USER, JOB_NUMBER, JOB_TYPE, JOB_SUBTYPE, SYSTEM_NAME, CCSID FROM TABLE(QSYS2.JOB_INFO('*')) FETCH FIRST 1 ROW ONLY",
            "SELECT JOB_NAME, AUTHORIZATION_NAME AS JOB_USER, JOB_NUMBER FROM QSYS2.JOB_INFO FETCH FIRST 1 ROW ONLY",
            "SELECT JOB_NAME FROM TABLE(QSYS2.JOB_INFO('*')) LIMIT 1",
        ]
        for sql in queries:
            try:
                cur = db.cursor()
                cur.execute(sql)
                row = cur.fetchone()
                cols = [d[0] for d in cur.description] if cur.description else []
                db.close()
                if row:
                    d = {cols[i].upper(): row[i] for i in range(len(cols))}
                    # Normaliza
                    job_name = str(d.get("JOB_NAME") or "").strip()
                    # JOB_NAME puede ser "123456/USER/JOB" o solo "JOB"
                    job_user = str(d.get("JOB_USER") or d.get("AUTHORIZATION_NAME") or "").strip()
                    job_number = str(d.get("JOB_NUMBER") or "").strip()
                    if job_name and "/" in job_name:
                        parts = job_name.split("/")
                        if len(parts) == 3:
                            job_number, job_user, job_name_short = parts
                            job_name = job_name_short
                        # Si viene completo lo preservamos como job_name completo
                    return {
                        "job_name": job_name,
                        "job_user": job_user,
                        "job_number": job_number,
                        "job_type": str(d.get("JOB_TYPE") or "").strip(),
                        "job_subtype": str(d.get("JOB_SUBTYPE") or "").strip(),
                        "system_name": str(d.get("SYSTEM_NAME") or "").strip(),
                        "ccsid": int(d.get("CCSID") or 0) if d.get("CCSID") else 0,
                        "source": "QSYS2.JOB_INFO",
                    }
            except Exception:
                try: db.close()
                except Exception: pass
                db = con.try_odbc() if hasattr(con, "try_odbc") else None
                if db is None:
                    break
                continue
        try: db.close()
        except Exception: pass

    # Intento 2: system DSPJOB por SSH (parsea salida)
    try:
        rc, out, err = con.sshes_raw("system -s \"DSPJOB OUTPUT(*PRINT)\"", timeout=30)
        text = out + err
        # Intenta también RTVJOBA
        rc2, out2, err2 = con.sshes_raw("system \"RTVJOBA JOBTYPE(&T) USER(&U) NBR(&N)\" 2>&1 || system \"DSPJOB JOB(*)\" 2>&1", timeout=30)
        combined = text + out2 + err2
        # Heurística: busca JOB: 123456/USER/JOBNAME
        m = re.search(r"(\d{6})/([A-Z0-9_]+)/([A-Z0-9_]+)", combined)
        if m:
            return {
                "job_name": m.group(3), "job_user": m.group(2), "job_number": m.group(1),
                "job_type": "", "job_subtype": "", "system_name": "",
                "source": "DSPJOB_SPOOL",
            }
    except Exception:
        pass

    # Intento 3: env vars / config fallback
    try:
        user = getattr(con.cfg, "user", "")
        return {
            "job_name": "", "job_user": str(user), "job_number": "",
            "job_type": "", "job_subtype": "", "system_name": str(getattr(con.cfg, "host","")),
            "source": "CONFIG_FALLBACK",
        }
    except Exception:
        return {
            "job_name": "", "job_user": "", "job_number": "",
            "job_type": "", "job_subtype": "", "system_name": "",
            "source": "UNKNOWN",
        }


def placeholder_job() -> dict:
    return {
        "job_name": "${JOB_NAME}",
        "job_user": "${JOB_USER}",
        "job_number": "${JOB_NUMBER}",
        "job_type": "${JOB_TYPE}",
        "system_name": "${SYSTEM_NAME}",
        "source": "PLACEHOLDER",
    }
