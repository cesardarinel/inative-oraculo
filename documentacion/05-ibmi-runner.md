# 05 — Runner IBM i

> `probe/runner_ibmi.py` + `internal/runner/runner.go` — compila y ejecuta fixtures en un IBM i real vía SSH/PASE.

## 5.1 Conexión

- **SSH (PASE/QSH)** base para compilar, CL y spool — `probe/conect.py:58-68`.
- **SFTP** para subir fuentes al IFS — `probe/conect.py:102-128`.
- **ODBC** bajo demanda para catálogo/DB — `try_odbc()` (retorna `None` si falta driver).
- **TN5250** bajo demanda para display — `conect.tn5250()` → `TN5250Client` (`display_5250.py`).

Config vía `probe/config.py` desde `oracle.env` (host/release/user/lib/ccsid/ports/ssl). `ConectarIBMi.close()` libera SSH+SFTP+TN en orden.

## 5.2 Subida de fuentes

```
IFS_SRC = /home/{user}/oracle/src
IFS_OBJ = /home/{user}/oracle/obj   # reservado
```

| Método | Cuándo | Qué hace |
|--------|--------|----------|
| `subir_fuente(local, nombre, ext)` | `CRTBNDRPG/CRTSQLRPGI` (soportan `SRCSTMF`) | `write_ifs(ifs, utf-8)` en `…/{name}.{ext}` |
| `subir_texto(contenido, nombre, ext)` | fixture en memoria | igual, desde string |
| `subir_miembro(contenido, mbr, srcpf=QDSPFSRC)` | `CRTDSPF/CRTPF` (no soportan `SRCSTMF`) | cria `CRTSRCPF` si falta + `CPYFRMSTMF TOMBR('/qsys.lib/…') MBROPT(*REPLACE)` (ASCII→EBCDIC) |

## 5.3 Compilación — el detalle crítico

```python
def compilar_listing(self, cmd: str) -> ListingResultado:
    _, out, err = self.con.sshes_raw(f'system -b "{cmd}"', timeout=180)
    listing = out + "\n" + err
    falla = ("Compilation failed" in listing or "RNS9310" in listing
             or "CPF0006" in listing or "SQL9001" in listing
             or "CPF7311" in listing or "CPF7302" in listing)
    return ListingResultado(ok=not falla, listing=listing, exit_code=1 if falla else 0)
```

Descubrimiento PUB400 2026-08-26: **solo `system -b` imprime el listing completo por stdout** (cabecera `5770WDS` incluida); con `system` a secas el detalle queda en un sub-job batch cuyo spool es inaccesible. Ver `runner_ibmi.py:62-76`.

Comandos:

| Método | Comando real |
|--------|--------------|
| `crtbndrpg(ifs, obj)` | `CRTBNDRPG PGM(lib/obj) SRCSTMF('ifs') OPTION(*EVENTF) TGTCCSID(37)` |
| `crtbndcl(ifs, obj)` | `CRTBNDCL PGM(lib/obj) SRCSTMF('ifs')` |
| `crtdspf(ifs)` / `crtpf(ifs)` | `CRTDSPF/CRTPF FILE(lib/obj) SRCSTMF('ifs')` |
| `crtdspf_miembro(lib,srcpf,mbr)` | `CRTDSPF FILE(lib/obj) SRCFILE(lib/srcpf) SRCMBR(mbr)` |
| `crtsqlrpgle(ifs, rpgppopt="*NONE")` | `CRTSQLRPGI OBJ(lib/obj) SRCSTMF('ifs') COMMIT(*NONE) RPGPPOPT(*NONE|*LVL2)` — `*LVL2` procesa `/COPY,/IF` antes del precompilador |
| `ejecutar_cl(cmd)` | `system -s "CHGCURLIB… ; cmd"` → `ListingResultado` |
| `call_pgm(pgm, lib, parms)` | `CALL PGM(lib/pgm) PARM(…)` |

Limpieza: `limpiar_objeto(nombre, tipo="*PGM")` → `DLTOBJ`; `limpiar_ifs(path)` → `rm -f`.

## 5.4 Helpers

- `nombre_objeto(nombre)` — sanitiza a `UPPER` `[^A-Z0-9#$@_]` → `""`, máx 10, fallback `ORACULO`.
- `ListingResultado {ok, listing, exit_code}` — `listing` es siempre `out+"\n"+err` para que los colectores parseen diagnósticos.
