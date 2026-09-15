# 01 — Visión y misión del oráculo

## Qué es

**iNative-oraculo** es un oráculo externo para **iNative**: se conecta a un **IBM i real** (PUB400 7.5), ejecuta *fixtures* equivalentes y captura **snapshots JSON dorados** que indican a iNative exactamente qué simular — mensajes, datos, indicadores, estado de job, resolución de objetos, *locks*, transacciones y display.

No es parte del producto. No se distribuye ni se enlaza en tiempo de compilación o ejecución local. Su única misión es **determinar y validar** el comportamiento que el runtime local debe reproducir. Puede desaparecer y `inative run / serve / test --local` debe seguir funcionando.

## Por qué existe (clean-room)

El runtime local de iNative se desarrolla bajo enfoque *clean-room* basado únicamente en documentación pública y en observables capturados por el oráculo. No se incluye código propietario de IBM. El oráculo es la **única pieza autorizada** para tocar un sistema real y producir pares `esperado/`.

## Qué valida

La comparación usa únicamente los **observables definidos por la matriz de compatibilidad** (→ `03-matriz-compatibilidad.md`):

`datos | mensajes | indicadores | job | objetos | locks | transacciones | display`

Si el par `esperado` (IBM i) y `actual` (iNative local) coinciden tras **normalización determinista** (→ `07-normalizador.md`), la simulación es indistinguible del real para ese fixture.

## Estado actual

**Descubrimiento primero** (vertical 1 en curso): captura de mensajes de compilación (`RNF`/`CPD`/`CPF`) y catálogo contra PUB400.

- **Python** (`probe/`) — *probing* rápido: SSH+SFTP+ODBC+TN5250, runner, colectores, normalizador, orquestador `captura.py`.
- **Go** (`internal/` + `oraculo/`) — contratos estables: `DisplaySnapshot` (§9.2/§18), esquema fixture (§20), comparador PASS/FAIL + divergencias (§20), suite `conformance/`.

## Artefactos dorados

Versión de contrato única: `contrato_version = 1` (int, `probe/captura.py:21`). Cada snapshot `esperado/<ID>.json` porta `{ibmi: {host, release, ccsid, capturado, exit_code, ok}, observables: [...]}` y queda versionado en git.

## Relación con iNative

iNative publica el **fixture + manifest + versión de contrato**; el oráculo lo ejecuta en IBM i y devuelve un resultado **normalizado** (`esperado/`). La suite `conformance/` cubre familias de observables (§19) con caso de referencia `HELLO-5250-001` (§9.3). Es unidireccional: iNative nunca llama al IBM i real en flujo local.
