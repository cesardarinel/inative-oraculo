package comparador

import (
	"encoding/json"
	"os"

	"oraculo/internal/colectores"
)

// LeerSnapshots lee snapshots desde un archivo. Soporta tres formatos:
//  1. []DisplaySnapshot directo
//  2. { observables: [{kind:"display", value:{screen,...}}] } (esperado/actual oráculo)
//  3. { value: {screen,...} } observable único
func LeerSnapshots(path string) ([]colectores.DisplaySnapshot, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	// Intento 1: array directo
	var out []colectores.DisplaySnapshot
	if err := json.Unmarshal(data, &out); err == nil && len(out) > 0 {
		return out, nil
	}
	// Intento 2: wrapper oráculo con observables
	var wrapper struct {
		Observables []struct {
			Kind  string          `json:"kind"`
			Value json.RawMessage `json:"value"`
		} `json:"observables"`
	}
	if err := json.Unmarshal(data, &wrapper); err == nil && len(wrapper.Observables) > 0 {
		var snaps []colectores.DisplaySnapshot
		for _, o := range wrapper.Observables {
			if o.Kind != "display" && o.Kind != "" {
				continue
			}
			var s colectores.DisplaySnapshot
			if err := json.Unmarshal(o.Value, &s); err == nil {
				// s puede venir con wrapper {screen,cursor,fields,...} o ya es DisplaySnapshot
				// Si Screen es cero, intenta deserializar interno
				if s.Screen.Rows == 0 && s.Screen.Cols == 0 {
					continue
				}
				snaps = append(snaps, s)
			}
		}
		if len(snaps) > 0 {
			return snaps, nil
		}
	}
	// Si no se pudo, retorna array vacío sin error para no bloquear diff de no-display
	if err := json.Unmarshal(data, &out); err == nil {
		return out, nil
	}
	return nil, err
}
