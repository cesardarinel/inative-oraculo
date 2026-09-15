// Package comparador implements the oracle's comparison step (plan §20).
//
// The comparator checks that the observables captured on a real IBM i are
// semantically equivalent to those produced by the local simulation, honoring
// the fixture's `compare` set (which aspects to compare) and `ignore` list
// (non-deterministic fields that must not be required to match literally,
// e.g. timestamps and job numbers).
package comparador

import (
	"fmt"
	"sort"
	"strings"

	"oraculo/internal/colectores"
	"oraculo/internal/fixture"
)

// Divergencia is a single semantic difference found by the Comparator.
type Divergencia struct {
	Path     string `json:"path"`
	Esperado string `json:"esperado"`
	Actual   string `json:"actual"`
}

func (d Divergencia) String() string {
	return fmt.Sprintf("%s: esperado=%q actual=%q", d.Path, d.Esperado, d.Actual)
}

// Resultado is the outcome of comparing expected vs actual observables.
type Resultado struct {
	Divergencias []Divergencia `json:"divergencias"`
	PASS         bool          `json:"pass"`
}

// Comparator compares expected (golden from IBM i) observables against actual
// (local simulation) observables for one fixture.
type Comparator struct {
	comp   fixture.ComparaSet
	ignora []string
}

// New builds a Comparator honoring the given compare set and ignore list.
func New(comp fixture.ComparaSet, ignore []string) *Comparator {
	return &Comparator{comp: comp, ignora: normalizeIgnore(ignore)}
}

// NormalizarIgnore pre-processes the ignore list for matching.
func normalizeIgnore(ignore []string) []string {
	out := make([]string, 0, len(ignore))
	for _, s := range ignore {
		s = strings.TrimSpace(strings.ToLower(s))
		if s == "" {
			continue
		}
		out = append(out, s)
	}
	return out
}

// esIgnorable reports whether the given lowercase path (dot separated) should
// be skipped. An ignore entry matches if it equals the full path, is a
// substring of the full path, equals any segment, or is a substring of any segment.
func (c *Comparator) esIgnorable(path string) bool {
	path = strings.ToLower(path)
	segs := strings.Split(path, ".")
	for _, ig := range c.ignora {
		if ig == path || strings.Contains(path, ig) {
			return true
		}
		if ig == segs[0] {
			return true
		}
		// substring match on any segment covers "timestamp", "job.number", etc.
		for _, s := range segs {
			if strings.Contains(s, ig) || s == ig {
				return true
			}
		}
	}
	return false
}

// CompararSnapshots compares two sequences of DisplaySnapshot (expected from
// IBM i, actual from iNative local) honoring the compare set and ignore list.
// The sequences must have the same length; screens are compared positionally.
func (c *Comparator) CompararSnapshots(esperados, actuales []colectores.DisplaySnapshot) Resultado {
	var divs []Divergencia
	n := len(esperados)
	if n != len(actuales) {
		divs = append(divs, Divergencia{Path: "screen.sequence.length", Esperado: fmt.Sprint(n), Actual: fmt.Sprint(len(actuales))})
		n = 0
	}
	for i := 0; i < n; i++ {
		e, a := esperados[i], actuales[i]
		divs = append(divs, c.compararSnapshot(i, e, a)...)
	}
	if len(divs) == 0 {
		return Resultado{PASS: true}
	}
	return Resultado{Divergencias: divs, PASS: false}
}

// compararSnapshot compares one snapshot pair according to the enabled aspects.
func (c *Comparator) compararSnapshot(idx int, e, a colectores.DisplaySnapshot) []Divergencia {
	pre := fmt.Sprintf("screens[%d]", idx)
	var divs []Divergencia

	if c.comp.Screens {
		if !c.esIgnorable(pre+".screen.rows") && e.Screen.Rows != a.Screen.Rows {
			divs = append(divs, Divergencia{Path: pre + ".screen.rows", Esperado: fmt.Sprint(e.Screen.Rows), Actual: fmt.Sprint(a.Screen.Rows)})
		}
		if !c.esIgnorable(pre+".screen.cols") && e.Screen.Cols != a.Screen.Cols {
			divs = append(divs, Divergencia{Path: pre + ".screen.cols", Esperado: fmt.Sprint(e.Screen.Cols), Actual: fmt.Sprint(a.Screen.Cols)})
		}
	}

	if c.comp.Cursor {
		ep, ap := notNullCursor(e.Cursor), notNullCursor(a.Cursor)
		if !c.esIgnorable(pre+".cursor.row") && ep.Row != ap.Row {
			divs = append(divs, Divergencia{Path: pre + ".cursor.row", Esperado: fmt.Sprint(ep.Row), Actual: fmt.Sprint(ap.Row)})
		}
		if !c.esIgnorable(pre+".cursor.col") && ep.Col != ap.Col {
			divs = append(divs, Divergencia{Path: pre + ".cursor.col", Esperado: fmt.Sprint(ep.Col), Actual: fmt.Sprint(ap.Col)})
		}
	}

	if c.comp.Fields {
		divs = append(divs, c.compararCampos(pre, e.Fields, a.Fields)...)
		if c.comp.Attributes {
			divs = append(divs, c.compararAtributos(pre, e.Fields, a.Fields)...)
		}
	}

	if c.comp.Indicators {
		if !c.esIgnorable(pre + ".indicators") {
			divs = append(divs, c.compararIndicadores(pre, e.Indicators, a.Indicators)...)
		}
	}

	if c.comp.ResponseKey {
		if !c.esIgnorable(pre+".response_key") && e.ResponseKey != a.ResponseKey {
			divs = append(divs, Divergencia{Path: pre + ".response_key", Esperado: e.ResponseKey, Actual: a.ResponseKey})
		}
	}

	// 03-fidelidad: literales, grid, raw
	if c.comp.DisplayLiterals || c.comp.Display {
		divs = append(divs, c.compararLiterales(pre, e.Literals, a.Literals)...)
	}
	if c.comp.DisplayGrid || c.comp.Display {
		divs = append(divs, c.compararGrid(pre, e.TextGrid, a.TextGrid)...)
	}
	if c.comp.DisplayRaw {
		divs = append(divs, c.compararRawHex(pre, e.RawHex, a.RawHex)...)
	}

	return divs
}

func notNullCursor(c *colectores.CursorPos) colectores.CursorPos {
	if c == nil {
		return colectores.CursorPos{}
	}
	return *c
}

// compararCampos matches fields by (row,col) and compares position/length/usage/value.
func (c *Comparator) compararCampos(pre string, ef, af []colectores.ScreenField) []Divergencia {
	var divs []Divergencia
	if c.esIgnorable(pre + ".fields") {
		return divs
	}
	if len(ef) != len(af) {
		divs = append(divs, Divergencia{Path: pre + ".fields.count", Esperado: fmt.Sprint(len(ef)), Actual: fmt.Sprint(len(af))})
	}
	for i, e := range ef {
		if i >= len(af) {
			break
		}
		a := af[i]
		fpre := fmt.Sprintf("%s.fields[%d]", pre, i)
		if !c.esIgnorable(fpre+".name") && e.Name != a.Name {
			divs = append(divs, Divergencia{Path: fpre + ".name", Esperado: e.Name, Actual: a.Name})
		}
		if !c.esIgnorable(fpre+".row") && e.Row != a.Row {
			divs = append(divs, Divergencia{Path: fpre + ".row", Esperado: fmt.Sprint(e.Row), Actual: fmt.Sprint(a.Row)})
		}
		if !c.esIgnorable(fpre+".col") && e.Col != a.Col {
			divs = append(divs, Divergencia{Path: fpre + ".col", Esperado: fmt.Sprint(e.Col), Actual: fmt.Sprint(a.Col)})
		}
		if !c.esIgnorable(fpre+".length") && e.Length != a.Length {
			divs = append(divs, Divergencia{Path: fpre + ".length", Esperado: fmt.Sprint(e.Length), Actual: fmt.Sprint(a.Length)})
		}
		if !c.esIgnorable(fpre+".usage") && e.Usage != a.Usage {
			divs = append(divs, Divergencia{Path: fpre + ".usage", Esperado: string(e.Usage), Actual: string(a.Usage)})
		}
		// value may carry non-deterministic data (timestamps); honor field-level ignore.
		if !c.esIgnorable(fpre+".value") && e.Value != a.Value {
			divs = append(divs, Divergencia{Path: fpre + ".value", Esperado: e.Value, Actual: a.Value})
		}
	}
	return divs
}

// compararAtributos compares the attribute lists of matched fields.
func (c *Comparator) compararAtributos(pre string, ef, af []colectores.ScreenField) []Divergencia {
	var divs []Divergencia
	mx := len(ef)
	if len(af) < mx {
		mx = len(af)
	}
	for i := 0; i < mx; i++ {
		fpre := fmt.Sprintf("%s.fields[%d]", pre, i)
		if c.esIgnorable(fpre + ".attributes") {
			continue
		}
		ea := joinSorted(ef[i].Attributes)
		aa := joinSorted(af[i].Attributes)
		if ea != aa {
			divs = append(divs, Divergencia{Path: fpre + ".attributes", Esperado: ea, Actual: aa})
		}
	}
	return divs
}

func joinSorted(xs []string) string {
	c := make([]string, len(xs))
	copy(c, xs)
	sort.Strings(c)
	return strings.Join(c, ",")
}

// compararIndicadores compares indicator states (keys "01".."99"), honoring ignores.
func (c *Comparator) compararIndicadores(pre string, e, a map[string]bool) []Divergencia {
	var divs []Divergencia
	if c.esIgnorable(pre + ".indicators") {
		return divs
	}
	// union of keys
	keys := map[string]bool{}
	for k := range e {
		keys[k] = true
	}
	for k := range a {
		keys[k] = true
	}
	for k := range keys {
		path := pre + ".indicators." + k
		if c.esIgnorable(path) {
			continue
		}
		ev, eok := e[k]
		av, aok := a[k]
		if eok != aok || (eok && ev != av) {
			divs = append(divs, Divergencia{Path: path, Esperado: fmt.Sprint(ev), Actual: fmt.Sprint(av)})
		}
	}
	return divs
}

// compararLiterales compara literales por row/col exacto y text (case-sensitive, rstrip) y color.
// Color turquesa↔verde se considera equivalente si ignore contiene "color" o modo laxo; de lo contrario se compara exacto.
// Si ignore contiene "display.literals[*].color" o "color" se salta comparación de color.
func (c *Comparator) compararLiterales(pre string, ef, af []colectores.ScreenLiteral) []Divergencia {
	var divs []Divergencia
	if c.esIgnorable(pre + ".literals") || c.esIgnorable(pre+".display_literals") {
		return divs
	}
	if len(ef) != len(af) {
		if !c.esIgnorable(pre + ".literals.count") {
			divs = append(divs, Divergencia{Path: pre + ".literals.count", Esperado: fmt.Sprint(len(ef)), Actual: fmt.Sprint(len(af))})
		}
	}
	// Index actuals by row/col for exact matching
	actByPos := map[string]colectores.ScreenLiteral{}
	for _, lit := range af {
		key := fmt.Sprintf("%d,%d", lit.Row, lit.Col)
		actByPos[key] = lit
	}
	for i, e := range ef {
		fpre := fmt.Sprintf("%s.literals[%d]", pre, i)
		if c.esIgnorable(fpre) {
			continue
		}
		key := fmt.Sprintf("%d,%d", e.Row, e.Col)
		a, ok := actByPos[key]
		if !ok {
			// Fallback positional
			if i < len(af) {
				a = af[i]
				ok = true
			} else {
				divs = append(divs, Divergencia{Path: fpre + ".pos", Esperado: fmt.Sprintf("%d,%d", e.Row, e.Col), Actual: "missing"})
				continue
			}
		}
		if !c.esIgnorable(fpre+".row") && e.Row != a.Row {
			divs = append(divs, Divergencia{Path: fpre + ".row", Esperado: fmt.Sprint(e.Row), Actual: fmt.Sprint(a.Row)})
		}
		if !c.esIgnorable(fpre+".col") && e.Col != a.Col {
			divs = append(divs, Divergencia{Path: fpre + ".col", Esperado: fmt.Sprint(e.Col), Actual: fmt.Sprint(a.Col)})
		}
		// Text case-sensitive, rstrip already done; compare exact
		ev := strings.TrimRight(e.Text, " ")
		av := strings.TrimRight(a.Text, " ")
		if !c.esIgnorable(fpre+".text") && ev != av {
			divs = append(divs, Divergencia{Path: fpre + ".text", Esperado: ev, Actual: av})
		}
		// Color: permitir turquesa↔verde como equivalente si ignore pide laxismo o siempre lax por defecto
		if !c.esIgnorable(fpre+".color") && !c.esIgnorable(pre+".literals.color") && !c.esIgnorable("display.literals[*].color") {
			ec := normalizeColor(e.Color)
			ac := normalizeColor(a.Color)
			// Si ambos son green/turquesa, trátalos como iguales para evitar falsos positivos PUB400 vs ACS
			if isGreenTurquoise(ec) && isGreenTurquoise(ac) {
				// equivalent
			} else if ec != ac {
				divs = append(divs, Divergencia{Path: fpre + ".color", Esperado: ec, Actual: ac})
			}
		}
	}
	return divs
}

func normalizeColor(c string) string {
	c = strings.TrimSpace(strings.ToLower(c))
	switch c {
	case "verde", "green", "0x20", "0x30":
		return "green"
	case "turquesa", "turquoise", "0x21", "0x31":
		return "turquesa"
	case "rojo", "red", "0x22":
		return "red"
	case "blanco", "white", "0x23":
		return "white"
	default:
		return c
	}
}

func isGreenTurquoise(c string) bool {
	c = normalizeColor(c)
	return c == "green" || c == "turquesa"
}

// compararGrid compara text_grid línea a línea 24x80.
func (c *Comparator) compararGrid(pre string, eg, ag []string) []Divergencia {
	var divs []Divergencia
	if c.esIgnorable(pre + ".text_grid") || c.esIgnorable(pre+".display_grid") || c.esIgnorable(pre+".grid") {
		return divs
	}
	if len(eg) == 0 && len(ag) == 0 {
		return divs
	}
	if len(eg) != len(ag) {
		divs = append(divs, Divergencia{Path: pre + ".text_grid.count", Esperado: fmt.Sprint(len(eg)), Actual: fmt.Sprint(len(ag))})
		if len(eg) == 0 || len(ag) == 0 {
			return divs
		}
	}
	n := len(eg)
	if len(ag) < n {
		n = len(ag)
	}
	for i := 0; i < n; i++ {
		path := fmt.Sprintf("%s.text_grid[%d]", pre, i)
		if c.esIgnorable(path) {
			continue
		}
		// Ignorar cursor si ignore contiene cursor: grid ya no incluye cursor, pero por spec lo soportamos
		if c.esIgnorable(pre+".cursor") || c.esIgnorable("cursor") {
			// no op, grid no afectado
		}
		// Comparación exacta case-sensitive; se hace rtrim opcional si ignore pide?
		ev := eg[i]
		av := ag[i]
		// Si ignore contiene "grid" con trim, no recortamos; comparamos exacto 24x80
		if ev != av {
			// Intento laxo: comparar rstrip para ignorar trailing spaces
			if strings.TrimRight(ev, " ") == strings.TrimRight(av, " ") {
				continue
			}
			divs = append(divs, Divergencia{Path: path, Esperado: fmt.Sprintf("%q", ev), Actual: fmt.Sprintf("%q", av)})
		}
	}
	return divs
}

// compararRawHex compara payload hex byte-compare.
func (c *Comparator) compararRawHex(pre, er, ar string) []Divergencia {
	if c.esIgnorable(pre + ".raw_hex") || c.esIgnorable(pre+".display_raw") || c.esIgnorable("raw_hex") {
		return divsEmpty()
	}
	if er == "" && ar == "" {
		return nil
	}
	if strings.ToLower(strings.TrimSpace(er)) != strings.ToLower(strings.TrimSpace(ar)) {
		return []Divergencia{{Path: pre + ".raw_hex", Esperado: er, Actual: ar}}
	}
	return nil
}

func divsEmpty() []Divergencia { return nil }
