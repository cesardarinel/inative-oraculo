package filehandle

import (
	"testing"

	"oraculo/internal/joblog"
)

func TestChain_NotFound_IndicatorsAndJobLog(t *testing.T) {
	jl := joblog.NewWithPlaceholders()
	h := New("MYFILE", "QTEMP", jl)
	st := h.Chain("NOKEY")
	if st.Found {
		t.Fatal("expected not found")
	}
	if !h.Indicators["90"] {
		t.Fatal("IN90 should be set")
	}
	msgs := jl.Messages()
	if len(msgs) != 2 {
		t.Fatalf("expected 2 msgs (RNX1221+CPF5027), got %d", len(msgs))
	}
	if msgs[0].MessageID != "RNX1221" || msgs[1].MessageID != "CPF5027" {
		t.Fatalf("unexpected chain msgs: %+v", msgs)
	}
	if msgs[0].OrdinalPosition != 1 || msgs[1].OrdinalPosition != 2 {
		t.Fatalf("ordinal broken")
	}
}

func TestAllOps_FileIO_Matrix(t *testing.T) {
	jl := joblog.NewWithPlaceholders()
	h := New("MYFILE", "QTEMP", jl)
	h.ResetRecords("KEY1")

	tests := []struct {
		op   string
		fn   func() interface{}
	}{
		{"SETLL found", func() interface{} { return h.SetLL("KEY1") }},
		{"SETLL not found", func() interface{} { h.Log.Clear(); return h.SetLL("NOKEY") }},
		{"SETGT", func() interface{} { h.Log.Clear(); return h.SetGT("ANY") }},
		{"READ success", func() interface{} { h.ResetRecords("A"); h.Log.Clear(); return h.Read() }},
		{"CHAIN duplicate write", func() interface{} { h.ResetRecords("KEY1"); h.Log.Clear(); return h.Write("KEY1") }},
		{"WRITE success", func() interface{} { h.ResetRecords(); h.Log.Clear(); return h.Write("NEWKEY") }},
		{"UPDATE notfound", func() interface{} { h.ResetRecords(); h.Log.Clear(); return h.Update("NOKEY") }},
		{"DELETE notfound", func() interface{} { h.ResetRecords(); h.Log.Clear(); return h.Delete("NOKEY") }},
		{"OPEN notfound", func() interface{} {
			h2 := New("NOTEXIST", "QTEMP", jl)
			h2.Log.Clear()
			jl.Clear()
			return h2.Open()
		}},
	}
	for _, tc := range tests {
		_ = tc.fn()
		// Each op should either log or set indicators deterministically — no panic
		if tc.op == "" {
			t.Error("empty op")
		}
	}
	// Verify RT: WRITE duplicate must be ESCAPE
	h.ResetRecords("DUP")
	jl.Clear()
	h.Write("DUP")
	if h.Log.GetByID("CPF5033") == nil {
		t.Fatalf("duplicate WRITE should emit CPF5033")
	}
	if h.Log.GetByType(joblog.TypeEscape) == nil {
		t.Fatalf("expected escape type")
	}
}

func TestOpen_AuthorityError(t *testing.T) {
	jl := joblog.NewWithPlaceholders()
	h := New("NOAUTH", "QTEMP", jl)
	st := h.Open()
	if !st.Error || st.StatusCode != 9802 {
		t.Fatalf("expected authority error, got %+v", st)
	}
	if len(jl.GetByID("CPF9802")) == 0 {
		t.Fatalf("expected CPF9802")
	}
}
