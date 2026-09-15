package joblog

import (
	"path/filepath"
	"testing"
)

// TestAllNormalizedFixtures_SelfConsistent verifies every normalized fixture under inative-mock-data/normalized
// can be replayed deterministically (STATIC contract) — corpus as executable spec.
func TestAllNormalizedFixtures_SelfConsistent(t *testing.T) {
	matches, err := filepath.Glob("../../inative-mock-data/normalized/*.json")
	if err != nil || len(matches) == 0 {
		matches, _ = filepath.Glob("../../fixtures/joblog/normalized/*.json")
	}
	if len(matches) == 0 {
		t.Fatalf("no fixtures found")
	}
	for _, p := range matches {
		fix, err := LoadFixture(p)
		if err != nil {
			t.Errorf("%s load failed: %v", p, err)
			continue
		}
		// Replay into fresh JobLog and verify contract self-equality
		jl := NewWithPlaceholders()
		for _, m := range fix.JobLog.Messages {
			jl.Add(m)
		}
		if diffs := AssertEqual(fix.JobLog.Messages, jl.Messages()); len(diffs) > 0 {
			t.Errorf("%s contract self-check failed: %v", filepath.Base(p), diffs)
		}
		// Verify static/dynamic separation: normalized must not contain real timestamps/job numbers
		for _, m := range fix.JobLog.Messages {
			if m.JobName != "${JOB_NAME}" && m.JobName != "" {
				t.Errorf("%s: JobName not normalized: %q", p, m.JobName)
			}
			if !m.Timestamp.IsZero() {
				t.Errorf("%s: Timestamp not stripped", p)
			}
		}
	}
}

func TestSecondLevel_Preserved(t *testing.T) {
	fix, _ := LoadFixture("../../fixtures/joblog/normalized/RPG-RUNTIME-001.json")
	if fix.JobLog.Messages[0].MessageSecondLevelText == "" {
		t.Fatalf("expected second level preserved in normalized")
	}
	// Ensure AssertEqual detects second-level mismatch (contract per §1)
	jl := NewWithPlaceholders()
	for _, m := range fix.JobLog.Messages {
		// strip second level on purpose → should fail
		m2 := m
		m2.MessageSecondLevelText = ""
		jl.Add(m2)
		if len(fix.JobLog.Messages) == len(jl.Messages()) {
			break
		}
	}
	// Actually test with fully stripped: should produce diff
	jl2 := NewWithPlaceholders()
	for _, m := range fix.JobLog.Messages {
		m.MessageSecondLevelText = ""
		jl2.Add(m)
	}
	if diffs := AssertEqual(fix.JobLog.Messages, jl2.Messages()); len(diffs) == 0 {
		t.Fatalf("second-level mismatch should be detected")
	}
}

func TestMessageTypes_Exhaustive(t *testing.T) {
	cases := []struct{ raw, want string }{
		{"*COMP", "COMPLETION"},
		{"*DIAG", "DIAGNOSTIC"},
		{"*ESCAPE", "ESCAPE"},
		{"*INFO", "INFORMATIONAL"},
		{"CPC2102", "COMPLETION"},
		{"CPD0030", "DIAGNOSTIC"},
	}
	for _, tc := range cases {
		got := ParseMessageType(tc.raw)
		if string(got) != tc.want {
			t.Errorf("ParseMessageType(%q)=%q want %q", tc.raw, got, tc.want)
		}
	}
}

// TestJobLog_DiagBeforeEscape_Order ensures diagnostic chain before escape (plan §13)
func TestJobLog_DiagBeforeEscape_Order(t *testing.T) {
	jl := NewWithPlaceholders()
	jl.AddDiagnostic("CPF9801", 30, "Object not found")
	jl.AddEscape("CPF0006", 30, "Errors occurred")
	msgs := jl.Messages()
	if msgs[0].MessageType != TypeDiagnostic || msgs[1].MessageType != TypeEscape {
		t.Fatalf("ordering broken: %+v", msgs)
	}
	if msgs[0].OrdinalPosition >= msgs[1].OrdinalPosition {
		t.Fatalf("ordinal not strictly increasing")
	}
}
