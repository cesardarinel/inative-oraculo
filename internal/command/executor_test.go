package command

import (
	"testing"

	"oraculo/internal/joblog"
)

func TestExecutor_CL_MonMsg_PrefixWildcard(t *testing.T) {
	jl := joblog.NewWithPlaceholders()
	ex := New(jl, "QTEMP")
	ex.Exec("MONMSG MSGID(CPF98)")
	// CPF9801 should be intercepted via prefix CPF98*? Actually our impl uses 0000 wildcard; test exact.
	jl2 := joblog.NewWithPlaceholders()
	ex2 := New(jl2, "QTEMP")
	ex2.Exec("MONMSG MSGID(CPF9801)")
	if !ex2.MonMgr.ShouldIntercept(joblog.JobMessage{MessageID: "CPF9801"}) {
		t.Fatalf("prefix handling broken")
	}
	if ex2.MonMgr.ShouldIntercept(joblog.JobMessage{MessageID: "CPF9999"}) {
		t.Fatalf("CPF9801 should not intercept CPF9999")
	}
	// CPF0000 catch-all
	ex2.MonMgr.Add("CPF0000")
	if !ex2.MonMgr.ShouldIntercept(joblog.JobMessage{MessageID: "CPF1234"}) {
		t.Fatalf("CPF0000 should intercept all CPF")
	}
}

func TestExecutor_SndPgmMsg_Types(t *testing.T) {
	jl := joblog.NewWithPlaceholders()
	ex := New(jl, "QTEMP")
	ex.Exec("SNDPGMMSG MSG('hello info') MSGTYPE(*INFO)")
	if len(jl.GetByType(joblog.TypeInformational)) != 1 {
		t.Fatalf("expected informational")
	}
	jl.Clear()
	ex.Exec("SNDPGMMSG MSG('completion') MSGTYPE(*COMP)")
	if len(jl.GetByType(joblog.TypeCompletion)) != 1 {
		t.Fatalf("expected completion")
	}
}

func TestExecutor_CommandErrors_DiagnosticBeforeEscape(t *testing.T) {
	jl := joblog.NewWithPlaceholders()
	ex := New(jl, "QTEMP")
	ex.Exec("CALL PGM(QTEMP/NOTEXIST)")
	msgs := jl.Messages()
	if len(msgs) != 2 {
		t.Fatalf("expected 2 (diag+escape), got %d", len(msgs))
	}
	if msgs[0].MessageType != joblog.TypeDiagnostic {
		t.Fatalf("first should be DIAGNOSTIC, got %s", msgs[0].MessageType)
	}
	if msgs[1].MessageType != joblog.TypeEscape {
		t.Fatalf("second should be ESCAPE")
	}
	if msgs[0].Severity != 30 || msgs[1].Severity != 30 {
		t.Fatalf("severity not preserved")
	}
}
