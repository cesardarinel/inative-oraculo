# 10 — Plan de implementación

> Roadmap de verticales del oráculo (plan maestro adaptado a la implementación actual).

## 10.1 Estado — “Descubrimiento primero”

| Vertical | Descripción | Estado | Artefactos |
|----------|-------------|--------|------------|
| **1** | Mensajes de compilación (RNF/CPD/CPF) | **En curso** | `mensajes.py`, `joblog.py`, `runner_ibmi.py`, `esperado/RPGLE.*.json`, `fixtures/RPGLE/invalidos/` |
| **2** | Catálogo de mensajes QCPFMSG | Parcial | `catalogo.py`, `esperado/CATALOGO.C3S411.json` |
| **3** | Fidelidad 5250 (display semántico + literal/grid/raw + TN5250) | Implementado | `display_5250.py`, `display_codec.py`, `display.py`, `conformance/dspf/HELLO-5250-001`, `esperado/HELLO-5250-001.screens.json` |
| **4** | Datos / DB (PF/LF, overrides, SQL) | Esqueleto | `db.py`, `crtsqlrpgle` con `RPGPPOPT`, `normalizar_db` |
| **5** | Job / LIBL / Objects / locks | Esqueleto | `joblog.py` captura LIBL/objects vía `OBJECT_STATISTICS`, `comparador` cubre `libl/objects/db/joblog/return` |
| **6** | Pantallas reales end-to-end (TN5250 login + command) | Implementado | `TN5250Client` (TELNET+GDS), `captura.py` input loop, `probe/tn5250j_headless/` proxy |

Contratos Go (`internal/`) alineados con plan: `fixture` §20, `colectores` §9.2/§18, `comparador` §20, `normalizador` §2.3.

## 10.2 Cronograma (escalado al ZIP actual)

| Día | Actividad (Fases 1-6 de COMPILADOR…md) | Entregable |
|-----|----------------------------------------|------------|
| **D1 mañana** | Crear `TESTINAT`, `QRPGLESRC`, 4 programas `HOLA/ERROR_*` | Entorno listo (Fase 1) |
| **D1 tarde** | `CRTBNDRPG` + `JOBLOG_INFO`/`SPOOLED_FILE_INFO` + regex listing | §2 y §3 completos |
| **D2 mañana** | `OPTION(*EVENTF)` + `EVFEVENT` + DDL SQLite | §4 + §6.1 |
| **D2 tarde** | `OBJECT_STATISTICS` + `PROGRAM_EXPORT_IMPORT_INFO` + LIBL | §5 |
| **D3** | Redactar `COMPILADOR_IBM_I_ESPECIFICACIONES.md` + scripts validación | §6 + este plan |

## 10.3 Siguientes pasos

1. **Solidificar vertical 1**: añadir fixtures `ERROR_SINT/ERROR_LINK/EVENT_TEST` a `conformance/` con `concomp` de casos B/C y re-capturar con `OPTION(*EVENTF)` para materializar `EVFEVENT` real.
2. **Codificar `EVFEVENT` en SQLite** (DDL §4.3) y exponerlo como observable `evfevent` en `captura.py`.
3. **Cerrar `libl/objects` con validación QLCL**: comandos `ADDLIBLE/CHGCURLIB` + `DSPLIBL` ya en `esperado/CL.env.*.json` — faltan tests de regresión `make test`.
4. **Publicar `oraculo` v0.1**: freeze `contrato_version=1`, etiquetar snapshots PUB400 7.5.

## 10.4 Convenciones de nomenclatura

`ibmi-runner/` (doc) ↔ `probe/runner_ibmi.py` + `internal/runner/`; `colectores/` ↔ `probe/colectores/` + `internal/colectores/`; `normalizador/` ↔ `probe/normalizar.py` + `internal/normalizador/` — ver `README.md` nota de alineación.
