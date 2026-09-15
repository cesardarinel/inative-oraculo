# inative-capturer — recolector autónomo (plan `documentacion/vscode.md`)

Binario Go que, en **una sola ejecución**, se conecta por SSH a un IBM i real, crea `TESTINAT`, inyecta 4 fuentes RPGLE (`HOLA`/`ERROR_SINT`/`ERROR_LINK`/`WARNING_TEST`), ejecuta los comandos exactos de Code for IBM i y captura **stdout/stderr + JobLog + EVFEVENT + Spool** para generar `especificaciones_ibmi.json` + `documentacion/COMPILADOR_IBM_I_ESPECIFICACIONES.md`.

## Setup

```bash
cp capturer_config.json.example capturer_config.json
# edita host/user/password/lib (o usa oracle.env existente)
cat capturer_config.json
```

Alternativa: el capturer lee `oracle.env` si `capturer_config.json` no existe (mismo formato que `probe/`).

## Uso

```bash
# listado de casos embebidos
go run ./cmd/capturer --list

# mock sin IBM i (CI / prueba del pipeline)
make capturer-dry
# o
go run ./cmd/capturer --dry-run --out /tmp/especificaciones_ibmi.json --docs /tmp/COMPILADOR_IBM_I_ESPECIFICACIONES.md

# real contra PUB400
make capturer
# o
go run ./cmd/capturer --config capturer_config.json --out especificaciones_ibmi.json --docs documentacion/COMPILADOR_IBM_I_ESPECIFICACIONES.md
./binario/capturer --help

# build
make build-capturer   # → binario/capturer
```

## Salidas

| Archivo | Contenido |
|---------|-----------|
| `especificaciones_ibmi.json` | `{generated_at, cases, results:[{test_case, source_code, commands:[{command,stdout,stderr,exit_code}], joblog:[{message_id,severity}], evfevent:[{evt_type,evt_line,evt_msgid}], spool_data}]}` |
| `documentacion/COMPILADOR_IBM_I_ESPECIFICACIONES.md` | Markdown con tablas por caso (stdout/joblog/evfevent/spool) + §§ EVFEVENT/JobLog/Spool/SQLite DDL. |

## Notas

- Usa `system -b` para CRT* (listing completo por stdout) — ver `probe/runner_ibmi.py:65`.
- `EVT_LINE/COLUMN` son 1-indexed; DDL SQLite en §5 del doc.
- `--dry-run` produce 4 casos mock (CPF0000/RNF7030/CPD0053/RNF0000) sin red.
