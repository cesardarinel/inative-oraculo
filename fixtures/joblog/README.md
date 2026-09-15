# JobLog Fixtures — Biblioteca de comportamiento real de IBM i

Esta carpeta es el **corpus de comportamiento observable** que permite a iNative
reproducir el Job Log de forma determinista sin inventar mensajes.

> **Regla principal §0**: primero capturamos el comportamiento real, después
> implementamos el comportamiento simulado. No inventamos mensajes del simulador.

## Estructura (§18 + §14)

```
fixtures/joblog/
  raw/<ID>/capture.json         # respuesta exacta tal cual fue obtenida (dynamic intact)
  normalized/<ID>.json          # representación estable para iNative (placeholders)
  manifests/<ID>.json           # cómo fue producido cada fixture
```

Plus legacy para el comparador actual:

```
esperado/<ID>.json              # {contrato_version, observables:[{kind:joblog,…}]}
```

Dynamic vs static (§15):

- STATIC: message_id, message_type, severity, message_text, ordinal_position, second_level
- DYNAMIC: job_number, job_name, job_user, timestamp, system_name, message_key, from_program

## Matriz de experimentos (§6-§13)

| Nivel | Categoría | Ejemplos |
|-------|-----------|----------|
| 1 | commands/success | CRTBNDRPG, CRTRPGMOD, CALL, DSPLY |
| 2 | commands/* error | invalid-command, invalid-parameter, object-not-found, library-not-found, member-not-found |
| 3 | rpgle/compile/* | syntax-error, semantic-error, file-error (RNF/RNS) |
| 4 | rpgle/runtime/* | divide-by-zero, array-oob, decimal-error, program-not-found |
| 5 | fileio/* | chain, read, reade, setll, setgt, write, update, delete, eof |
| 6 | cl/* | DCL, CHGVAR, MONMSG, SNDPGMMSG, RCVMSG, OVRDBF, DLTF |
| 7 | messages/* | sndpgmmsg, dsply, diagnostic, escape, completion |
| 8 | diagnostic chain | ERROR → DIAGNOSTIC → ESCAPE (orden es contrato) |

Ver `probe/joblog_recorder.py:MATRIX` para catálogo smoke inicial (12 casos).

## Workflow §4

```
INITIAL SNAPSHOT
      │
      ▼
EXECUTE OPERATION
      │
      ▼
FINAL SNAPSHOT
      │
      ▼
DIFF  →  fixture
```

No asumir que el Job Log empieza vacío; el delta es el contrato.

## Recorder (Record / Replay) §20-§21

```bash
# Record (requiere IBM i real)
python3 -m probe.joblog_recorder record --id JOBLOG-0001 --name "divide_by_zero" --language RPGLE --command "CALL PGM(QTEMP/DIVZERO)"

# Record desde fixture existente
python3 -m probe.joblog_recorder record --fixture conformance/joblog/RPG-RUNTIME-001.json --id RPG-RUNTIME-001

# Replay sin IBM i
python3 -m probe.joblog_recorder replay JOBLOG-0001
python3 -m probe.joblog_recorder replay   # lista disponibles

# Matriz smoke completa
python3 -m probe.joblog_recorder record-matrix

# Listar catálogo
python3 -m probe.joblog_recorder list
```

Cada fixture pasa por estados §21: CAPTURED → REVIEWED → VERIFIED.

## Contract Test §19

```go
expected := joblog.LoadFixture("fixtures/joblog/normalized/RPG-RUNTIME-001.json")
actual := ctx.JobLog.Messages()
if diffs := joblog.AssertEqual(expected.JobLog.Messages, actual); len(diffs) > 0 { t.Fatalf(...) }
```

El orden forma parte del contrato; compara ID, type, severity, ordinal y texto normalizado.
Campos dinámicos se ignoran por diseño.
