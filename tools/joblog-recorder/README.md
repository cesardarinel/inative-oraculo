# tools/joblog-recorder — Herramienta independiente (plan §2)

> **No mezclar con `/internal/joblog` (runtime).** Este es el *recorder* de investigación/validación que genera el corpus `IBM i → fixture`. El runtime solo replaya.

Estructura exigida por plan §2 y §18:

```
tools/joblog-recorder/
  cmd/recorder/          CLI Go + wrapper Python (Record/Replay §20)
  internal/recorder/     lógica de captura (INITIAL→FINAL→DIFF §4)
  internal/joblog/       re-export de contratos (symlink lógico a internal/joblog)
  fixtures/
    raw/<ID>/capture.json
    normalized/<ID>.json
    manifests/<ID>.json
  metadata/
    recorder-version.json
    ibmi-environment.json
  tests/                 contract tests replay (§19)
```

Uso canónico:

```bash
# Record contra IBM i real
python3 -m probe.joblog_recorder record --id RPG-RUNTIME-001 --command "CALL PGM(QTEMP/DIVZERO)"
# o binario Go
go run ./tools/joblog-recorder/cmd/recorder record --id JOBLOG-0001 --command "CALL PGM(QTEMP/X)"

# Replay determinista sin IBM i
python3 -m probe.joblog_recorder replay RPG-RUNTIME-001
oraculo joblog diff --expected fixtures/joblog/normalized/RPG-RUNTIME-001.json --actual actual.json

# Wrapper tools/
./tools/joblog-recorder/cmd/recorder/replay.sh RPG-RUNTIME-001
```

Ver `fixtures/joblog/README.md` para matriz 8 niveles y `probe/joblog_recorder.py:MATRIX`.
