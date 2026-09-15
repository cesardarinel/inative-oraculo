# Documentación iNative-oraculo — Índice

> Oráculo externo que captura snapshots dorados contra IBM i real para que iNative local sea indistinguible del sistema nativo. El plan táctico de ingeniería inversa (Fases 1-6) fue ejecutado y consolidado en **COMPILADOR_IBM_I_ESPECIFICACIONES.md**.

## Mapa de documentación

| # | Documento | Qué contiene |
|---|-----------|--------------|
| **★** | [COMPILADOR_IBM_I_ESPECIFICACIONES.md](COMPILADOR_IBM_I_ESPECIFICACIONES.md) | **Documento maestro** — JobLog, Spool (listing), EVFEVENT, metadatos `QSYS2`→SQLite, regex/spools/SQL reales PUB400 7.5, requisitos para iNative Go+SQLite. **Empieza aquí.** |
| 0 | `00-indice.md` (este archivo) | Mapa del repo y del plan de 5+1 fases. |
| 1 | [01-vision.md](01-vision.md) | Misión, clean-room, estado (vertical 1 en curso). |
| 2 | [02-contrato.md](02-contrato.md) | Handshake iNative↔oráculo, formato snapshot dorado, versionado. |
| 3 | [03-matriz-compatibilidad.md](03-matriz-compatibilidad.md) | Kinds observables (`mensajes/job/display/…`), comparador, qué sí/no se compara. |
| 4 | [04-fixtures.md](04-fixtures.md) | Esquema fixture §20 (`source/input/compare/ignore`), resolución de fuentes, CLI. |
| 5 | [05-ibmi-runner.md](05-ibmi-runner.md) | `RunnerIBMi` — `system -b`, `SRCSTMF`/`SRCPF`, `CRTBNDRPG/CRTDSPF/CRTSQLRPGI`, limpieza. |
| 6 | [06-colectores.md](06-colectores.md) | `mensajes.py`/`joblog.py`/`catalogo.py`/`display_5250.py` — regex y formatos reales. |
| 7 | [07-normalizador.md](07-normalizador.md) | Normalización determinista por kind (Python+Go). |
| 8 | [08-esperado.md](08-esperado.md) | `esperado/` — snapshots dorados versionados, flujo de actualización. |
| 9 | [09-reportes.md](09-reportes.md) | `comparador` PASS/FAIL + `Divergencia.path`, reportes, laxismos. |
| 10 | [10-plan.md](10-plan.md) | Roadmap de verticales, cronograma 3 días, siguientes pasos. |
| — | [diseno-oracle-python.md](diseno-oracle-python.md) | Diseño de `probe/` (captura/orquestador), display 5250 + TN5250, dependencias. |
| — | [vscode.md](vscode.md) | Plan del recolector autónomo `inative-capturer` (origen, aplicado en `cmd/capturer/`). |
| — | `cmd/capturer/main.go` | **Recolector autónomo Go** — SSH + 4 casos + JobLog/EVFEVENT/Spool → `especificaciones_ibmi.json` + `COMPILADOR…md`. |

## El plan de 5+1 fases — estado

| Fase | Objetivo | Artefacto | Estado |
|------|----------|-----------|--------|
| 1 | Preparar `TESTINAT` + 4 casos HOLA/ERROR_* / EVENT_TEST | §1 en maestro | ✅ Capturado (PUB400) |
| 2 | JobLog vía `QSYS2.JOBLOG_INFO` o `DSPJOBLOG` spool | §2 | ✅ `joblog.py` + tabla mensajes |
| 3 | Spool `QSYSPRT` + regex listing RPG/DDS | §3 | ✅ `_PATRON_LINEA`/`_PATRON_DDS` |
| 4 | EVFEVENT (`E/W/I`, `EVT_LINE/COLUMN` 1-indexed) → DDL SQLite | §4 | ✅ Spec + DDL |
| 5 | Metadatos `OBJECT_STATISTICS` / `PROGRAM_EXPORT_IMPORT_INFO` → `modules/programs` | §5 | ✅ Tablas mapeo |
| 6 | Consolidar `COMPILADOR_IBM_I_ESPECIFICACIONES.md` + scripts validación | §6-§8 | ✅ Este repo |

## Cómo leer esta doc

1. **Equipo iNative Go**: lee `COMPILADOR_IBM_I_ESPECIFICACIONES.md` completo — es la spec ejecutable (SQL/regex/DDL/scripts de validación).
2. **Operación del oráculo**: `01 → 02 → 04 → 05 → 06 → 07 → 08 → 09`.
3. **Onboarding rápido**: `README.md` (root) + `10-plan.md` + `make help`.

## Convenciones

`ibmi-runner/` (doc) ↔ `probe/runner_ibmi.py` + `internal/runner/`; `colectores/` ↔ `probe/colectores/` + `internal/colectores/`; `normalizador/` ↔ `probe/normalizar.py` + `internal/normalizador/`. Ver nota en `README.md`.

---

## Plan táctico original (referencia, Fases 1-6)

> El contenido a continuación es el plan táctico recibido — se preserva como referencia. La implementación ejecutada está en `COMPILADOR_IBM_I_ESPECIFICACIONES.md`.

---

Tu objetivo es **extraer las especificaciones exactas** de cómo el compilador nativo se comunica con el IDE (JobLog, Spool, EVFEVENT y metadatos SQL) para que el equipo de iNative pueda replicarlo **al milímetro** en Go y SQLite.

El plan de 5 fases táctico para capturar toda esta información y entregar documentación ejecutable al equipo de desarrollo fue:

### Fase 1: Preparación del Campo de Pruebas (Día 1)

```sql
CRTLIB LIB(TESTINAT) TYPE(*TEST)
CRTSRCPF FILE(TESTINAT/QRPGLESRC) RCDLEN(112)
CRTSRCPF FILE(TESTINAT/QCLSRC) RCDLEN(112)
```

Casos de prueba: `HOLA.RPGLE` (éxito), `ERROR_SINT.RPGLE` (sintaxis), `ERROR_LINK.RPGLE` (símbolo no resuelto), `EVENT_TEST.RPGLE` (OPTION(*EVENTF)).

### Fase 2: Captura del Job Log

```bash
CRTBNDRPG PGM(TESTINAT/HOLA) SRCFILE(TESTINAT/QRPGLESRC) OPTION(*EVENTF)
```
```sql
SELECT MESSAGE_ID, MESSAGE_TYPE, SEVERITY, MESSAGE_TEXT, FROM_LINE, FROM_COLUMN
FROM TABLE(QSYS2.JOBLOG_INFO('*')) WHERE JOB_NAME = QSYS2.JOB_NAME
  AND (MESSAGE_ID LIKE 'CPF%' OR MESSAGE_ID LIKE 'RNF%')
ORDER BY ORDINAL_POSITION;
```

### Fase 3: Extracción del Spool

```bash
CRTBNDRPG PGM(TESTINAT/HOLA) SRCFILE(TESTINAT/QRPGLESRC) GENOPT(*SOURCE)
```
```sql
SELECT SPOOLED_FILE_NAME, DATA FROM TABLE(QSYS2.SPOOLED_FILE_INFO('*ALL','*ALL','*ALL','*CURRENT'));
```

### Fase 4: EVFEVENT

```bash
CRTBNDRPG PGM(TESTINAT/EVENT_TEST) SRCFILE(TESTINAT/QRPGLESRC) OPTION(*EVENTF)
```
```sql
SELECT * FROM TESTINAT.EVFEVENT WHERE MBRNAME = 'EVENT_TEST';
-- Columnas: EVT_TYPE(E/W/I), EVT_LINE, EVT_COLUMN, EVT_MSGID, EVT_MSGTXT, EVT_SEVERITY
-- 1-indexed; script DDL SQLite en maestro §4.3
```

### Fase 5: Metadatos SQL

```sql
SELECT OBJNAME, OBJATTRIBUTE, CREATION_TIMESTAMP, BINARY_SIZE, COMPILER_VERSION
FROM TABLE(QSYS2.OBJECT_STATISTICS('TESTINAT','*MODULE'));
SELECT SYMBOL_NAME, SYMBOL_TYPE, LINKAGE_TYPE FROM QSYS2.PROGRAM_EXPORT_IMPORT_INFO
WHERE PROGRAM_NAME='HOLA' AND PROGRAM_LIBRARY='TESTINAT';
SELECT PROGRAM_NAME, DEFAULT_ACTIVATION_GROUP FROM QSYS2.SYSPROCS WHERE PROGRAM_LIBRARY='TESTINAT';
```

### Fase 6: Consolidación

Reunido y ejecutado en `COMPILADOR_IBM_I_ESPECIFICACIONES.md` (§1-§8) con metodología PUB400 7.5 real, regex verificados y DDL listo para SQLite.

**Consejos preservados del plan**: EVFEVENT solo lleva errores (no AST); stdout SSH debe ser idéntico al IBM i real para Code for IBM i; spool en `spooled_files` para `WRKSPLF`.
