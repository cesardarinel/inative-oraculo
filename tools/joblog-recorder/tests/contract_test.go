package tests

import (
	"path/filepath"
	"testing"

	"oraculo/internal/joblog"
)

// Tests miran al corpus normalizado como spec ejecutable (Replay sin IBM i)
func TestToolsCorpus_Replay(t *testing.T) {
	for _, p := range []string{
		"../../fixtures/joblog/normalized/RPG-RUNTIME-001.json",
		"../../inative-mock-data/normalized/RPG-RUNTIME-001.json",
	} {
		fix, err := joblog.LoadFixture(p)
		if err != nil {
			continue
		}
		if len(fix.JobLog.Messages) == 0 {
			t.Errorf("%s vacío", p)
		}
		t.Logf("ok %s: %d msgs", filepath.Base(p), len(fix.JobLog.Messages))
		break
	}
}
