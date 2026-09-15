// Command recorder — wrapper Go para tools/joblog-recorder (plan §20).
// Delega a Python probe.joblog_recorder pero expone binario Go tipado.
package main

import (
	"fmt"
	"os"
	"os/exec"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("uso: recorder <record|replay|list|record-matrix> [flags]")
		fmt.Println("  record --id JOBLOG-0001 --command \"CALL PGM(QTEMP/X)\"")
		fmt.Println("  replay JOBLOG-0001")
		fmt.Println("  list")
		os.Exit(2)
	}
	// Delegación a Python (single source of truth)
	args := append([]string{"-m", "probe.joblog_recorder"}, os.Args[1:]...)
	cmd := exec.Command("python3", args...)
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		if ee, ok := err.(*exec.ExitError); ok {
			os.Exit(ee.ExitCode())
		}
		fmt.Fprintln(os.Stderr, "recorder error:", err)
		os.Exit(1)
	}
}
