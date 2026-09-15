// Package colectores defines the collection of observable system behavior on
// a real IBM i. Observables are the only things compared by the oracle: data,
// messages, indicators, job state, object resolution, locks, transactions and
// display output when applicable.
package colectores

// Observable types (Kinds) defined by the compatibility matrix (plan §20 and
// documentacion/03-matriz-compatibilidad.md).
const (
	KindDatos         = "datos"
	KindMensajes      = "mensajes"
	KindIndicadores   = "indicadores"
	KindJob           = "job"
	KindObjetos       = "objetos"
	KindLocks         = "locks"
	KindTransacciones = "transacciones"
	KindDisplay       = "display"
)

// Observable defines one normalized unit of comparison between the local
// simulation (iNative) and real IBM i. Only these observables are comparable.
//
// For kind `display`, Value carries a stable serialization of a
// DisplaySnapshot produced by the normalizer (see display.go).
type Observable struct {
	Kind  string // KindDatos | KindMensajes | ... | KindDisplay
	Name  string // observable identifier within its kind
	Value string // normalized value; strings or stable serializations of values
}

// Colector collects observables of a given kind from an IBM i session.
type Colector interface {
	Kind() string
	Colectar(conexion any) ([]Observable, error)
}
