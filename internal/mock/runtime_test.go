package mock

import (
	"testing"

	"oraculo/internal/command"
	"oraculo/internal/filehandle"
	"oraculo/internal/joblog"
)

func TestMockRuntime_ReplayDeterministic(t *testing.T) {
	rt := NewRuntime("../../inative-mock-data/normalized")
	if rt.Corpus.Root == "" {
		rt.Corpus.Root = "../../inative-mock-data/normalized"
	}
	if err := rt.ReplayFixture("RPG-RUNTIME-001"); err != nil {
		// fallback to fixtures path for CI where inative-mock-data may be absent
		rt.Corpus.Root = "../../fixtures/joblog/normalized"
		if err2 := rt.ReplayFixture("RPG-RUNTIME-001"); err2 != nil {
			t.Fatalf("replay: %v / %v", err, err2)
		}
	}
	msgs := rt.Log.Messages()
	if len(msgs) != 3 {
		t.Fatalf("expected 3 msgs from corpus, got %d", len(msgs))
	}
	if msgs[0].MessageID != "RNQ0100" || msgs[0].MessageType != joblog.TypeEscape {
		t.Fatalf("first msg wrong: %+v", msgs[0])
	}
	// Re-replay must be deterministic (same order, same second-level)
	rt2 := NewRuntime("")
	_ = rt2.ReplayFixture("RPG-RUNTIME-001")
	if d := joblog.AssertEqual(msgs, rt2.Log.Messages()); len(d) > 0 {
		t.Fatalf("deterministic replay failed: %v", d)
	}
}

func TestMockRuntime_MonMsgHandlesEscape(t *testing.T) {
	jl := joblog.NewWithPlaceholders()
	exec := command.New(jl, "QTEMP")
	// MONMSG CPF0000 catch-all must intercept full diagnostic → escape chain (§11)
	// Using CPF9801 alone would leave CPF0006 escape unhandled — so we test catch-all semantics.
	exec.Exec("MONMSG MSGID(CPF0000)")
	ok, _ := exec.Exec("CALL PGM(QTEMP/NOTEXIST)")
	if !ok {
		t.Fatalf("MONMSG CPF0000 should have handled entire chain, but Exec reported failure")
	}
	// JobLog must still contain messages (MONMSG does not erase log, just prevents Escape propagation)
	if len(jl.Messages()) < 2 {
		t.Fatalf("expected at least 2 messages after MONMSG, got %d: %+v", len(jl.Messages()), jl.Messages())
	}
	// Verify prefix wildcard: MONMSG CPF98* handles CPF9801
	jl2 := joblog.NewWithPlaceholders()
	exec2 := command.New(jl2, "QTEMP")
	exec2.Exec("MONMSG MSGID(CPF9801)")
	// Diagnostic CPF9801 should be intercepted; CPF0006 still escapes without second MONMSG
	ok2, _ := exec2.Exec("CALL PGM(QTEMP/NOTEXIST)")
	if ok2 {
		t.Fatalf("MONMSG CPF9801 alone should NOT fully handle CPF0006 escape chain — expected failure")
	}
}

func TestMockRuntime_FileHandle_Chain_NotFound_LogsDiagnosticChain(t *testing.T) {
	jl := joblog.NewWithPlaceholders()
	h := filehandle.New("MYFILE", "QTEMP", jl)
	st := h.Chain("NOKEY")
	if st.Found {
		t.Fatalf("expected not found")
	}
	if !h.Indicators["90"] {
		t.Fatalf("expected IN90 set on not-found")
	}
	msgs := jl.Messages()
	if len(msgs) != 2 {
		t.Fatalf("expected 2 diagnostic chain msgs, got %d", len(msgs))
	}
	if msgs[0].MessageID != "RNX1221" {
		t.Fatalf("first should be RNX1221, got %s", msgs[0].MessageID)
	}
}

func TestMockRuntime_FileHandle_EOF_SetsIndicator(t *testing.T) {
	jl := joblog.NewWithPlaceholders()
	h := filehandle.New("MYFILE", "QTEMP", jl)
	h.ResetRecords("A")
	h.Chain("A") // prime found
	_ = h.Read()  // first read success
	st2 := h.Read() // second read -> EOF per mock sequencing
	if !st2.EOF {
		t.Fatalf("expected EOF on second read, got %+v", st2)
	}
	if !h.Indicators["90"] {
		t.Fatalf("EOF indicator not set")
	}
}

func TestMockRuntime_VSCodeResponse_Compatible(t *testing.T) {
	rt := NewRuntime("../../inative-mock-data/normalized")
	_ = rt.ReplayFixture("MSG-SNDPGMMSG-001")
	if len(rt.Log.Messages()) == 0 {
		rt.Corpus.Root = "../../fixtures/joblog/normalized"
		_ = rt.ReplayFixture("MSG-SNDPGMMSG-001")
	}
	resp := rt.VSCodeResponse()
	if resp["jobLog"] == nil {
		t.Fatalf("VSCode response missing jobLog")
	}
	jl, ok := resp["jobLog"].([]map[string]interface{})
	if !ok || len(jl) != 1 {
		t.Fatalf("expected 1 jobLog entry, got %+v", resp["jobLog"])
	}
	if jl[0]["messageId"] != "CPF9897" {
		t.Fatalf("wrong messageId in VSCode response")
	}
}


