package normalizador

import (
	"strings"
	"testing"

	"oraculo/internal/colectores"
)

func TestSerializarDisplayDeterminista(t *testing.T) {
	sn := colectores.DisplaySnapshot{
		Screen: colectores.ScreenSize{Rows: 24, Cols: 80},
		Cursor: &colectores.CursorPos{Row: 6, Col: 21},
		Fields: []colectores.ScreenField{
			{Name: "CUSTOMER_ID", Row: 5, Col: 20, Length: 10, Usage: colectores.FieldUsageInput, Value: "1001"},
		},
		Indicators:  map[string]bool{"01": false, "03": true},
		ResponseKey: "ENTER",
	}
	a := SerializarDisplay(sn)
	b := SerializarDisplay(sn)
	if a != b {
		t.Fatalf("serialización no determinista:\n%s\n%s", a, b)
	}
	if !strings.Contains(a, `"rows":24`) {
		t.Fatalf("faltan rows en serialización: %s", a)
	}
	if !strings.Contains(a, `"response_key":"ENTER"`) {
		t.Fatalf("falta response_key en serialización: %s", a)
	}
}
