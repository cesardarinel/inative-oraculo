// Package normalizador normalizes raw observables collected from real IBM i
// so they can be compared deterministically with the local simulation output.
//
// Normalization removes line/column or trailing-whitespace differences that do
// not carry semantic meaning, keeping family + id + text and typed values.
package normalizador

import (
	"bytes"
	"encoding/json"

	"oraculo/internal/colectores"
)

// Normalizado is a normalized observable ready for comparison.
type Normalizado struct {
	Kind  string
	Name  string
	Value string
	Norm  string // normalized representation used for comparison
}

// Normalizador transforms raw observables into a comparable form.
type Normalizador interface {
	Normalizar(observables []any) ([]Normalizado, error)
}

// SerializarDisplay produces a deterministic, stable textual serialization of
// a DisplaySnapshot (plan §9.2). This is the `Value` carried by observables of
// kind `display`. It is canonical: the same snapshot always yields the same
// string, independent of map ordering.
func SerializarDisplay(sn colectores.DisplaySnapshot) string {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	_ = enc.Encode(sn)
	return buf.String()
}
