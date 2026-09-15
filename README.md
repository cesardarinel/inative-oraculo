# iNative-oraculo

Oráculo externo para **iNative**: se conecta a un **IBM i real**, ejecuta
*fixtures* equivalentes y **captura snapshots JSON "dorados"** que indican a
iNative **exactamente qué simular** (mensajes, datos, indicadores, estado de
*job*, resolución de objetos, *locks*, transacciones, *display*).

> El oráculo **no se distribuye con el producto** ni se convierte en
> dependencia de compilación o de ejecución local. Su única misión es
> determinar y validar el comportamiento que el runtime local debe
> reproducir. Puede desaparecer y el desarrollo local (`inative run`,
> `inative serve`, `inative test --local`) debe seguir funcionando por
> completo.

## Estado

**Descubrimiento primero** (vertical 1 en curso): captura de mensajes de
compilación (RNF) y catálogo contra PUB400. Implementado en **Python**
(probing rápido) con esqueleto Go de contratos:

- Estructura según `001.md` (fixtures, runner, colectores, normalizador,
  esperado, reportes).
- Conexión SSH+SFTP+ODBC a IBM i real (`probe/`).
- Runner `CRTBNDRPG` + colector de listing + normalizador + orquestador
  que emite `esperado/<fixture>.json`.

**Alineación con el plan maestro** (aplicada): contratos Go para el
**DisplaySnapshot** semántico (§9.2/§18) en `internal/colectores`, el esquema
de **fixture JSON** (§20) en `internal/fixture`, y el **comparador**
PASS/FAIL + divergencias (§20) en `internal/comparador`. Suite de conformidad
por familia de observables en `conformance/` (§19), con el caso de referencia
`HELLO-5250-001` (§9.3). CLI expone `fixture` y `diff`.

## Estructura

```
iNative-oraculo/
├── fixtures/         fuentes + manifest + snapshots esperados (exportados desde iNative)
├── conformance/      suite de conformidad por familia de observables (plan maestro §19)
├── probe/            Python: descubrimiento (config, conect, runner_ibmi,
│                     colectores/, normalizar, captura)
│   └── colectores/   observables por kind (catalogo, mensajes, display, …)
├── esperado/         snapshots dorados capturados de IBM i (versionados)
│                     └── HELLO-5250-001.screens.json  (DisplaySnapshot §9.2, ilustrativo)
├── reportes/         informe de conformidad (coincidencias/divergencias)
├── oraculo/          CLI Go (binario oraculo)
├── internal/         contratos Go (runner, colectores, normalizador, fixture, comparador, version)
├── oracle.env.example  plantilla de conexión (host/release/user/lib) — committed
├── oracle.env          credenciales reales — NO versionado
└── documentacion/    documentación del oráculo
```

> Los nombres `ibmi-runner/`, `colectores/`, `normalizador/` de `001.md`
> corresponden en la implementación a `probe/runner_ibmi.py`,
> `probe/colectores/` y `probe/normalizar.py` (y a los contratos en
> `internal/`).

La comparación de pantallas utiliza el **DisplaySnapshot** semántico
(plan §9.2/§18) en `internal/colectores`, el esquema de **fixture JSON** (§20)
en `internal/fixture` y el **comparador** PASS/FAIL + divergencias (§20) en
`internal/comparador`, honrando el conjunto `compare`/`ignore` de cada caso.


## Relación con iNative (contrato)

`iNative` publica el **fixture + manifest + versión del contrato**; el
oráculo ejecuta el fixture equivalente en IBM i y devuelve un resultado
**normalizado**. La comparación usa únicamente los observables definidos
por la **matriz de compatibilidad**: datos, mensajes, indicadores, estado
de job, resolución de objetos, locks, transacciones y salida de display
cuando aplique. Este repositorio mantiene sus propias credenciales,
conexiones y automatización de IBM i, **fuera** del repositorio central.

## Uso

Descubrimiento (Python; requiere `oracle.env` con la conexión y
`pip install -r requirements.txt`):

```bash
python -m probe.captura fixtures/RPGLE/invalidos/var-no-declarada.rpgle RPGLE.invalidos.var-no-declarada
# genera esperado/RPGLE.invalidos.var-no-declarada.json
```

CLI Go (esqueleto):

```bash
make build              # compila ./binario/oraculo
./binario/oraculo version
./binario/oraculo fixture conformance/dspf/HELLO-5250-001.json   # valida fixture §20
./binario/oraculo diff --fixture f.json --expected e.json --actual a.json [--json]
./binario/oraculo help
```

## Comandos de desarrollo

```bash
make test         # go test ./...
make vet          # go vet ./...
make help         # lista de comandos
```

## Documentación

Índice en [`documentacion/`](documentacion/):

0. [Índice y mapa](documentacion/00-indice.md)
1. [Visión y misión del oráculo](documentacion/01-vision.md)
2. [Contrato entre repositorios](documentacion/02-contrato.md)
3. [Matriz de compatibilidad (observables)](documentacion/03-matriz-compatibilidad.md)
4. [Fixtures](documentacion/04-fixtures.md)
5. [Runner IBM i](documentacion/05-ibmi-runner.md)
6. [Colectores](documentacion/06-colectores.md)
7. [Normalizador](documentacion/07-normalizador.md)
8. [Snapshots esperados](documentacion/08-esperado.md)
9. [Informes de conformidad](documentacion/09-reportes.md)
10. [Plan de implementación](documentacion/10-plan.md)
11. [Diseño del oráculo (Python)](documentacion/diseno-oracle-python.md)

## Nota legal

Desarrollo bajo enfoque *clean-room* basado únicamente en documentación
pública. No se incluye código propietario de IBM. El oráculo no es un
producto oficial de IBM.
# inative-oraculo
