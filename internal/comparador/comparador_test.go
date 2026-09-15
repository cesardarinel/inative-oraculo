package comparador

import (
	"testing"

	"oraculo/internal/colectores"
	"oraculo/internal/fixture"
)

func snap() []colectores.DisplaySnapshot {
	return []colectores.DisplaySnapshot{
		{
			Screen: colectores.ScreenSize{Rows: 24, Cols: 80},
			Cursor: &colectores.CursorPos{Row: 6, Col: 21},
			Fields: []colectores.ScreenField{
				{Name: "CUSTOMER_ID", Row: 5, Col: 20, Length: 10, Usage: colectores.FieldUsageInput, Value: "1001"},
			},
			Indicators:  map[string]bool{"01": false, "03": true},
			ResponseKey: "ENTER",
		},
	}
}

// fullComp enables all comparison aspects.
func fullComp() fixture.ComparaSet {
	return fixture.ComparaSet{
		Screens: true, Fields: true, Cursor: true, Attributes: true,
		Indicators: true, ResponseKey: true,
	}
}

func TestCompararSnapshotsPASS(t *testing.T) {
	e := snap()
	a := snap()
	res := New(fullComp(), nil).CompararSnapshots(e, a)
	if !res.PASS {
		t.Fatalf("esperado PASS, got %+v", res.Divergencias)
	}
	if len(res.Divergencias) != 0 {
		t.Fatalf("no divergencias esperadas, got %+v", res.Divergencias)
	}
}

func TestCampoValueIguado(t *testing.T) {
	e := snap()
	a := snap()
	a[0].Fields[0].Value = "9999"
	res := New(fullComp(), nil).CompararSnapshots(e, a)
	if res.PASS {
		t.Fatal("PASS inesperado con valor de campo distinto")
	}
	if len(res.Divergencias) != 1 || res.Divergencias[0].Path != "screens[0].fields[0].value" {
		t.Fatalf("divergencia inesperada: %+v", res.Divergencias)
	}
}

func TestCampoValueIgnorado(t *testing.T) {
	e := snap()
	a := snap()
	a[0].Fields[0].Value = "9999"
	res := New(fullComp(), []string{"value"}).CompararSnapshots(e, a)
	if !res.PASS {
		t.Fatalf("esperado PASS con value ignorado, got %+v", res.Divergencias)
	}
}

func TestLongitudSecuencia(t *testing.T) {
	e := snap()
	a := snap()[:0]
	res := New(fullComp(), nil).CompararSnapshots(e, a)
	if res.PASS {
		t.Fatal("PASS inesperado con longitudes distintas")
	}
	if len(res.Divergencias) != 1 || res.Divergencias[0].Path != "screen.sequence.length" {
		t.Fatalf("divergencia inesperada: %+v", res.Divergencias)
	}
}

func TestIndicadorDiferente(t *testing.T) {
	e := snap()
	a := snap()
	a[0].Indicators["03"] = false
	res := New(fullComp(), nil).CompararSnapshots(e, a)
	if res.PASS {
		t.Fatal("PASS inesperado con indicador distinto")
	}
	found := false
	for _, d := range res.Divergencias {
		if d.Path == "screens[0].indicators.03" {
			found = true
		}
	}
	if !found {
		t.Fatalf("no se reportó indicador distinto: %+v", res.Divergencias)
	}
}

func TestResponseKey(t *testing.T) {
	e := snap()
	a := snap()
	a[0].ResponseKey = "F3"
	res := New(fullComp(), nil).CompararSnapshots(e, a)
	if res.PASS {
		t.Fatal("PASS inesperado con response_key distinto")
	}
}

func TestCompareSetDesactivaAspectos(t *testing.T) {
	e := snap()
	a := snap()
	a[0].ResponseKey = "F3"
	a[0].Cursor.Row = 99
	// apenas ResponseKey activo -> el cursor distinto no debe reportarse.
	c := fixture.ComparaSet{ResponseKey: true}
	res := New(c, nil).CompararSnapshots(e, a)
	if res.PASS {
		t.Fatal("PASS inesperado: response_key debió fallar")
	}
	for _, d := range res.Divergencias {
		if d.Path == "screens[0].cursor.row" {
			t.Fatalf("cursor no debía compararse: %+v", d)
		}
	}
}

func TestEsIgnorable(t *testing.T) {
	c := New(fullComp(), []string{"job.number", "timestamp"})
	if !c.esIgnorable("screens[0].fields[0].timestamp") {
		t.Fatal("timestamp no ignorado")
	}
	if !c.esIgnorable("job.number") {
		t.Fatal("job.number no ignorado")
	}
	if c.esIgnorable("screens[0].fields[0].value") {
		t.Fatal("value no debía ignorarse")
	}
}
