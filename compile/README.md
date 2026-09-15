# compile/ — Golden Corpus de compilación IBM i (oráculo, FASE 2)

Cada caso mide **un comando de compilación real** en IBM i y guarda fuente +
captura + expectativa normalizada. iNative lo consulta vía
`INATIVE_ORACLE_DIR` (nunca se copia al repo iNative).

## Layout

```text
compile/<lang>/<caso>/
  source.<ext>        # fuente de referencia (rpgle/clle/cbl/sqlrpgle/dspf)
  raw/provenance.json # de dónde salió la captura (sin duplicar datos)
  expected.json       # Normalized: success, object_created, max_severity,
                      # messages[{id,severity,line}], status, provenance
```

## expected.json

```json
{
  "case": "var-no-declarada",
  "language": "RPGLE",
  "success": false,
  "object_created": false,
  "max_severity": 30,
  "messages": [{"id": "RNF7030", "severity": 30, "line": 7}],
  "status": "gap",
  "provenance": {"measured": true, "ref": "esperado/...json",
                 "note": "..."}
}
```

- `status: stable` → iNative debe coincidir (el runner falla si difiere).
- `status: gap` → divergencia conocida y documentada (el runner solo informa).
- `provenance.measured: true` = medido en IBM i real (host/release/fecha en
  `ref`). `false` = supuesto documentado pendiente de captura.

## Casos

| Caso | Origen | Estado |
|---|---|---|
| rpg/var-no-declarada | medido pub400 7.5 (`esperado/RPGLE.invalidos.var-no-declarada.json`) | gap: iNative emite CPF9898 backend, no RNF7030/7503 |
| rpg/datfmt-iso | supuesto (IBM i acepta `*ISO`; captura pendiente) | stable (regresión de la decisión ISO) |
| sqlrpgle/hellos | fuente real del proyecto Hola Mundo; iNative limpio en ambas fases | pendiente de captura (COMMAND+JOBLOG+EVFEVENT+objeto+retorno) |
| dspf/hello-success | `CRTDSPF` éxito: `CPI2126`+`CPI2121`+`CPC7301`, Summary vacía + `CPC7301 00`, sin Final Summary | gap: command messages (harness completo pendiente) |
| rpgle/hello-success | `CRTBNDRPG` éxito con `datfmt(*iso)`: `RNS9304`+`CPC0904`, RNF7031+RNF7089 sev 00, Final (Info 2, Records 24) | gap: sev-00 + command messages. Fuente idéntica disponible |
| rpgle/hello_fixed-error | `CRTBNDRPG` fijo corrupto: `RNS9308`+`RNS9310`, 57 marcas (19×0262, 12×5375, F-spec, 5014, 6×7030-basura, 10×7503, 2×7421), `**UNDEF**`, GENLVL=10 | gap total en IDs. Nota: IBM imprime Total 53 (RNF5375 fuera del Summary, Severe 19 vs 20 contado): aritmética sin explicar, conservada tal cual |
| dds/hello (Golden Sample) | `CRTDSPF` real V7R5M0: command messages + listing 9 págs + Messages (18 IDs) + `CPF7311`/`CPF7302`, sin objeto | gap: iNative lo aceptaría (solo exige spec `A`); requiere validación DDS por columnas (CPD74xx). Fuente STMF exacta pendiente (reconstruible del listing) |
| dds/hello2 (Golden Sample 2) | `CRTDSPF` real V7R5M0, fuente 29 líneas: `CPF7302` (sev **40**, sin `CPF7311`) + Messages (CPD5238/CPD7508/CPD7596) + **Message Summary** por buckets (5/0/0/2/3), sin objeto | gap: mismo que hello. Novedades del modelo: buckets de severidad, regla GENLVL=20, `CPF7302` con 40. Líneas marcadas: 800 y 1300 |
| dds/hello-success | `CRTDSPF` éxito V7R5M0: `CPI2126`+`CPI2121`+`CPC7301`, listing 3 págs, Message Summary vacía + `CPC7301 00`, **sin Final Summary** (el éxito no la trae) | gap: command messages difieren (harness completo pendiente) |
| rpgle/hello_rpg-error | `CRTBNDRPG` RPG fijo V7R5M0: `RNS9308`+`RNS9310`, inline `=====>` con letras, 40 ocurrencias (19×RNF0262, 5×RNF7030, 9×RNF7503, F-spec, RNF5014), Cross Ref con `**UNDEF**`, sin objeto | gap total en IDs (iNative no valida fijo por columnas). GENLVL=10 medido |
| rpg/bloque-sin-endif (RNF5177) | medido, **sin fuente** | pendiente de captura con fuente |
| rpg/dup-declarada (RNF3316) | medido, **sin fuente** | pendiente |
| rpg/literal-sin-cerrar (RNF7030 *INLR) | medido, **sin fuente** | pendiente |
| rpg/token-raro (RNF0604+RNF5359) | medido, **sin fuente** | pendiente |
| DSPF.invalidos.* / CL.* | medidos, **sin fuente** | pendiente |
| rpgle/hello_rpg-error2 | Mismo programa, otro desplazamiento (15:20:22): F-spec resuelve (WORKSTN 13D), 45 ocurrencias (19×0262, 0289, 2003, 5014, 8×7030 con nombres reales por falta de INDARA e I-specs O-only, 12×7503), `RNS9308`+`RNS9310` | gap en IDs. Lección: el fijo es sensible a columnas (mismo fuente lógico, diagnósticos distintos) |
| dds/hello-success, rpgle/hello-success | Segundos runs idénticos (15:20:21/53, DSPF+RPGLE+HELLOD) | confirmaciones de estabilidad en provenance |
| rpgle/hello_rpg-error3 | Tercer desplazamiento (15:26:19): F-spec con RNF0289+RNF2003 y fuente MIXTA (F/I fijos + cálculos free Seq 002900+). Transcript parcial (págs 1-2, sin resultado) | sin expected (no inventar desenlace); evidencia de formato mixto |
| sqlrpgle/hellos-success | `CRTSQLRPGI` éxito: QSQLPRE+QSQLTEMP1 en QTEMP (`RNS9307` sev 00), fase RPG limpia (Total 0, Records 82), `RNS9304`. Confirma el modelo compuesto | gap: fase precompiler + command messages (harness completo pendiente) |
| sqlrpgle/hello_sql-error | `SQL9001: SQL precompile failed.` MEDIDO (forma USER OUTPUT de iNative confirmada). SQL1001 (rec 14, F-spec) + 2×SQL0312 (rec 21/30, `:USUARIO` O-only). Summary SQL con columna Terminal | gap en IDs (nuestro precompiler no valida host vars ni ficheros). RECORD 14 vs línea 16: doble numeración IBM |
| rpgle/hello_rpg-success | Fijo en ÉXITO (`RNS9304`, cero diagnósticos; F-spec idéntica a hello_rpg-error a simple vista: bytes invisibles mandan) | gap: sin Summary capturada (transcript parcial) + STMF pendiente |

| sqlrpgle/hello_sql-success | Fijo+SQL en ÉXITO (`RNS9304`, Total 0, 40 records; bloques `C/EXEC SQL` intactos en el listing) | gap: command messages + fase precompiler |
| cl/hello_cl-error | `CPF0820` + `CPD0043` x2 (RTVSYSVAL no acepta VAR; forma correcta: RTNVAR), Cross Ref con labels, Summary de 10 buckets, cierre con severidad máxima | gap: sin validador CL por comando |
| c/hello_c-success | `CZS1607` (+`CPF5D04` auth, sev inferida) sin listing | gap: regla IDs ILE C pendiente |
| cpp/hello_cpp-success | `CPD5D1E` (colisión) + `CPF5D04` + `CZS1607` sin listing | gap: regla IDs ILE C++ pendiente |
| cobol/hello_cbl-success | `LNC0901` + listing 7 págs: source STMT, 30 textos (31 impresos: falta 1 warning), Summary con buckets COBOL 00-04/05-19, GENLVL 30, cierre LNC0901 | gap en IDs (nuestro COBOL no emite diagnósticos) |

| cl/hello_cl-error2 | Segunda variante (QDATE LEN(6), IF simplificados, `*BCAT`, GOTO LOOP): mismo 2xCPD0043 en líneas 1900/2100 | gap en IDs |

| cl/hello_cl-success | CL en ÉXITO con `RTNVAR` (el fix correcto): cero diagnósticos, `CPC0815` | gap: command message (CPC0815 ya aplicado en código, con test) |
| cl/helloc-success | Menú CLLE 87 líneas en ÉXITO (`CPI2119`+`CPI2121`+`CPC0815`, Cross Ref multilínea, cierre doble) | gap: command messages |

Regla: sin fuente no hay caso (recompilar es el punto del corpus).
