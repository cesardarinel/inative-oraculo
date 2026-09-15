// Package filehandle — RPG FileHandle runtime per §10 (P2).
// Maps RPG opcodes to JobLog + indicators + status codes, replaying fixtures.
package filehandle

import (
	"fmt"
	"strings"

	"oraculo/internal/joblog"
)

// Op enumerates file operations per §10.
type Op string

const (
	OpOpen   Op = "OPEN"
	OpRead   Op = "READ"
	OpReadC  Op = "READC"
	OpReadE  Op = "READE"
	OpReadP  Op = "READP"
	OpReadPE Op = "READPE"
	OpChain  Op = "CHAIN"
	OpSetLL  Op = "SETLL"
	OpSetGT  Op = "SETGT"
	OpWrite  Op = "WRITE"
	OpUpdate Op = "UPDATE"
	OpDelete Op = "DELETE"
)

// FileStatus mirrors RPG %STATUS / INFDS.
type FileStatus struct {
	Found   bool // %FOUND / CHAIN success
	EOF     bool // %EOF
	Equal   bool // %EQUAL
	Error   bool // general error
	StatusCode int // 0 = success, else CPF/RNX code numeric
}

// Handle is a deterministic file handle that writes to JobLog.
// In iNative mock runtime, operations replay fixtures; this implementation
// emits the correct IBM i message pattern without a real DB.
type Handle struct {
	Name   string
	Library string
	Log    *joblog.JobLog
	Status FileStatus
	Indicators map[string]bool // RPG indicators 01-99, e.g., IN90 = EOF
	records map[string]bool    // mock key → exists
}

// New creates a handle bound to a JobLog (JobContext injected).
func New(name, library string, jl *joblog.JobLog) *Handle {
	if jl == nil {
		jl = joblog.NewWithPlaceholders()
	}
	return &Handle{
		Name: strings.ToUpper(name),
		Library: strings.ToUpper(library),
		Log: jl,
		Indicators: make(map[string]bool),
		records: map[string]bool{"KEY1": true, "EXIST": true},
	}
}

// setIndicator sets RPG indicator per operation outcome.
func (h *Handle) setIndicator(ind string, v bool) {
	h.Indicators[ind] = v
}

// Chain emulates CHAIN: random access by key.
// Success → CPF? No message, just indicators. Not-found → RNQ1221 + diagnostic chain handled via fixture replay.
func (h *Handle) Chain(key string) FileStatus {
	key = strings.ToUpper(key)
	if h.records[key] {
		h.Status = FileStatus{Found: true, StatusCode: 0}
		h.setIndicator("90", false)
		h.setIndicator("91", false)
		// No JobLog on success (just CPF-like completion if needed)
		return h.Status
	}
	// Record not found — IBM i would set indicators and optionally RNQ/RNX + CPF
	h.Status = FileStatus{Found: false, StatusCode: 1221, Error: true}
	h.setIndicator("90", true) // *IN90 = not found commonly
	// Emit diagnostic chain as fixtures expect (ordered! §13)
	h.Log.AddDiagnostic("RNX1221", 30, fmt.Sprintf("Record with key %s not found in file %s.%s.", key, h.Library, h.Name))
	h.Log.AddDiagnostic("CPF5027", 30, fmt.Sprintf("CHAIN: Record not found for file %s.", h.Name))
	return h.Status
}

// Read emulates sequential READ: returns next record or EOF.
func (h *Handle) Read() FileStatus {
	// For mock, alternate: first call success, second EOF (simplified)
	if h.Status.EOF {
		return h.Status
	}
	// Simulate EOF after one successful read if no more records
	// We'll flip to EOF on second call for test determinism
	if h.Status.Found {
		h.Status = FileStatus{EOF: true}
		h.setIndicator("90", true) // EOF indicator
		h.Log.AddInformational("CPF5001", 0, fmt.Sprintf("READ: End of file reached for %s.", h.Name))
		return h.Status
	}
	h.Status = FileStatus{Found: true}
	h.setIndicator("90", false)
	return h.Status
}

// ReadE emulates READE (read equal key).
func (h *Handle) ReadE(key string) FileStatus {
	return h.Chain(key) // simplified: same as CHAIN for mock
}

// SetLL emulates SETLL: set lower limit, sets %FOUND/%EQUAL + indicators.
func (h *Handle) SetLL(key string) FileStatus {
	found := h.records[strings.ToUpper(key)]
	h.Status = FileStatus{Found: found, Equal: found}
	h.setIndicator("90", !found)
	h.setIndicator("91", !found) // *IN91 often equal
	if !found {
		h.Log.AddDiagnostic("CPF5025", 10, fmt.Sprintf("SETLL: Key %s not found, positioned at next.", key))
	}
	return h.Status
}

// SetGT emulates SETGT: set greater than.
func (h *Handle) SetGT(key string) FileStatus {
	// Always succeeds positioning, no error message.
	h.Status = FileStatus{Found: true}
	h.setIndicator("90", false)
	return h.Status
}

// Write emulates WRITE: duplicate key → CPF5033 etc.
func (h *Handle) Write(key string) FileStatus {
	key = strings.ToUpper(key)
	if h.records[key] {
		h.Status = FileStatus{Error: true, StatusCode: 5033}
		h.Log.AddEscape("CPF5033", 30, fmt.Sprintf("WRITE: Duplicate key %s in file %s.", key, h.Name))
		return h.Status
	}
	h.records[key] = true
	h.Status = FileStatus{Found: true, StatusCode: 0}
	h.Log.AddCompletion("CPF5035", 0, fmt.Sprintf("WRITE: Record %s written to file %s.", key, h.Name))
	return h.Status
}

// Update emulates UPDATE: record not locked → CPF5069.
func (h *Handle) Update(key string) FileStatus {
	if !h.records[strings.ToUpper(key)] {
		h.Status = FileStatus{Error: true, StatusCode: 5027}
		h.Log.AddEscape("CPF5027", 30, fmt.Sprintf("UPDATE: Record %s not found for update.", key))
		return h.Status
	}
	h.Status = FileStatus{Found: true}
	h.Log.AddCompletion("CPF5036", 0, fmt.Sprintf("UPDATE: Record %s updated.", key))
	return h.Status
}

// Delete emulates DELETE.
func (h *Handle) Delete(key string) FileStatus {
	if !h.records[strings.ToUpper(key)] {
		h.Status = FileStatus{Error: true, StatusCode: 5027}
		h.Log.AddEscape("CPF5027", 30, fmt.Sprintf("DELETE: Record %s not found.", key))
		return h.Status
	}
	delete(h.records, strings.ToUpper(key))
	h.Status = FileStatus{Found: true}
	h.Log.AddCompletion("CPF5037", 0, fmt.Sprintf("DELETE: Record %s deleted from %s.", key, h.Name))
	return h.Status
}

// SetRecord allows tests to seed mock DB without JobLog side effects.
func (h *Handle) SetRecord(key string, exists bool) {
	if exists {
		h.records[strings.ToUpper(key)] = true
	} else {
		delete(h.records, strings.ToUpper(key))
	}
}

// ResetRecords clears and optionally seeds records (for deterministic fileio tests).
func (h *Handle) ResetRecords(keys ...string) {
	h.records = make(map[string]bool)
	for _, k := range keys {
		h.records[strings.ToUpper(k)] = true
	}
	h.Status = FileStatus{}
	h.Indicators = make(map[string]bool)
}

// Open checks object existence (§10: file not found, no authority, member not found).
func (h *Handle) Open() FileStatus {
	if h.Name == "NOTEXIST" || h.Name == "NOTFOUND" {
		h.Status = FileStatus{Error: true, StatusCode: 9801}
		h.Log.AddDiagnostic("CPF9801", 30, fmt.Sprintf("Object %s in library %s not found.", h.Name, h.Library))
		h.Log.AddEscape("CPF0006", 30, "Errors occurred in command.")
		return h.Status
	}
	if h.Name == "NOAUTH" {
		h.Status = FileStatus{Error: true, StatusCode: 9802}
		h.Log.AddEscape("CPF9802", 30, fmt.Sprintf("Not authorized to object %s in %s.", h.Name, h.Library))
		return h.Status
	}
	h.Status = FileStatus{Found: true}
	return h.Status
}
