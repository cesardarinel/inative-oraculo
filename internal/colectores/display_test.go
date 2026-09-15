package colectores

import "testing"

func TestObservableDisplayContract(t *testing.T) {
	o := NewDisplayObservable("HELLO-5250-001#1")
	if o.Kind != KindDisplay {
		t.Fatalf("kind = %q, esperado %q", o.Kind, KindDisplay)
	}
	if o.Name != "HELLO-5250-001#1" {
		t.Fatalf("name inesperado: %q", o.Name)
	}
}

func TestFieldUsageValues(t *testing.T) {
	cases := map[FieldUsage]string{
		FieldUsageInput:  "input",
		FieldUsageOutput: "output",
		FieldUsageBoth:   "both",
		FieldUsageHidden: "hidden",
	}
	for u, want := range cases {
		if string(u) != want {
			t.Fatalf("%s != %s", u, want)
		}
	}
}
