// Package joblog implements the deterministic JobLog engine for iNative.
//
// This is the runtime component that must reproduce the observable behavior of
// IBM i QSYS2.JOBLOG_INFO. It does NOT invent messages; it replays contracts
// captured from a real IBM i via the JobLog Recorder (probe/joblog_recorder).
//
// Hierarchy:
//
//	JobContext → CommandExecutor / RPG Runtime / FileHandle → JobLog Engine → Messages
//
// The engine is responsible for:
//
//	AddMessage / AddDiagnostic / AddEscape / AddCompletion
//	GetMessages / GetLastMessage / GetBySeverity / GetById / Clear / Snapshot
//	plus MONMSG / RCVMSG / SNDPGMMSG integration points.
package joblog

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"
)

// ---------------------------------------------------------------------------
// Message type – maps IBM i MESSAGE_TYPE (QSYS2.JOBLOG_INFO.MESSAGE_TYPE)
// ---------------------------------------------------------------------------

type MessageType string

const (
	TypeCompletion   MessageType = "COMPLETION"    // *COMP  CPC*
	TypeDiagnostic   MessageType = "DIAGNOSTIC"    // *DIAG  CPD*
	TypeEscape       MessageType = "ESCAPE"        // *ESCAPE CPF*
	TypeInformational MessageType = "INFORMATIONAL" // *INFO  CPI*
	TypeInquiry      MessageType = "INQUIRY"       // *INQ
	TypeNotify       MessageType = "NOTIFY"        // *NOTIFY
	TypeRequest      MessageType = "REQUEST"       // *RQS
	TypeSenderCopy   MessageType = "SENDER_COPY"   // *COPY
	TypeWarning      MessageType = "WARNING"       // derived from CPF severity
	Status           MessageType = "STATUS"        // *STATUS
	UnknownType      MessageType = "UNKNOWN"
)

// AllTypes enumerates known message types for validation.
var AllTypes = []MessageType{
	TypeCompletion, TypeDiagnostic, TypeEscape, TypeInformational,
	TypeInquiry, TypeNotify, TypeRequest, TypeSenderCopy, TypeWarning, Status,
}

// ParseMessageType normalizes raw IBM i values ("*COMP", "COMPLETION", "CPC") to canonical.
func ParseMessageType(raw string) MessageType {
	u := strings.ToUpper(strings.TrimSpace(raw))
	u = strings.TrimPrefix(u, "*")
	switch u {
	case "COMP", "COMPLETION", "CPC":
		return TypeCompletion
	case "DIAG", "DIAGNOSTIC", "CPD":
		return TypeDiagnostic
	case "ESCAPE", "CPF":
		return TypeEscape
	case "INFO", "INFORMATIONAL", "CPI":
		return TypeInformational
	case "INQ", "INQUIRY":
		return TypeInquiry
	case "NOTIFY":
		return TypeNotify
	case "RQS", "REQUEST":
		return TypeRequest
	case "COPY", "SENDER_COPY":
		return TypeSenderCopy
	case "WARNING":
		return TypeWarning
	case "STATUS":
		return Status
	case "":
		return UnknownType
	default:
		// Heuristic by prefix
		if strings.HasPrefix(u, "CPC") {
			return TypeCompletion
		}
		if strings.HasPrefix(u, "CPD") {
			return TypeDiagnostic
		}
		if strings.HasPrefix(u, "CPF") || strings.HasPrefix(u, "CEE") || strings.HasPrefix(u, "RNQ") || strings.HasPrefix(u, "RNS") {
			// CPF/CEE/RNQ are families, not types; caller must supply type separately.
			// Default to Escape if severity >= 30, else Diagnostic – but we return Unknown and let caller decide.
			return UnknownType
		}
		return MessageType(u)
	}
}

// ---------------------------------------------------------------------------
// JobMessage – one entry in the Job Log
// ---------------------------------------------------------------------------

// JobMessage models a single entry from QSYS2.JOBLOG_INFO with ordered,
// typed, and severitized semantics. Dynamic fields (timestamp, job_number)
// are separated so fixtures can be replayed deterministically.
type JobMessage struct {
	// Identification (STATIC)
	MessageID   string      `json:"message_id"`             // CPF0000, CEE9901, RNQ0100 …
	MessageType MessageType `json:"message_type"`           // COMPLETION, DIAGNOSTIC, ESCAPE …
	Severity    int         `json:"severity"`               // 0-99

	// Content (STATIC, but text may contain dynamic inserts – kept verbatim in raw)
	MessageText           string `json:"message_text"`
	MessageSecondLevelText string `json:"message_second_level_text,omitempty"`
	MessageSubstitutionData string `json:"message_substitution_data,omitempty"`

	// Temporal / ordering (DYNAMIC except ordinal)
	Timestamp       time.Time `json:"message_timestamp,omitempty"`
	OrdinalPosition int       `json:"ordinal_position"` // 1-based, contract: order matters

	// Provenance (for raw capture; stripped in normalized replay)
	FromProgram     string `json:"from_program,omitempty"`
	FromLibrary     string `json:"from_library,omitempty"`
	FromModule      string `json:"from_module,omitempty"`
	FromProcedure   string `json:"from_procedure,omitempty"`
	ToProgram       string `json:"to_program,omitempty"`
	FromUser        string `json:"from_user,omitempty"`
	MessageKey      string `json:"message_key,omitempty"` // internal IBM i key
	JobName         string `json:"job_name,omitempty"`    // denormalized for raw
}

// IsEscape reports whether this message would abort the caller if not MONMSG'd.
func (m JobMessage) IsEscape() bool { return m.MessageType == TypeEscape }

// IsDiagnostic reports diagnostic (chained before an Escape).
func (m JobMessage) IsDiagnostic() bool { return m.MessageType == TypeDiagnostic }

// StaticKey returns the semantic identity used for contract comparison
// (ignores dynamic fields like Timestamp, JobName, MessageKey).
func (m JobMessage) StaticKey() string {
	return fmt.Sprintf("%s|%s|%d|%s", m.MessageID, m.MessageType, m.Severity, strings.TrimSpace(m.MessageText))
}

// ---------------------------------------------------------------------------
// JobContext – execution context for the snapshot (STATIC structure, DYNAMIC values)
// ---------------------------------------------------------------------------

type JobContext struct {
	JobName    string `json:"job_name"`   // e.g. 123456/QUSER/QPADEV0001
	JobUser    string `json:"job_user"`
	JobNumber  string `json:"job_number"`
	JobType    string `json:"job_type,omitempty"`    // INTERACTIVE, BATCH, etc.
	JobSubtype string `json:"job_subtype,omitempty"` // D, I …
	SystemName string `json:"system_name,omitempty"`
	LibraryList []string `json:"library_list,omitempty"`
	CurrentLibrary string `json:"current_library,omitempty"`
	CCSID     int    `json:"ccsid,omitempty"`
}

// Placeholder returns a JobContext with dynamic placeholders for replay.
func PlaceholderJobContext() JobContext {
	return JobContext{
		JobName:    "${JOB_NAME}",
		JobUser:    "${JOB_USER}",
		JobNumber:  "${JOB_NUMBER}",
		SystemName: "${SYSTEM_NAME}",
	}
}

// ---------------------------------------------------------------------------
// JobLog Engine
// ---------------------------------------------------------------------------

type JobLog struct {
	ctx      JobContext
	messages []JobMessage
	nextOrd  int
}

// New creates an empty JobLog scoped to the given context.
func New(ctx JobContext) *JobLog {
	return &JobLog{ctx: ctx, nextOrd: 1}
}

// NewWithPlaceholders creates a JobLog with placeholder context (for fixtures replay).
func NewWithPlaceholders() *JobLog { return New(PlaceholderJobContext()) }

// Context returns the job context (copy).
func (jl *JobLog) Context() JobContext { return jl.ctx }

// SetContext replaces the context (e.g. after capturing real values).
func (jl *JobLog) SetContext(c JobContext) { jl.ctx = c }

// Add appends a fully-formed message, assigning ordinal if zero.
func (jl *JobLog) Add(m JobMessage) {
	if m.OrdinalPosition == 0 {
		m.OrdinalPosition = jl.nextOrd
		jl.nextOrd++
	} else if m.OrdinalPosition >= jl.nextOrd {
		jl.nextOrd = m.OrdinalPosition + 1
	}
	// Ensure deterministic ordering invariant
	jl.messages = append(jl.messages, m)
}

// AddMessage is the generic append (COMPLETION by default if type empty).
func (jl *JobLog) AddMessage(id string, typ MessageType, severity int, text string) JobMessage {
	if typ == "" {
		typ = TypeCompletion
	}
	m := JobMessage{
		MessageID:       strings.ToUpper(strings.TrimSpace(id)),
		MessageType:     typ,
		Severity:        severity,
		MessageText:     text,
		OrdinalPosition: jl.nextOrd,
		Timestamp:       time.Now().UTC(),
	}
	jl.Add(m)
	return m
}

func (jl *JobLog) AddCompletion(id string, severity int, text string) JobMessage {
	return jl.AddMessage(id, TypeCompletion, severity, text)
}
func (jl *JobLog) AddDiagnostic(id string, severity int, text string) JobMessage {
	return jl.AddMessage(id, TypeDiagnostic, severity, text)
}
func (jl *JobLog) AddEscape(id string, severity int, text string) JobMessage {
	return jl.AddMessage(id, TypeEscape, severity, text)
}
func (jl *JobLog) AddInformational(id string, severity int, text string) JobMessage {
	return jl.AddMessage(id, TypeInformational, severity, text)
}

// Messages returns a copy ordered by ordinal.
func (jl *JobLog) Messages() []JobMessage {
	out := make([]JobMessage, len(jl.messages))
	copy(out, jl.messages)
	sort.Slice(out, func(i, j int) bool { return out[i].OrdinalPosition < out[j].OrdinalPosition })
	return out
}

// GetLastMessage returns the last message or nil.
func (jl *JobLog) GetLastMessage() *JobMessage {
	if len(jl.messages) == 0 {
		return nil
	}
	last := jl.messages[len(jl.messages)-1]
	return &last
}

// GetBySeverity returns messages with severity >= min (inclusive).
func (jl *JobLog) GetBySeverity(min int) []JobMessage {
	var out []JobMessage
	for _, m := range jl.messages {
		if m.Severity >= min {
			out = append(out, m)
		}
	}
	return out
}

// GetByID returns messages matching id (case-insensitive, ordered).
func (jl *JobLog) GetByID(id string) []JobMessage {
	u := strings.ToUpper(strings.TrimSpace(id))
	var out []JobMessage
	for _, m := range jl.messages {
		if m.MessageID == u {
			out = append(out, m)
		}
	}
	return out
}

// GetByType returns messages of given type.
func (jl *JobLog) GetByType(t MessageType) []JobMessage {
	var out []JobMessage
	for _, m := range jl.messages {
		if m.MessageType == t {
			out = append(out, m)
		}
	}
	return out
}

// Clear removes all messages (but keeps ordinal counter for diagnostics; reset if needed).
func (jl *JobLog) Clear() { jl.messages = nil }

// Reset clears and resets ordinal (simulates new job).
func (jl *JobLog) Reset() { jl.messages = nil; jl.nextOrd = 1 }

// Len reports number of messages.
func (jl *JobLog) Len() int { return len(jl.messages) }

// Snapshot returns an immutable copy of the entire log (for diff / fixture).
func (jl *JobLog) Snapshot() Snapshot {
	msgs := jl.Messages()
	return Snapshot{Job: jl.ctx, Messages: msgs, CapturedAt: time.Now().UTC()}
}

// Snapshot is the serializable view of a JobLog at a point in time.
type Snapshot struct {
	Job        JobContext  `json:"job"`
	Messages   []JobMessage `json:"messages"`
	CapturedAt time.Time    `json:"captured_at,omitempty"`
}

// MarshalJSON ensures stable ordering by ordinal.
func (s Snapshot) MarshalJSON() ([]byte, error) {
	type raw Snapshot
	cp := raw(s)
	sort.Slice(cp.Messages, func(i, j int) bool { return cp.Messages[i].OrdinalPosition < cp.Messages[j].OrdinalPosition })
	return json.Marshal(cp)
}

// Diff computes messages present in 'after' but not in 'before' (by ordinal+id+text).
// This implements the INITIAL SNAPSHOT → EXECUTE → FINAL SNAPSHOT → DIFF workflow.
func Diff(before, after []JobMessage) []JobMessage {
	seen := make(map[string]bool, len(before))
	for _, m := range before {
		seen[m.StaticKey()] = true
		// Also index by ordinal to avoid missing reordered diagnostics
		seen[fmt.Sprintf("ord:%d:%s", m.OrdinalPosition, m.MessageID)] = true
	}
	var delta []JobMessage
	for _, m := range after {
		k := m.StaticKey()
		ok := fmt.Sprintf("ord:%d:%s", m.OrdinalPosition, m.MessageID)
		if !seen[k] && !seen[ok] {
			delta = append(delta, m)
		}
	}
	return delta
}

// Normalize returns a copy with dynamic fields replaced by placeholders,
// suitable for deterministic replay comparison (STATIC contract).
func Normalize(msgs []JobMessage) []JobMessage {
	out := make([]JobMessage, len(msgs))
	for i, m := range msgs {
		out[i] = m
		out[i].Timestamp = time.Time{} // strip
		out[i].JobName = "${JOB_NAME}"
		out[i].MessageKey = ""
		// Collapse whitespace in text for stability (but preserve raw separately)
		out[i].MessageText = strings.Join(strings.Fields(m.MessageText), " ")
		out[i].MessageSecondLevelText = strings.Join(strings.Fields(m.MessageSecondLevelText), " ")
	}
	return out
}
