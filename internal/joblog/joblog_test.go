package joblog

import (
	"testing"
)

// ---------------------------------------------------------------------------
// Engine tests (§22)
// ---------------------------------------------------------------------------

func TestJobLogEngine_AddAndOrder(t *testing.T) {
	ctx := PlaceholderJobContext()
	jl := New(ctx)
	jl.AddDiagnostic("CPD0000", 10, "Diagnostic before escape")
	jl.AddEscape("CPF0006", 30, "Errors occurred in command.")

	msgs := jl.Messages()
	if len(msgs) != 2 {
		t.Fatalf("expected 2 messages, got %d", len(msgs))
	}
	if msgs[0].OrdinalPosition != 1 || msgs[1].OrdinalPosition != 2 {
		t.Fatalf("ordinal not preserved: %v", msgs)
	}
	if msgs[1].MessageType != TypeEscape {
		t.Fatalf("expected ESCAPE, got %s", msgs[1].MessageType)
	}
}

func TestJobLogEngine_GetBySeverity(t *testing.T) {
	jl := NewWithPlaceholders()
	jl.AddInformational("CPF9897", 0, "hello")
	jl.AddDiagnostic("CPF9801", 30, "not found")
	jl.AddEscape("CPF0006", 30, "failed")
	if len(jl.GetBySeverity(30)) != 2 {
		t.Fatalf("severity filter failed")
	}
	if len(jl.GetByID("CPF9897")) != 1 {
		t.Fatalf("GetByID failed")
	}
}

func TestDiff_PreservesOrder(t *testing.T) {
	before := []JobMessage{
		{MessageID: "CPF0001", MessageText: "start", OrdinalPosition: 1},
	}
	after := []JobMessage{
		{MessageID: "CPF0001", MessageText: "start", OrdinalPosition: 1},
		{MessageID: "CPF9801", MessageType: TypeDiagnostic, MessageText: "Object NOTEXIST not found", OrdinalPosition: 2},
		{MessageID: "CPF0006", MessageType: TypeEscape, MessageText: "Errors occurred", OrdinalPosition: 3},
	}
	delta := Diff(before, after)
	if len(delta) != 2 {
		t.Fatalf("expected delta 2, got %d", len(delta))
	}
	if delta[0].MessageID != "CPF9801" || delta[1].MessageID != "CPF0006" {
		t.Fatalf("delta order broken: %v", delta)
	}
}

func TestNormalize_StripsDynamic(t *testing.T) {
	msgs := []JobMessage{
		{MessageID: "CPF0001", MessageText: "  hello   world  ", JobName: "123456/USER/JOB", MessageKey: "ABC", Severity: 0},
	}
	norm := Normalize(msgs)
	if norm[0].JobName != "${JOB_NAME}" {
		t.Fatalf("dynamic not replaced")
	}
	if norm[0].MessageText != "hello world" {
		t.Fatalf("text not collapsed: %q", norm[0].MessageText)
	}
}

// ---------------------------------------------------------------------------
// Fixture contract tests (§19) — deterministic replay against normalized fixtures
// ---------------------------------------------------------------------------

func TestContract_RPG_Runtime_DivideByZero(t *testing.T) {
	fix, err := LoadFixture("../../fixtures/joblog/normalized/RPG-RUNTIME-001.json")
	if err != nil {
		t.Fatalf("load fixture: %v", err)
	}
	// Simulate iNative runtime reproducing the same messages
	ctx := PlaceholderJobContext()
	jl := New(ctx)
	for _, m := range fix.JobLog.Messages {
		jl.Add(JobMessage{
			MessageID:                m.MessageID,
			MessageType:              m.MessageType,
			Severity:                 m.Severity,
			MessageText:              m.MessageText,
			MessageSecondLevelText:   m.MessageSecondLevelText,
			OrdinalPosition:          m.OrdinalPosition,
		})
	}
	expected := fix.JobLog.Messages
	actual := jl.Messages()
	if diffs := AssertEqual(expected, actual); len(diffs) > 0 {
		t.Fatalf("contract failed:\n%v", diffs)
	}
}

func TestContract_CMD_ObjectNotFound(t *testing.T) {
	fix, err := LoadFixture("../../fixtures/joblog/normalized/CMD-ERR-002.json")
	if err != nil {
		t.Fatalf("load fixture: %v", err)
	}
	jl := NewWithPlaceholders()
	// Simulate diagnostic → escape chain (order matters §13)
	jl.AddDiagnostic("CPF9801", 30, "Object NOTEXIST in library QTEMP not found.")
	jl.AddEscape("CPF0006", 30, "Errors occurred in command.")

	if diffs := AssertEqual(fix.JobLog.Messages, jl.Messages()); len(diffs) > 0 {
		t.Fatalf("CMD-ERR-002 contract failed: %v", diffs)
	}
}

func TestContract_MessageOrdering_IsContract(t *testing.T) {
	fix, _ := LoadFixture("../../fixtures/joblog/normalized/RPG-RUNTIME-001.json")
	expected := fix.JobLog.Messages
	// Swap order -> must fail
	swapped := make([]JobMessage, len(expected))
	copy(swapped, expected)
	if len(swapped) >= 2 {
		swapped[0], swapped[1] = swapped[1], swapped[0]
		// Fix ordinals to reflect swapped order (simulates buggy replay)
		swapped[0].OrdinalPosition = 1
		swapped[1].OrdinalPosition = 2
		diffs := AssertEqual(expected, swapped)
		if len(diffs) == 0 {
			t.Fatalf("expected ordering diff but got none – order must be contract (§13)")
		}
	}
}

func TestContract_SNDPGMMSG_Informational(t *testing.T) {
	fix, _ := LoadFixture("../../fixtures/joblog/normalized/MSG-SNDPGMMSG-001.json")
	jl := NewWithPlaceholders()
	jl.AddInformational("CPF9897", 0, "HELLO FROM PROGRAM")
	if diffs := AssertEqual(fix.JobLog.Messages, jl.Messages()); len(diffs) > 0 {
		t.Fatalf("SNDPGMMSG contract failed: %v", diffs)
	}
}
