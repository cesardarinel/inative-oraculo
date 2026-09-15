# esperado/

Snapshots "dorados" capturados de un IBM i real. Son generados por
`python -m probe.captura`, versionados y consumidos por iNative como verdad
de referencia (ver `documentacion/08-esperado.md`).

## Formatos

- **Mensajes de compilación** (vertical 1): observables `kind: "mensajes"`
  con `name` (código RNF/R...), `severidad`, `linea`, `col`, `value`, `norm`.
- **Pantallas / display** (plan §9.2, §18): observables `kind: "display"`
  que embeben un `DisplaySnapshot` semántico (`screen`, `cursor`, `fields`,
  `indicators`, `response_key`). Se comparan con `internal/comparador`
  respetando el conjunto `compare` e `ignore` del fixture.

## Reglas

- Versionados y reproducibles; objeto de comparación determinista.
- Nunca contienen credenciales.
- Comparan únicamente observables de la matriz de compatibilidad.
