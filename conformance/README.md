# conformance/ — Conformance Suite

Suite de conformidad del oráculo (ver plan maestro §19 y §20). Cada
subdirectorio agrupa **fixtures versionados** de una familia de observables de
la [matriz de compatibilidad](../documentacion/03-matriz-compatibilidad.md).

El oráculo ejecuta el fixture equivalente en un **IBM i real**, recolecta los
observables, los **normaliza** y los **compara** con la salida local simulada
usando `internal/comparador` (PASS/FAIL + divergencias). El resultado alimenta
`reportes/`.

## Familias (según §19)

| Carpeta | Fixture(s) de referencia (§19 tabla) | Observable principal |
|---|---|---|
| `library-list` | `library-resolution` | resolución de objetos por LIBL |
| `object-resolution` | — | objeto resuelto, biblioteca |
| `qtemp` | `qtemp-isolation` | visibilidad y limpieza de QTEMP |
| `authority` | `authority-denied` | message id, job log, operation state |
| `pf-lf` | — | campo/textura de PF/LF |
| `chain-read` | `chain-not-found` | FOUND/ERROR/EOF y flujo |
| `setll-reade` | — | posicionamiento clave |
| `packed-zoned` | `packed-decimal` | valor exacto y flags |
| `indicators` | — | estado de indicadores |
| `messages` | — | catálogo y Job Log |
| `monmsg` | — | captura de errores por MONMSG |
| `overrides` | `override` | objeto efectivo y datos leídos |
| `locks` | `locking` | wait/timeout/failure |
| `commit-rollback` | `commit-rollback` | estado final de datos |
| `journal` | — | formato de evento estable |
| `dspfd` | — | descripción de archivo |
| `dspf` | `HELLO-5250-001` | pantalla/display (§9.3, §18) |
| `job-lifecycle` | — | ciclo de vida de job |

## Contrato de cada fixture

Formato JSON según §20 (`id`, `name`, `source`, `input`, `compare`, `ignore`),
modelado en `internal/fixture`. La comparación de pantallas usa el
`DisplaySnapshot` de `internal/colectores` (§9.2) y el `internal/comparador`.

## Ejecución

```bash
make test          # pruebas Go (contratos + comparador)
python -m probe.captura ...   # descubrimiento de snapshot dorado
```

> Regla (§20/§24): nunca se versionan credenciales ni rutas específicas del
> IBM i en los fixtures; solo fuentes, manifest, snapshot esperado y la
> versión del contrato.
