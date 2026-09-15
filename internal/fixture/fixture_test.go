package fixture

import "testing"

func TestFixtureJSONRoundTrip(t *testing.T) {
	f := Fixture{
		ID:   "HELLO-5250-001",
		Name: "Pantalla básica equivalente en IBM i e iNative",
		Source: Source{
			RPGLE: "./src/HELLO.rpgle",
			DSPF:  "./src/HELLO.dspf",
		},
		Input: []InputAction{
			{Type: "text", Field: "CUSTOMER_ID", Value: "1001"},
			{Type: "key", Value: "ENTER"},
			{Type: "key", Value: "F3"},
		},
		Compare: ComparaSet{
			Screens: true, Fields: true, Cursor: true,
			Attributes: true, Indicators: true, ResponseKey: true,
		},
		Ignore: []string{"job.number", "timestamp"},
	}
	data, err := Marshal(f)
	if err != nil {
		t.Fatal(err)
	}
	back, err := Load(data)
	if err != nil {
		t.Fatal(err)
	}
	if back.ID != f.ID || len(back.Input) != 3 || len(back.Ignore) != 2 {
		t.Fatalf("round-trip inconsistente: %+v", back)
	}
	if !back.Compare.Alpha() {
		t.Fatal("ComparaSet debería estar activo tras round-trip")
	}
}
