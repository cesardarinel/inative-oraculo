// Package fixture models the versioned fixture schema that iNative publishes
// to the oracle (plan §20 "Modelo de comparación Local vs IBM i real").
//
// A fixture carries the source, the input script, the set of observable
// aspects to compare and the list of non-deterministic fields to ignore.
package fixture

import "encoding/json"

// Source references the source members of the fixture (RPGLE/CL/DSPF/PF/LF).
type Source struct {
	RPGLE string            `json:"rpgle,omitempty"`
	CL    string            `json:"cl,omitempty"`
	DSPF  string            `json:"dspf,omitempty"`
	PF    string            `json:"pf,omitempty"`
	LF    string            `json:"lf,omitempty"`
	Other map[string]string `json:"other,omitempty"`
}

// InputAction is one step of a scripted input sequence (keyboard/field entry).
type InputAction struct {
	Type  string `json:"type"`            // "text"|"key"|"field"|"command"|"wait"
	Field string `json:"field,omitempty"` // destination field for "text"/"field"
	Value string `json:"value"`           // field value, or key name ("ENTER","F3",...), or CL command
}

// ComparaSet declares which observable aspects must be compared. Aspects not
// present in this set (or false) are excluded from the comparison.
type ComparaSet struct {
	Screens         bool `json:"screens,omitempty"`
	Fields          bool `json:"fields,omitempty"`
	Cursor          bool `json:"cursor,omitempty"`
	Attributes      bool `json:"attributes,omitempty"`
	Indicators      bool `json:"indicators,omitempty"`
	ResponseKey     bool `json:"response_key,omitempty"`
	Display         bool `json:"display,omitempty"`
	DisplayLiterals bool `json:"display_literals,omitempty"`
	DisplayGrid     bool `json:"display_grid,omitempty"`
	DisplayRaw      bool `json:"display_raw,omitempty"`
}

// UnmarshalJSON allows alias compare keys (display true → screens+fields+literals+grid).
func (c *ComparaSet) UnmarshalJSON(data []byte) error {
	type raw ComparaSet
	var r raw
	if err := json.Unmarshal(data, (*raw)(&r)); err != nil {
		return err
	}
	*c = ComparaSet(r)
	// Aliases: "display": true habilita screens+fields+lits+grid para compat 03-fidelidad
	if c.Display {
		c.Screens = true
		c.Fields = true
		c.DisplayLiterals = true
		c.DisplayGrid = true
	}
	return nil
}

// AlphaSet returns true if any of the requested aspects is enabled.
func (c ComparaSet) Alpha() bool {
	return c.Screens || c.Fields || c.Cursor || c.Attributes || c.Indicators || c.ResponseKey || c.Display || c.DisplayLiterals || c.DisplayGrid || c.DisplayRaw
}

// Fixture is the versioned contract published by iNative.
type Fixture struct {
	ID        string        `json:"id"`
	Name      string        `json:"name,omitempty"`
	Source    Source        `json:"source,omitempty"`
	Setup     []InputAction `json:"setup,omitempty"`
	Input     []InputAction `json:"input,omitempty"`
	Compare   ComparaSet    `json:"compare,omitempty"`
	Ignore    []string      `json:"ignore,omitempty"`
	Transport string        `json:"transport,omitempty"` // auto|ssh|5250
	Timeout   int           `json:"timeout,omitempty"`
	DB        *DBSpec       `json:"db,omitempty"`
}

// DBSpec declares tables to capture for the db observable.
type DBSpec struct {
	Tables []string `json:"tables,omitempty"`
	Tablas []string `json:"tablas,omitempty"`
}
