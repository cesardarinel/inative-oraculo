// Package colectores sub-package: display branding.
//
// DisplaySnapshot models a screen in a transport-independent way (plan §9.2,
// §18). It is the sole contract used to compare a DSPF/5250 screen between
// iNative (local) and a real IBM i. The comparison is done against this
// semantic model, not against pixels.
package colectores

// DisplaySnapshot is the normalized, comparable representation of one screen.
// Exact schema per plan §9.2 ("Cómo comparar la pantalla sin depender de un
// screenshot"). Fields that are inherently non-deterministic (timestamps, job
// numbers) live outside the semantic comparison and are handled via the
// fixture `ignore` list (see internal/fixture and internal/comparador).
//
// Extended 03-fidelidad: literals, text_grid, attr_grid, raw_hex (TN5250).
type DisplaySnapshot struct {
	Screen      ScreenSize      `json:"screen"`
	Cursor      *CursorPos      `json:"cursor,omitempty"`
	Fields      []ScreenField   `json:"fields"`
	Literals    []ScreenLiteral `json:"literals,omitempty"`
	TextGrid    []string        `json:"text_grid,omitempty"`
	AttrGrid    [][]CellAttr    `json:"attr_grid,omitempty"`
	RawHex      string          `json:"raw_hex,omitempty"`
	Indicators  map[string]bool `json:"indicators,omitempty"`
	ResponseKey string          `json:"response_key,omitempty"`
}

// ScreenLiteral is fixed text outside fields (03-fidelidad).
type ScreenLiteral struct {
	Row   int    `json:"row"`
	Col   int    `json:"col"`
	Text  string `json:"text"`
	Color string `json:"color,omitempty"`
	Attr  int    `json:"attr,omitempty"`
}

// CellAttr is per-cell display attribute (color/hi/ul/protected).
type CellAttr struct {
	Color     string `json:"color,omitempty"`
	Hi        bool   `json:"hi,omitempty"`
	Ul        bool   `json:"ul,omitempty"`
	Protected bool   `json:"protected,omitempty"`
}

// ScreenSize defines the terminal dimensions of the snapshot.
type ScreenSize struct {
	Rows int `json:"rows"`
	Cols int `json:"cols"`
}

// CursorPos is the cursor position within the screen.
type CursorPos struct {
	Row int `json:"row"`
	Col int `json:"col"`
}

// FieldUsage enumerates the I/O usage of a screen field.
type FieldUsage string

const (
	FieldUsageInput  FieldUsage = "input"
	FieldUsageOutput FieldUsage = "output"
	FieldUsageBoth   FieldUsage = "both"
	FieldUsageHidden FieldUsage = "hidden"
)

// ScreenField is a single field of the screen.
type ScreenField struct {
	Name       string     `json:"name,omitempty"`
	Row        int        `json:"row"`
	Col        int        `json:"col,omitempty"`
	Length     int        `json:"length"`
	Usage      FieldUsage `json:"usage,omitempty"`
	Value      string     `json:"value,omitempty"`
	Attributes []string   `json:"attributes,omitempty"`
}

// NewDisplayKind constructs an observable of kind `display` whose Name is the
// logical screen/case identifier and whose Value is a stable serialization of
// the DisplaySnapshot (produced by the normalizer; never raw struct bytes).
func NewDisplayObservable(name string) Observable {
	return Observable{
		Kind: KindDisplay,
		Name: name,
	}
}
