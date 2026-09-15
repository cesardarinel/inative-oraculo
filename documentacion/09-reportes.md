# 09 — Informes de conformidad

> `reportes/` + `internal/comparador/` — el oráculo no adivina: emite PASS/FAIL con divergencias auditables (plan §20).

## 9.1 Modelo

`internal/comparador/comparador.go`:

```go
type Divergencia struct{ Path, Esperado, Actual string } // Path dot-separated, ej. screens[0].fields[1].value
type Resultado struct{ Divergencias []Divergencia; PASS bool }
type Comparator struct{ comp fixture.ComparaSet; ignora []string }

func New(comp ComparaSet, ignore []string) *Comparator // normalizeIgnore lower+trim
func (c *Comparator) CompararSnapshots(esperados, actuales []DisplaySnapshot) Resultado
func (c *Comparator) esIgnorable(path string) bool // ignore substring match sobre path y segmentos
```

Aspectos comparados según `compare` (`ComparaSet`): `Screens/Fields/Cursor/Attributes/Indicators/ResponseKey + Display/Literals/Grid/Raw` — alias `Display:true → Screens+Fields+Literals+Grid`.

## 9.2 CLI Go

```bash
./binario/oraculo diff --fixture conformance/dspf/HELLO-5250-001.json \
  --expected esperado/HELLO-5250-001.json --actual /tmp/actual.json [--json]

# Pretty:
# PASS (0 divergencias)
# o
# FAIL
#   - screens[0].fields[2].value: esperado="1001" actual="0001"
#   - screens[0].literals[0].text: esperado="Cliente:" actual="Client:"
```

Con `--json` emite `Resultado` JSON para `reportes/`.

## 9.3 Reportes

`reportes/` guarda informes PASS/FAIL por corrida. No se versiona (generado). Cada informe referencia `fixture id + contrato_version + esperado vs actual + divergencias` — ver `reportes/README.md`.

## 9.4 Laxismos de comparación

- **Grid**: compara `text_grid` 24×80 exacto; tolera `rtrim` trailing si solo diff son espacios finales.
- **Color literales**: `green ↔ turquesa (0x20↔0x21)` se considera equivalente (evita falsos positivos PUB400 vs ACS 5250) a menos que `ignore` pida comparación estricta — `isGreenTurquoise()`.
- **Ignore**: cualquier entry `ig` en `ignore` hace match si `ig == path` o `strings.Contains(path, ig)` o coincide con un segmento — cubre `job.number`, `timestamp`, `display.literals[*].color` sin regex.

## 9.5 Suite de conformidad (plan §19)

`conformance/` organiza fixtures por familia de observables; `HELLO-5250-001` (§9.3) es el caso de referencia end-to-end. `make test` valida `comparador_test.go` y `display_test.go`.
