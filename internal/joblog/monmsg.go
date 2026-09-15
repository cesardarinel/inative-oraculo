// MonMsg / RcvMsg / SndPgmMsg — integración CL con JobLog (§11, §22)
package joblog

import (
	"strings"
)

// MonMsgRule models a CL MONMSG instruction: intercept messages by ID.
// In IBM i, MONMSG MSGID(CPFxxxx) EXEC(...) handles an Escape/Diagnostic without aborting.
type MonMsgRule struct {
	MsgID string // e.g. CPF9801 or CPF0000 wildcard (prefix)
	Handled bool // whether EXEC was DO (handled) vs just monitoring
}

// MonMsgManager holds active MONMSG intercepts for the current CL scope.
type MonMsgManager struct {
	rules []MonMsgRule
	log   *JobLog
}

// NewMonMsgManager creates a manager bound to a JobLog.
func NewMonMsgManager(jl *JobLog) *MonMsgManager {
	return &MonMsgManager{log: jl}
}

// Add registers a MONMSG rule. CPF0000 means catch-all.
func (m *MonMsgManager) Add(msgID string) {
	m.rules = append(m.rules, MonMsgRule{MsgID: strings.ToUpper(strings.TrimSpace(msgID)), Handled: true})
}

// ShouldIntercept reports whether the given message would be intercepted by MONMSG.
// This mirrors IBM i behavior before/after interception: the message still appears in Job Log
// but does NOT cause an Escape to propagate if MONMSG matches.
func (m *MonMsgManager) ShouldIntercept(msg JobMessage) bool {
	u := strings.ToUpper(msg.MessageID)
	for _, r := range m.rules {
		if r.MsgID == "CPF0000" || r.MsgID == "*ALL" {
			return true
		}
		if strings.HasSuffix(r.MsgID, "0000") {
			// prefix wildcard: CPF98* covers CPF9801 etc.
			prefix := strings.TrimSuffix(r.MsgID, "0000")
			if strings.HasPrefix(u, prefix) {
				return true
			}
		}
		if u == r.MsgID {
			return true
		}
	}
	return false
}

// InterceptAndLog adds a message but reports whether it was MONMSG'd (i.e., not escalating).
// The message is ALWAYS added to Job Log (§11: MONMSG still leaves trace, but prevents Escape).
func (m *MonMsgManager) InterceptAndLog(msg JobMessage) (intercepted bool) {
	was := m.ShouldIntercept(msg)
	m.log.Add(msg)
	return was
}

// SndPgmMsg models SNDPGMMSG / SND-MSG / DSPLY behavior (§12).
// It separates JobLog, DisplaySession and ProgramMessage as plan suggests.
type SndPgmMsgRequest struct {
	MsgID     string
	MsgText   string
	MsgType   MessageType // *INFO, *DIAG, *ESCAPE, *COMP, *STATUS
	ToProgram string      // TOPGMQ(*PRV), *EXT, etc.
	Severity  int
}

// SndPgmMsg sends a program message into the JobLog and returns the created JobMessage.
// This is the runtime entry point for SNDPGMMSG, SND-MSG (RPG), DSPLY.
func (jl *JobLog) SndPgmMsg(req SndPgmMsgRequest) JobMessage {
	if req.MsgType == "" {
		req.MsgType = TypeInformational
	}
	if req.MsgID == "" {
		req.MsgID = "CPF9897" // generic user message
	}
	if req.Severity == 0 && req.MsgType == TypeEscape {
		req.Severity = 40
	}
	m := JobMessage{
		MessageID:       strings.ToUpper(req.MsgID),
		MessageType:     req.MsgType,
		Severity:        req.Severity,
		MessageText:     req.MsgText,
		OrdinalPosition: jl.nextOrd,
		ToProgram:       req.ToProgram,
	}
	jl.Add(m)
	return m
}

// RcvMsg models RCVMSG (§11): retrieve and optionally remove a message.
// IBM i RCVMSG MSGQ(*PGMQ) etc. — here we pop from Job Log deterministically.
func (jl *JobLog) RcvMsg(msgID string, remove bool) *JobMessage {
	u := strings.ToUpper(strings.TrimSpace(msgID))
	for idx, m := range jl.messages {
		if msgID == "" || msgID == "*TOP" || m.MessageID == u {
			found := m // copy
			if remove {
				jl.messages = append(jl.messages[:idx], jl.messages[idx+1:]...)
				// Reordinalize to keep contract? Keep original ordinals for fidelity; just remove.
			}
			return &found
		}
	}
	return nil
}

// ClearMONMSG resets manager (scope exit).
func (m *MonMsgManager) Clear() { m.rules = nil }

// DisplaySession stub — separation hint for architecture (§12).
// Real DisplaySession would render DSPLY; here we just log as Informational.
func (jl *JobLog) Dsply(text string) JobMessage {
	return jl.SndPgmMsg(SndPgmMsgRequest{
		MsgID:   "CPF9897",
		MsgType: TypeInformational,
		MsgText: text,
		Severity: 0,
	})
}
