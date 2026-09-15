// Package mock — Mock IBM i behavior corpus para iNative (plan §18-§23).
// Re-exports fixtures capturados como Mock Runtime sin IBM i real.
// Implementa: entrada → comando → JobLog → resultado → pantalla → EVFEVENT → estado final.
package mock

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"oraculo/internal/command"
	"oraculo/internal/filehandle"
	"oraculo/internal/joblog"
)

// Corpus holds all verified fixtures in normalized form (STATIC contract).
type Corpus struct {
	Root string // inative-mock-data or fixtures/joblog/normalized
}

// New creates corpus pointing at inative-mock-data/normalized by default.
func New(root string) *Corpus {
	if root == "" {
		root = "inative-mock-data/normalized"
	}
	return &Corpus{Root: root}
}

// Load loads a fixture by ID (with or without .json).
func (c *Corpus) Load(id string) (joblog.Fixture, error) {
	if !strings.HasSuffix(id, ".json") {
		id += ".json"
	}
	roots := []string{c.Root}
	// Also try relative to repo root when invoked from subpackages (go test ./internal/mock)
	roots = append(roots,
		"fixtures/joblog/normalized",
		"tools/joblog-recorder/fixtures/normalized",
		"../fixtures/joblog/normalized",
		"../../fixtures/joblog/normalized",
		"../../inative-mock-data/normalized",
		"../inative-mock-data/normalized",
		"inative-mock-data/normalized",
	)
	// Also absolute repo root guess
	if wd, err := os.Getwd(); err == nil {
		// walk up 3 levels
		for i := 0; i < 4; i++ {
			try := filepath.Join(wd, strings.Repeat("../", i), "fixtures/joblog/normalized", id)
			roots = append(roots, try)
			try2 := filepath.Join(wd, strings.Repeat("../", i), "inative-mock-data/normalized", id)
			roots = append(roots, try2)
		}
	}
	for _, r := range roots {
		// if r is already a file path (contains .json), try direct
		if strings.HasSuffix(r, ".json") {
			if _, err := os.Stat(r); err == nil {
				return joblog.LoadFixture(r)
			}
			continue
		}
		p := filepath.Join(r, id)
		// normalize
		if _, err := os.Stat(p); err == nil {
			return joblog.LoadFixture(p)
		}
		// also try if r already is full path to file (when c.Root is full path)
		if _, err := os.Stat(r); err == nil && !strings.HasSuffix(r, ".json") {
			// r is dir, already tried
		}
	}
	// Direct candidate files
	candidates := []string{
		filepath.Join(c.Root, id),
	}
	for _, p := range candidates {
		if _, err := os.Stat(p); err == nil {
			return joblog.LoadFixture(p)
		}
	}
	// walk from c.Root
	var found string
	_ = filepath.Walk(c.Root, func(p string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && filepath.Base(p) == id {
			found = p
			return fmt.Errorf("found")
		}
		return nil
	})
	if found != "" {
		return joblog.LoadFixture(found)
	}
	// fallback walk fixtures
	_ = filepath.Walk("fixtures", func(p string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && filepath.Base(p) == id {
			found = p
			return fmt.Errorf("found")
		}
		return nil
	})
	if found != "" {
		return joblog.LoadFixture(found)
	}
	return joblog.Fixture{}, fmt.Errorf("fixture %s not found in corpus %s (wd=%s)", id, c.Root, func() string { wd, _ := os.Getwd(); return wd }())
}

// Runtime is the mock iNative runtime that replays IBM i behavior.
// Architecture: JobContext → CommandExecutor → RPG Runtime (FileHandle) → JobLog (§22)
type Runtime struct {
	JobCtx  joblog.JobContext
	Log     *joblog.JobLog
	Exec    *command.Executor
	Files   map[string]*filehandle.Handle
	Corpus  *Corpus
}

// NewRuntime creates a runtime with placeholder JobContext (deterministic replay).
func NewRuntime(corpusRoot string) *Runtime {
	jc := joblog.PlaceholderJobContext()
	jl := joblog.New(jc)
	return &Runtime{
		JobCtx: jc,
		Log:    jl,
		Exec:   command.New(jl, "QTEMP"),
		Files:  make(map[string]*filehandle.Handle),
		Corpus: New(corpusRoot),
	}
}

// ReplayFixture loads the expected messages from corpus and replays them into the JobLog.
// This is the "Mock IBM i behavior" — no invention, only verified contracts.
func (r *Runtime) ReplayFixture(id string) error {
	fix, err := r.Corpus.Load(id)
	if err != nil {
		return err
	}
	r.Log.Clear()
	for _, m := range fix.JobLog.Messages {
		r.Log.Add(m)
	}
	r.JobCtx = fix.Job
	r.Log.SetContext(fix.Job)
	return nil
}

// ExecCommand executes a CL command via Executor (which itself logs to JobLog).
// If a fixture exists for this command pattern, prefer its exact messages.
func (r *Runtime) ExecCommand(cmd string) (bool, int) {
	// Try to find fixture by command prefix for deterministic replay
	upper := strings.ToUpper(strings.TrimSpace(cmd))
	var fixtureID string
	switch {
	case strings.Contains(upper, "DIVZERO"):
		fixtureID = "RPG-RUNTIME-001"
	case strings.Contains(upper, "NOTEXIST") && strings.Contains(upper, "CALL"):
		fixtureID = "CMD-ERR-002"
	default:
		return r.Exec.Exec(cmd)
	}
	if err := r.ReplayFixture(fixtureID); err == nil {
		// Return result from fixture
		fix, _ := r.Corpus.Load(fixtureID)
		return fix.Result.Success, fix.Result.ExitCode
	}
	return r.Exec.Exec(cmd)
}

// File returns or creates a FileHandle bound to this runtime's JobLog.
func (r *Runtime) File(name, lib string) *filehandle.Handle {
	key := strings.ToUpper(lib + "/" + name)
	if h, ok := r.Files[key]; ok {
		return h
	}
	h := filehandle.New(name, lib, r.Log)
	r.Files[key] = h
	return h
}

// VSCodeResponse builds the JSON that VS Code would receive from IBM i for this JobLog.
// This satisfies §P2 VS Code integration: response compatible.
func (r *Runtime) VSCodeResponse() map[string]interface{} {
	msgs := r.Log.Messages()
	out := make([]map[string]interface{}, len(msgs))
	for i, m := range msgs {
		out[i] = map[string]interface{}{
			"messageId":   m.MessageID,
			"messageType": string(m.MessageType),
			"severity":    m.Severity,
			"text":        m.MessageText,
			"secondLevel": m.MessageSecondLevelText,
			"ordinal":     m.OrdinalPosition,
		}
	}
	// EVFEVENT if fixture had it
	var evfevent interface{}
	// Try load last replayed fixture's evfevent
	return map[string]interface{}{
		"job":      r.JobCtx,
		"jobLog":   out,
		"evfevent": evfevent,
		"success":  len(r.Log.GetByType(joblog.TypeEscape)) == 0,
	}
}

// MarshalJobLog returns stable JSON for VS Code mock server.
func (r *Runtime) MarshalJobLog() ([]byte, error) {
	return json.MarshalIndent(r.VSCodeResponse(), "", "  ")
}
