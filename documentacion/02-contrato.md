# 02 — Contrato entre repositorios

> Define el handshake entre **iNative** (productor de fixtures) y **iNative-oraculo** (validador contra IBM i real).

## 2.1 Flujo

```
iNative                    oráculo
  │  fixture + manifest        │
  │  (id, source, input,      │
  │   compare, ignore)        │
  ├──────────────────────────►│
  │                           │  probe/captura.py
  │                           │  1. subir fuentes (IFS/SRCPF)
  │                           │  2. CRTBNDRPG/CRTDSPF/… vía SSH
  │                           │  3. setup/input (CL batch o TN5250)
  │                           │  4. colectar 6 observables
  │                           │  5. normalizar → esperado/<ID>.json
  │  esperado/<ID>.json       │
  ◄───────────────────────────┤
  │  comparador (internal/)   │
  │  expected vs actual →     │
  │  PASS / divergencias      │
```

## 2.2 Formato del snapshot dorado

`probe/captura.py:322-339` — JSON canónico (indent 2, utf-8):

```json
{
  "contrato_version": 1,
  "fixture": "RPGLE.invalidos.var-no-declarada",
  "ibmi": {
    "host": "pub400.com",
    "release": "7.5",
    "ccsid": 37,
    "capturado": "2026-08-25T22:26:09+00:00",
    "exit_code": 1,
    "ok": false
  },
  "observables": [
    {"kind":"mensajes","name":"RNF7030","value":"The name or indicator VARNOMBRE is not defined.","severidad":30,"linea":7,"norm":"The name or indicator VARNOMBRE is not defined."},
    {"kind":"mensajes","name":"RNF7503","value":"Expression contains an operand that is not defined.","severidad":30,"linea":7}
  ]
}
```

Reglas guía §2.2:

- `contrato_version: int` (no string).
- `ibmi.release` en forma `7.5`, `ccsid` int (37 = EBCDIC US).
- `observables` es array de `{kind, name, value, …}` — los campos extra (`severidad`, `linea`, `norm`) se preservan.

Obsolescencia compat: `probe/captura.py:366` expone `capturar(fixture, nombre, out_dir)` para `.rpgle` suelto (legado vertical 1); el camino canónico es `capturar_fixture(fixture_path, out_dir)`.

## 2.3 Que se compara (y que se ignora)

El `fixture.compare` declara qué aspectos semánticos deben coincidir; `fixture.ignore` lista paths no-deterministas (case-insensitive, substring match — ver `internal/comparador/comparador.go:64-82`):

```json
{
  "compare": {"screens": true, "fields": true, "indicators": true},
  "ignore": ["job.number", "timestamp"]
}
```

El comparador produce `{PASS: bool, Divergencias: [{Path, Esperado, Actual}]}` — → `09-reportes.md`.

## 2.4 Versionado

- `CONTRATO_VERSION = 1` en `probe/captura.py:21` y `internal/version/version.go`.
- Cambios breaking → bump mayor + snapshots re-capturados.
- Los nombres `ibmi-runner/`, `colectores/`, `normalizador/` de la guía §001 corresponden en código a `probe/runner_ibmi.py`, `probe/colectores/`, `probe/normalizar.py` y los contratos Go en `internal/`.

## 2.5 Límites del contrato

- El oráculo mantiene sus propias credenciales (`oracle.env` no versionado, plantilla `oracle.env.example` sí) — fuera del repo central.
- **Matriz de compatibilidad** (→ `03-…`) es el único conjunto comparable; nada fuera de esos observables puede exigir PASS.
- Transporte: `ssh` (batch) siempre disponible; `tn5250` solo si el fixture lo requiere (`compare.display*` / input `key`/`field`).
