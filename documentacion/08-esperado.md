# 08 — Snapshots esperados

> `esperado/` — snapshots dorados versionados capturados contra IBM i real. Son la fuente de verdad del oráculo.

## 8.1 Formato

Cada `esperado/<ID>.json` tiene `contrato_version: 1` (int) y dos bloques:

```json
{
  "contrato_version": 1,
  "fixture": "RPGLE.invalidos.var-no-declarada",
  "ibmi": {"host":"pub400.com","release":"7.5","ccsid":37,"capturado":"2026-08-25T22:26:09+00:00","exit_code":1,"ok":false},
  "observables": [
    {"kind":"mensajes","name":"RNF7030","value":"The name or indicator VARNOMBRE is not defined.","severidad":30,"linea":7,"norm":"…"},
    {"kind":"mensajes","name":"RNF7503","value":"Expression contains an operand that is not defined.","severidad":30,"linea":7}
  ]
}
```

Generado por `probe/captura.py:322-360` tras normalización por kind (`normalizar_observables` con `ignore` del fixture). Incluye `screens` doradas (`HELLO-5250-001.screens.json`) con `DisplaySnapshot` extendido (literals/grid/raw) cuando `compare` pide display.

## 8.2 Convenciones

- `fixture` = `id` del fixture (o `Path.stem`).
- `ibmi.capturado` en UTC ISO-8601 con timezone.
- `observables` respeta `kind` de la matriz (§03) y lleva `norm` para `mensajes` legacy (`probe/tests/test_normalizar.py`).
- Snapshots con `exit_code:0, ok:true, observables:[]` → compilación limpia (ej. `RPGLE.validos.hola-dsply`).

## 8.3 Flujo de actualización

```bash
# 1) Captura (requiere oracle.env)
python -m probe.captura --fixture conformance/dspf/HELLO-5250-001.json --out esperado
make captura FIXTURE=conformance/dspf/HELLO-5250-001.json
make captura-all   # recorre conformance/**/*.json

# 2) Verifica diff contra iNative local
./binario/oraculo diff --fixture conformance/dspf/HELLO-5250-001.json --expected esperado/HELLO-5250-001.json --actual /tmp/actual.json

# 3) Commit si PASS
git add esperado/HELLO-5250-001.json && git commit -m "esperado: HELLO-5250-001 PUB400 7.5"
```

Importante: `esperado/` es **git-versionado**; `reportes/` no.

## 8.4 Inventario actual

`go list` de `esperado/` (2026-08-25): `CATALOGO.C3S411`, `CL.env.*`, `DSPF.*`, `DSPJOBLOG-001`, `EDTLIB-001`, `HELLO-5250-001(+.screens)`, `IND-001`, `PF-001`, `RPGLE.*` (6 válidos/inválidos), `RPGLE.sqlrpgle.copy-*` — ver `esperado/README.md`.
