// Package version centraliza la versión del oráculo y del contrato.
package version

import "fmt"

// Version del CLI del oráculo.
const Version = "v0.0.1"

// ContratoVersion es la versión del contrato entre iNative (publica fixtures
// + manifest) y el oráculo (ejecuta el equivalente en IBM i y devuelve un
// resultado normalizado).
const ContratoVersion = "1"

// Cli devuelve una descripción corta usada por el punto de entrada CLI.
func Cli() string {
	return fmt.Sprintf("iNative oráculo de conformidad %s (contrato %s)", Version, ContratoVersion)
}
