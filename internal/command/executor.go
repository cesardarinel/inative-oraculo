// Package command — CommandExecutor per §22 diagram (JobContext → CommandExecutor → JobLog)
package command

import (
	"strings"

	"oraculo/internal/joblog"
)

// Executor executes CL commands deterministically, emitting IBM i JobLog messages.
// It is the Mock IBM i behavior layer; fixtures are the evidence.
type Executor struct {
	Log     *joblog.JobLog
	MonMgr  *joblog.MonMsgManager
	Library string
}

// New creates executor bound to JobLog.
func New(jl *joblog.JobLog, lib string) *Executor {
	if jl == nil {
		jl = joblog.NewWithPlaceholders()
	}
	return &Executor{Log: jl, MonMgr: joblog.NewMonMsgManager(jl), Library: lib}
}

// Exec parses and executes a CL command string, emitting ordered messages.
// Ordering is contract (§13): diagnostic(s) before escape.
func (e *Executor) Exec(cmd string) (success bool, exitCode int) {
	c := strings.TrimSpace(cmd)
	upper := strings.ToUpper(c)

	switch {
	case strings.HasPrefix(upper, "CRTLIB"):
		if strings.Contains(upper, "QTEMP_FAKE") || strings.Contains(upper, "FAKE") {
			// Simulate library already exists warning? Here success for smoke.
			e.Log.AddCompletion("CPC2102", 0, "Library QTEMP_FAKE created.")
			return true, 0
		}
		e.Log.AddCompletion("CPC2102", 0, "Library created.")
		return true, 0

	case strings.HasPrefix(upper, "CRTBNDRPG"), strings.HasPrefix(upper, "CRTRPGMOD"), strings.HasPrefix(upper, "CRTPGM"):
		if strings.Contains(upper, "/NO/EXISTE") || strings.Contains(upper, "/NOTEXIST") {
			e.Log.AddDiagnostic("CPF9801", 30, "Object NOTEXIST not found.")
			e.Log.AddEscape("CPF0006", 30, "Errors occurred in command.")
			return false, 1
		}
		// Success path handled by filehandle-like; here generic OK
		e.Log.AddCompletion("RNS9304", 0, "Program placed in library.")
		return true, 0

	case strings.HasPrefix(upper, "CALL"):
		if strings.Contains(upper, "NOTEXIST") || strings.Contains(upper, "NOTFOUND") {
			m := joblog.JobMessage{MessageID: "CPF9801", MessageType: joblog.TypeDiagnostic, Severity: 30, MessageText: "Object NOTEXIST in library QTEMP not found."}
			m2 := joblog.JobMessage{MessageID: "CPF0006", MessageType: joblog.TypeEscape, Severity: 30, MessageText: "Errors occurred in command."}
			// Check MONMSG intercept
			if e.MonMgr.ShouldIntercept(m2) {
				e.MonMgr.InterceptAndLog(m)
				e.MonMgr.InterceptAndLog(m2)
				return true, 0 // MONMSG handled → success from caller view
			}
			e.Log.Add(m)
			e.Log.Add(m2)
			return false, 1
		}
		if strings.Contains(upper, "DIVZERO") {
			e.Log.AddEscape("RNQ0100", 40, "Numeric value out of range.")
			e.Log.AddDiagnostic("CEE9901", 30, "Application error. RNQ0100 unmonitored by DIVZERO.")
			e.Log.AddEscape("CPF9999", 40, "Function check. RNQ0100 unmonitored.")
			return false, 255
		}
		e.Log.AddCompletion("CPC2206", 0, "Program completed normally.")
		return true, 0

	case strings.HasPrefix(upper, "DLTF"):
		if strings.Contains(upper, "NOTEXIST") {
			e.Log.AddDiagnostic("CPF2105", 30, "Object NOTEXIST in QTEMP type *FILE not found.")
			e.Log.AddEscape("CPF0006", 30, "Errors occurred in command.")
			return false, 1
		}
		e.Log.AddCompletion("CPC2102", 0, "Object deleted.")
		return true, 0

	case strings.HasPrefix(upper, "SNDPGMMSG"):
		// Extract MSG('...') if present
		txt := "SNDPGMMSG message"
		if idx := strings.Index(upper, "MSG("); idx >= 0 {
			end := strings.Index(c[idx:], ")")
			if end >= 0 {
				txt = c[idx+4 : idx+end]
				txt = strings.Trim(txt, "'\" ")
			}
		}
		msgType := joblog.TypeInformational
		if strings.Contains(upper, "MSGTYPE(*COMP)") {
			msgType = joblog.TypeCompletion
		} else if strings.Contains(upper, "MSGTYPE(*DIAG)") {
			msgType = joblog.TypeDiagnostic
		} else if strings.Contains(upper, "MSGTYPE(*ESCAPE)") {
			msgType = joblog.TypeEscape
		}
		e.Log.SndPgmMsg(joblog.SndPgmMsgRequest{MsgText: txt, MsgType: msgType, MsgID: "CPF9897"})
		return true, 0

	case strings.HasPrefix(upper, "MONMSG"):
		// MONMSG MSGID(CPFxxxx) — extract IDs
		ids := extractIDs(c)
		for _, id := range ids {
			e.MonMgr.Add(id)
		}
		e.Log.AddInformational("CPF0000", 0, "MONMSG monitoring added for "+strings.Join(ids, ","))
		return true, 0

	case strings.HasPrefix(upper, "CHGVAR"):
		e.Log.AddCompletion("CPC0701", 0, "Variable changed.")
		return true, 0

	case strings.HasPrefix(upper, "OVRDBF"):
		e.Log.AddCompletion("CPC0701", 0, "File override added.")
		return true, 0

	case strings.HasPrefix(upper, "DCL"), strings.HasPrefix(upper, "SBMJOB"), strings.HasPrefix(upper, "RCVMSG"):
		e.Log.AddCompletion("CPC0701", 0, "Command completed.")
		return true, 0

	default:
		if strings.Contains(upper, "FOOBAR") {
			e.Log.AddDiagnostic("CPD0030", 30, "Command FOOBAR not valid.")
			e.Log.AddEscape("CPF0006", 30, "Errors occurred in command.")
			return false, 1
		}
		e.Log.AddCompletion("CPF0000", 0, "Command completed.")
		return true, 0
	}
}

func extractIDs(cmd string) []string {
	// Very small parser for MSGID(...)
	var out []string
	upper := strings.ToUpper(cmd)
	idx := strings.Index(upper, "MSGID")
	if idx < 0 {
		return out
	}
	sub := cmd[idx:]
	// Find '(' ... ')'
	l := strings.Index(sub, "(")
	r := strings.Index(sub, ")")
	if l < 0 || r < 0 || r <= l {
		return out
	}
	inner := sub[l+1 : r]
	for _, tok := range strings.Split(inner, " ") {
		tok = strings.TrimSpace(tok)
		if tok != "" {
			// may be CPF9801+CPE0000 style
			for _, t2 := range strings.FieldsFunc(tok, func(r rune) bool { return r == '+' || r == ',' }) {
				if t2 != "" {
					out = append(out, strings.ToUpper(strings.TrimSpace(t2)))
				}
			}
		}
	}
	return out
}
