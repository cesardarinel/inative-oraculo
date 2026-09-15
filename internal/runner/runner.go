// Package runner defines the top-level contract of the conformance oracle:
// it consumes published fixtures from iNative, runs the equivalent on a real
// IBM i through the ibmi-runner, normalizes the collected observables and
// produces a conformance report.
//
// The oracle is intentionally decoupled from local development. It must be
// safe for this package to disappear without affecting iNative local builds.
package runner

import "oraculo/internal/version"

// Result is the outcome of running one oracle case.
type Result struct {
	Fixtures     string   // path to the fixture under evaluation
	Observables  []string // normalized observables collected on IBM i
	Divergencias []string // list of divergences found, empty on PASS
	PASS         bool     // whether the case matched the expected snapshot
}

// Runner executes a set of oracle cases against a real IBM i.
type Runner interface {
	Run(casos []string) ([]Result, error)
	Report() ([]byte, error)
}

// Version returns the oracle CLI version and the contract version it honors.
func Version() string {
	return version.Cli()
}
