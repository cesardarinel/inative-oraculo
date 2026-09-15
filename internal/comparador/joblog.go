package comparador

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"oraculo/internal/joblog"
)

// LeerJobLogLee mensajes esperados/actuales desde envoltorios esperado/*.json (observables kind joblog)
// Soporta dos formatos: joblog_v2/normalized raw fixture (joblog.messages) y legacy observables.
func LeerJobLog(path string) ([]joblog.JobMessage, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	// Intento 1: fixture normalizado JobLog {joblog:{messages:[...]}}
	var fj joblog.Fixture
	if err := json.Unmarshal(data, &fj); err == nil && len(fj.JobLog.Messages) > 0 {
		return fj.JobLog.Messages, nil
	}
	// Intento 2: legado esperado {observables:[{kind:joblog,value:[...]}]}
	var wrapper struct {
		Observables []struct {
			Kind  string          `json:"kind"`
			Value json.RawMessage `json:"value"`
		} `json:"observables"`
	}
	if err := json.Unmarshal(data, &wrapper); err == nil {
		for _, o := range wrapper.Observables {
			if strings.ToLower(o.Kind) == "joblog" || strings.ToLower(o.Kind) == "joblog_v2" {
				// value es []JobMessage o []map con id/sev/text
				var msgs []joblog.JobMessage
				if err := json.Unmarshal(o.Value, &msgs); err == nil && len(msgs) > 0 {
					return msgs, nil
				}
				// Prueba formato legacy plano [{id,sev,text}]
				var legacy []struct {
					ID   string `json:"id"`
					Sev  int    `json:"sev"`
					Text string `json:"text"`
				}
				if err := json.Unmarshal(o.Value, &legacy); err == nil {
					out := make([]joblog.JobMessage, len(legacy))
					for i, l := range legacy {
						out[i] = joblog.JobMessage{
							MessageID:       strings.ToUpper(l.ID),
							MessageType:     joblog.UnknownType,
							Severity:        l.Sev,
							MessageText:     l.Text,
							OrdinalPosition: i + 1,
						}
					}
					return out, nil
				}
			}
		}
	}
	// Intento 3: array directo []JobMessage
	var direct []joblog.JobMessage
	if err := json.Unmarshal(data, &direct); err == nil && len(direct) > 0 {
		return direct, nil
	}
	return nil, fmt.Errorf("no se pudo leer JobLog desde %s", path)
}

// CompararJobLogs usa el contrato de joblog.AssertEqual (ID, type, severity, ordinal, text)
func CompararJobLogs(esperados, actuales []joblog.JobMessage, ignore []string) Resultado {
	diffs := joblog.AssertEqual(esperados, actuales)
	// Filtra ignore (paths que contienen token ignorado)
	ignoreLow := make([]string, len(ignore))
	for i, s := range ignore {
		ignoreLow[i] = strings.ToLower(strings.TrimSpace(s))
	}
	var filtered []Divergencia
	for _, d := range diffs {
		low := strings.ToLower(d)
		skip := false
		for _, ig := range ignoreLow {
			if ig != "" && strings.Contains(low, ig) {
				skip = true
				break
			}
		}
		if !skip {
			filtered = append(filtered, Divergencia{Path: "joblog", Esperado: "", Actual: d})
		}
	}
	if len(filtered) == 0 && len(diffs) == 0 {
		return Resultado{PASS: true}
	}
	if len(filtered) == 0 && len(diffs) > 0 {
		// todo ignorado → PASS
		return Resultado{PASS: true}
	}
	return Resultado{Divergencias: filtered, PASS: false}
}
