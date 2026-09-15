package joblog

import (
	"encoding/json"
	"fmt"
	"os"
	"time"
)

// ---------------------------------------------------------------------------
// Fixture – contract captured from IBM i and replayed in iNative.
// Two-level storage: raw (exact) + normalized (static contract).
// ---------------------------------------------------------------------------

const FixtureVersion = 1

type FixtureStatus string

const (
	StatusCaptured FixtureStatus = "CAPTURED"
	StatusReviewed FixtureStatus = "REVIEWED"
	StatusVerified FixtureStatus = "VERIFIED"
)

type Fixture struct {
	FixtureVersion int            `json:"fixture_version"`
	Source         string         `json:"source"` // "IBM i 7.5" / "PUB400"
	Experiment     ExperimentMeta `json:"experiment"`
	Job            JobContext     `json:"job"`
	JobRaw         *JobContext    `json:"job_raw,omitempty"` // exact values before normalization
	Operation      OperationMeta  `json:"operation"`
	Result         ResultMeta     `json:"result"`
	JobLog         JobLogFixture  `json:"joblog"`
	Raw            *RawCapture    `json:"raw,omitempty"`      // only in raw/ file, not normalized
	Manifest       *Manifest      `json:"manifest,omitempty"`
}

type ExperimentMeta struct {
	ID        string `json:"id"`        // JOBLOG-0001, RPG-RUNTIME-001 …
	Name      string `json:"name"`      // divide_by_zero, invalid_command …
	Language  string `json:"language"`  // RPGLE, CL, CMD, FILEIO, MESSAGE
	Operation string `json:"operation"` // CALL, CRTBNDRPG, SNDPGMMSG …
	Category  string `json:"category,omitempty"` // commands/success, rpg/runtime/...
}

type OperationMeta struct {
	Command string `json:"command"`           // full CL command executed
	Program string `json:"program,omitempty"` // target pgm if CALL
	Library string `json:"library,omitempty"`
	Extra   map[string]string `json:"extra,omitempty"` // parms, etc.
}

type ResultMeta struct {
	Success    bool   `json:"success"`
	ExitCode   int    `json:"exit_code,omitempty"`
	ReturnCode int    `json:"return_code,omitempty"`
	SQLCode    *int   `json:"sqlcode,omitempty"`
}

type JobLogFixture struct {
	Messages      []JobMessage `json:"messages"`                 // normalized, ordered – the contract
	RawMessages   []JobMessage `json:"raw_messages,omitempty"`   // exact capture (only raw file)
	InitialCount  int          `json:"initial_count,omitempty"`  // len(initial_snapshot)
	FinalCount    int          `json:"final_count,omitempty"`    // len(final_snapshot)
	DeltaCount    int          `json:"delta_count"`              // len(messages)
}

type RawCapture struct {
	InitialSnapshot Snapshot  `json:"initial_snapshot"`
	FinalSnapshot   Snapshot  `json:"final_snapshot"`
	Delta           []JobMessage `json:"delta"`
	IBMiVersion     string    `json:"ibmi_version,omitempty"`
	CapturedAt      time.Time `json:"captured_at"`
	Host            string    `json:"host,omitempty"`
}

type Manifest struct {
	ID              string        `json:"id"`
	Language        string        `json:"language"`
	SourceFile      string        `json:"source_file,omitempty"`
	Command         string        `json:"command"`
	Execution       string        `json:"execution,omitempty"`
	ExpectedResult  string        `json:"expected_result,omitempty"` // success, runtime_error, compile_error …
	IBMiVersion     string        `json:"ibmi_version,omitempty"`
	CapturedAt      time.Time     `json:"captured_at"`
	FixtureStatus   FixtureStatus `json:"fixture_status"`
	RecorderVersion string        `json:"recorder_version,omitempty"`
	Notes           string        `json:"notes,omitempty"`
}

// DynamicFields enumerates fields considered non-deterministic and replaced in normalized.
var DynamicFields = []string{"job_number", "job_name", "job_user", "timestamp", "system_name", "message_key"}

// NewFixture builds a normalized fixture from raw snapshots via Diff + Normalize.
func NewFixture(exp ExperimentMeta, jobRaw JobContext, op OperationMeta, result ResultMeta, before, after Snapshot, ibmiVersion, host string) Fixture {
	delta := Diff(before.Messages, after.Messages)
	normalized := Normalize(delta)

	jobNormalized := jobRaw
	jobNormalized.JobName = "${JOB_NAME}"
	jobNormalized.JobUser = "${JOB_USER}"
	jobNormalized.JobNumber = "${JOB_NUMBER}"
	jobNormalized.SystemName = "${SYSTEM_NAME}"

	now := time.Now().UTC()
	// copy for raw preservation
	jr := jobRaw

	return Fixture{
		FixtureVersion: FixtureVersion,
		Source:         fmt.Sprintf("IBM i %s", ibmiVersion),
		Experiment:     exp,
		Job:            jobNormalized,
		JobRaw:         &jr,
		Operation:      op,
		Result:         result,
		JobLog: JobLogFixture{
			Messages:     normalized,
			RawMessages:  delta,
			InitialCount: len(before.Messages),
			FinalCount:   len(after.Messages),
			DeltaCount:   len(delta),
		},
		Raw: &RawCapture{
			InitialSnapshot: before,
			FinalSnapshot:   after,
			Delta:           delta,
			IBMiVersion:     ibmiVersion,
			CapturedAt:      now,
			Host:            host,
		},
		Manifest: &Manifest{
			ID:             exp.ID,
			Language:       exp.Language,
			Command:        op.Command,
			ExpectedResult: map[bool]string{true: "success", false: "error"}[result.Success],
			IBMiVersion:    ibmiVersion,
			CapturedAt:     now,
			FixtureStatus:  StatusCaptured,
		},
	}
}

// WriteRaw writes the full fixture (with Raw) to path (raw/…).
func (f Fixture) WriteRaw(path string) error {
	data, err := json.MarshalIndent(f, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

// WriteNormalized writes only the deterministic contract (without Raw field) to path.
func (f Fixture) WriteNormalized(path string) error {
	cp := f
	cp.Raw = nil
	cp.JobRaw = nil
	// Keep only normalized messages
	cp.JobLog.RawMessages = nil
	data, err := json.MarshalIndent(cp, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

// LoadFixture reads a fixture from disk (raw or normalized).
func LoadFixture(path string) (Fixture, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return Fixture{}, err
	}
	var f Fixture
	if err := json.Unmarshal(data, &f); err != nil {
		return Fixture{}, err
	}
	return f, nil
}

// AssertEqual compares expected (from fixture) vs actual (from JobLog engine)
// honoring static contract: ID, Type, Severity, Order, Text (normalized),
// and allowing dynamic fields to differ.
func AssertEqual(expected, actual []JobMessage) []string {
	var diffs []string
	if len(expected) != len(actual) {
		diffs = append(diffs, fmt.Sprintf("message count: expected %d got %d", len(expected), len(actual)))
	}
	n := len(expected)
	if len(actual) < n {
		n = len(actual)
	}
	for i := 0; i < n; i++ {
		e, a := expected[i], actual[i]
		base := fmt.Sprintf("messages[%d]", i)
		if e.MessageID != a.MessageID {
			diffs = append(diffs, fmt.Sprintf("%s.id: expected %q got %q", base, e.MessageID, a.MessageID))
		}
		if e.MessageType != a.MessageType && e.MessageType != UnknownType && a.MessageType != UnknownType {
			diffs = append(diffs, fmt.Sprintf("%s.type: expected %q got %q", base, e.MessageType, a.MessageType))
		}
		if e.Severity != a.Severity {
			diffs = append(diffs, fmt.Sprintf("%s.severity: expected %d got %d", base, e.Severity, a.Severity))
		}
		if e.OrdinalPosition != a.OrdinalPosition {
			diffs = append(diffs, fmt.Sprintf("%s.ordinal: expected %d got %d", base, e.OrdinalPosition, a.OrdinalPosition))
		}
		// text: compare normalized (collapse ws, case-sensitive as IBM i)
		en := normalizeText(e.MessageText)
		an := normalizeText(a.MessageText)
		if en != an {
			diffs = append(diffs, fmt.Sprintf("%s.text: expected %q got %q", base, en, an))
		}
		if e.MessageSecondLevelText != "" || a.MessageSecondLevelText != "" {
			es := normalizeText(e.MessageSecondLevelText)
			as := normalizeText(a.MessageSecondLevelText)
			if es != as {
				diffs = append(diffs, fmt.Sprintf("%s.second_level: expected %q got %q", base, es, as))
			}
		}
	}
	// extra actual messages beyond expected
	if len(actual) > len(expected) {
		for i := len(expected); i < len(actual); i++ {
			diffs = append(diffs, fmt.Sprintf("unexpected extra message[%d]: %s %s", i, actual[i].MessageID, actual[i].MessageText))
		}
	}
	return diffs
}

func normalizeText(s string) string {
	// collapse whitespace, preserve case
	fields := []string{}
	for _, f := range splitFields(s) {
		if f != "" {
			fields = append(fields, f)
		}
	}
	return join(fields, " ")
}

func splitFields(s string) []string {
	// strings.Fields already does collapse
	return split(s)
}

func split(s string) []string {
	// use std Fields semantics
	var out []string
	start := -1
	for i, r := range s {
		isSpace := r == ' ' || r == '\t' || r == '\n' || r == '\r'
		if !isSpace && start == -1 {
			start = i
		}
		if isSpace && start != -1 {
			out = append(out, s[start:i])
			start = -1
		}
	}
	if start != -1 {
		out = append(out, s[start:])
	}
	return out
}

func join(elems []string, sep string) string {
	if len(elems) == 0 {
		return ""
	}
	res := elems[0]
	for _, e := range elems[1:] {
		res += sep + e
	}
	return res
}
