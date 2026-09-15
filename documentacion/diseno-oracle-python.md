# Diseño del oráculo (Python)

> `probe/` — orquestador de descubrimiento rápido en Python 3.11+. El esqueleto Go (`internal/`) es mirror de contratos; la lógica de captura vive en Python para iterar contra PUB400 sin recompilar.

## Arquitectura

```
probe/
├── config.py          Config desde oracle.env (host/user/pass/lib/ccsid/ports, release 7.5)
├── conect.py          ConectarIBMi: SSH(QSH+QSH), SFTP(IFS), ODBC(Db2), TN5250(socket+ssl)
├── runner_ibmi.py     RunnerIBMi: subir fuentes (IFS/SRCPF), CRTBNDRPG/CRTDSPF/CRTSQLRPGI, ejecutar CL, limpiar
├── captura.py         Orquestador: fixture JSON → subir → compilar → setup/input (batch/TN5250) → colectar 6 observables → normalizar → esperado/<ID>.json
├── normalizar.py      Normalización por Kind (display/joblog/libl/objects/db/return)
└── colectores/
    ├── mensajes.py    _PATRON_LINEA (RNF) + _PATRON_DDS (CPD) — listing real 5770WDS
    ├── joblog.py      QSYS2.JOBLOG_INFO → spool DSPJOBLOG/CPYSPLF → parse_joblog_text
    ├── libl.py        QSYS2.LIBRARY_LIST_INFO
    ├── objects.py     QSYS2.OBJECT_STATISTICS
    ├── catalogo.py    DSPMSGD/RTVMSGD QCPFMSG (rangos familia RNF/CPF/…)
    ├── db.py          SELECT * vía ODBC
    ├── display.py     DisplaySnapshot semántico (artífice lógico, sin 5250 real)
    ├── display_5250.py TN5250Client (TELNET+GDS+EBCDIC cp37) + decode_5250_stream
    └── display_codec.py Codec 5250 (SBA/SF/RA, EBCDIC→str, AID, EBCDIC grids)
    tn5250j_headless/   Fallback Java tn5250j + proxytls.go (port 992 → TLS)

internal/ (mirror Go, requerido por inative local):
  colectores/display.go  DisplaySnapshot tipado + Kinds
  fixture/fixture.go     Fixture/ComparaSet/Source
  comparador/            Comparator PASS/FAIL (esIgnorable)
  normalizador/          SerializarDisplay
  version/version.go     CONTRATO_VERSION = 1
```

## Flujo de `captura.py:56-362`

1. `load(env_file)` → `Config.validate()` (host/user/pass).
2. `_load_fixture(path)` + `_resolve_source_path` (fixture-relative → fixtures/ → conformance/ recursively).
3. Para cada `source` (`rpgle/dspf/pf/lf/cl/sqlrpgle`): `runner.subir_fuente → crtbndrpg/crtdspf/crtpf/crtsqlrpgle` → `parsear_listing(listing)` → acumula `joblog_accum` + `last_rc`.
4. Para cada `setup` step: `runner.ejecutar_cl(cmd)` → acumula joblog.
5. Para cada `input` step (`command/key/field/text/wait/sql`): si `needs_display` y `use_tn5250` → `con.tn5250().negotiate() + capture()`; luego dispatch: `sql→db.ejecutar_sql`, `command→tn.execute_command|ssh`, `key→press_key`, `field/text→send_fields` (espera ENTER), `wait→sleep`.
6. Colecta batch: `joblog (accum+JOBLOG_INFO)`, `libl`, `objects`, `db` (si fixture.db).
7. `display_5250.to_observable(snapshots)` + `normalizar_observables(observables, ignore)` → `{contrato_version, fixture, ibmi, observables}` → `esperado/<ID>.json`.

Compat: `capturar(fixture,nombre,out_dir)` preserva firma legacy `python -m probe.captura file.rpgle nombre`.

## Dependencias

`requirements.txt`: `paramiko` (SSH/SFTP), `pyodbc` (opcional), `slow` sockets stdlib para TN5250 (sin lib externa). Tests: `pytest probe/tests` (`test_captura_offline`, `test_colectores_parsers`, `test_display_codec`, `test_normalizar`).

## Tests

```bash
pytest -q probe/tests                 # parsers listing/joblog, normalización, display_codec
python -m probe.captura --fixture conformance/dspf/HELLO-5250-001.json --out esperado
go test ./...                         # fixture/comparador/normalizador
```
