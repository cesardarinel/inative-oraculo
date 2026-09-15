# 04 — Fixtures

> Esquema §20 (`internal/fixture/fixture.go` + `probe/captura.py`).

## 4.1 Definición

Un fixture es el contrato versionado que iNative publica al oráculo. Vive en `fixtures/` o `conformance/<familia>/` y contiene fuentes + guion + expectativas de comparación.

```json
{
  "id": "HELLO-5250-001",
  "name": "Pantalla básica equivalente en IBM i e iNative",
  "source": {"rpgle": "./src/HELLO.rpgle", "dspf": "./src/HELLO.dspf"},
  "input": [
    {"type":"text","field":"CUSTOMER_ID","value":"1001"},
    {"type":"key","value":"ENTER"},
    {"type":"key","value":"F3"}
  ],
  "compare": {"screens": true, "fields": true, "cursor": true, "attributes": true, "indicators": true},
  "ignore": ["job.number","timestamp"],
  "transport": "auto"
}
```

Tipos de `source` (`fixture.go:10-18`): `rpgle|cl|dspf|pf|lf|other` — `probe/captura.py:98-101` los mapea a extensión real (`sqlrpgle` preservada).

Tipos de `InputAction` (`fixture.go:21-25`): `text|key|field|command|wait|sql` — `field` y `text` son alias de relleno de campo; `sql` ejecuta `db.ejecutar_sql` vía ODBC; `command/cmd` es CL batch (`CALL`, `CRTLIB`, etc.).

## 4.2 Resolución de fuentes

`probe/captura.py:32-52` — `_resolve_source_path`:

1. `path(src)` si es absoluto y existe
2. `fixture_path.parent / src`
3. `repo/fixtures / src`
4. `repo/conformance / src` (y búsqueda recursiva por `name`)

Si no se encuentra → warning y se omite (`captura.py:96`).

## 4.3 Compare / Ignore

```go
type ComparaSet struct {
  Screens, Fields, Cursor, Attributes, Indicators, ResponseKey bool
  Display, DisplayLiterals, DisplayGrid, DisplayRaw bool
}
// UnmarshalJSON: Display:true habilita Screens+Fields+Literals+Grid
```

`compare` declara qué aspectos deben coincidir; los no listados se excluyen. `ignore` es lista de paths (case-insensitive, substring) que el comparador y normalizadores aplican — ver `03-matriz-compatibilidad.md`.

## 4.4 Ejemplos por familia

| ID | Fuente | Compara | Qué valida |
|----|--------|---------|------------|
| `HELLO-5250-001` (conformance/dspf) | `rpgle+dspf` | screens/fields/cursor/attributes/indicators | Display semántico §9.2 |
| `RPGLE.invalidos.var-no-declarada` | `rpgle` inválido | mensajes | `RNF7030 línea 7` |
| `DSPF.invalidos.sin-rcdfmt` | `dspf` sin `RCD_FMT` | joblog/libl | `CPD5238` |
| `CATALOGO.C3S411` | `sql` catalogo | db | `QSYS.C3S411` |

## 4.5 CLI

```bash
./binario/oraculo fixture conformance/dspf/HELLO-5250-001.json   # valida fixture §20
python -m probe.captura --fixture conformance/dspf/HELLO-5250-001.json --out esperado
# compat rpgle suelto:
python -m probe.captura fixtures/RPGLE/invalidos/var-no-declarada.rpgle RPGLE.invalidos.var-no-declarada
make captura FIXTURE=conformance/dspf/HELLO-5250-001.json
make captura-all  # recorre conformance/**/*.json
```
