// Command oraculo is the CLI entry point for the iNative external conformance
// oracle. It exposes the public contracts (versions, fixtures and the §20
// comparator) plus the Python discovery flow.
package main

import (
	"encoding/json"
	"fmt"
	"os"

	"oraculo/internal/comparador"
	"oraculo/internal/fixture"
	"oraculo/internal/runner"
)

func main() {
	args := os.Args[1:]
	if len(args) == 0 {
		usage()
		os.Exit(2)
	}
	switch args[0] {
	case "version":
		fmt.Println(runner.Version())
	case "fixture":
		if len(args) != 2 {
			fmt.Fprintln(os.Stderr, "uso: oraculo fixture <archivo.json>")
			os.Exit(2)
		}
		if err := cmdFixture(args[1]); err != nil {
			fmt.Fprintln(os.Stderr, "error:", err)
			os.Exit(1)
		}
	case "diff":
		if err := cmdDiff(args[1:]); err != nil {
			fmt.Fprintln(os.Stderr, "error:", err)
			os.Exit(1)
		}
	case "joblog":
		if err := cmdJobLog(args[1:]); err != nil {
			fmt.Fprintln(os.Stderr, "error:", err)
			os.Exit(1)
		}
	case "help", "-h", "--help":
		usage()
	default:
		usage()
		os.Exit(2)
	}
}

// cmdFixture carga y valida un fixture (§20), imprimiéndolo canonicalizado.
func cmdFixture(path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	f, err := fixture.Load(data)
	if err != nil {
		return fmt.Errorf("fixture inválido: %w", err)
	}
	out, err := fixture.Marshal(f)
	if err != nil {
		return err
	}
	fmt.Println(string(out))
	return nil
}

// cmdDiff compara snapshots esperados vs actuales usando el comparador §20.
//
//	oraculo diff --fixture fixture.json --expected e.json --actual a.json [--json]
func cmdDiff(args []string) error {
	var fpath, epath, apath string
	asJSON := false
	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "--fixture":
			i++
			fpath = args[i]
		case "--expected":
			i++
			epath = args[i]
		case "--actual":
			i++
			apath = args[i]
		case "--json":
			asJSON = true
		default:
			return fmt.Errorf("argumento desconocido: %s", args[i])
		}
	}
	if fpath == "" || epath == "" || apath == "" {
		return fmt.Errorf("uso: oraculo diff --fixture f.json --expected e.json --actual a.json [--json]")
	}

	f, err := fixture.LoadFile(fpath)
	if err != nil {
		return err
	}
	esperados, err := comparador.LeerSnapshots(epath)
	if err != nil {
		return err
	}
	actuales, err := comparador.LeerSnapshots(apath)
	if err != nil {
		return err
	}

	cmp := comparador.New(f.Compare, f.Ignore)
	res := cmp.CompararSnapshots(esperados, actuales)

	if asJSON {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		return enc.Encode(res)
	}

	fmt.Printf("fixture: %s\n", fpath)
	if res.PASS {
		fmt.Println("PASS")
		return nil
	}
	fmt.Printf("FAIL — %d divergencias:\n", len(res.Divergencias))
	for _, d := range res.Divergencias {
		fmt.Printf("  %s\n", d)
	}
	// Exit 1 para CI cuando hay divergencias (solo modo texto)
	if !asJSON {
		os.Exit(1)
	}
	return nil
}

// cmdJobLog compara JobLogs (contrato rico §19) — determinista, orden es contrato.
func cmdJobLog(args []string) error {
	if len(args) == 0 {
		return fmt.Errorf("uso: oraculo joblog <diff|replay> ...\n  oraculo joblog diff --expected fixtures/joblog/normalized/RPG-RUNTIME-001.json --actual <actual.json> [--json]\n  oraculo joblog replay <ID>")
	}
	switch args[0] {
	case "diff":
		var epath, apath string
		asJSON := false
		ignore := []string{}
		for i := 1; i < len(args); i++ {
			switch args[i] {
			case "--expected":
				i++
				if i < len(args) {
					epath = args[i]
				}
			case "--actual":
				i++
				if i < len(args) {
					apath = args[i]
				}
			case "--json":
				asJSON = true
			case "--ignore":
				i++
				if i < len(args) {
					ignore = append(ignore, args[i])
				}
			}
		}
		if epath == "" || apath == "" {
			return fmt.Errorf("uso: oraculo joblog diff --expected <fixture.json> --actual <actual.json> [--json]")
		}
		esperados, err := comparador.LeerJobLog(epath)
		if err != nil {
			return err
		}
		actuales, err := comparador.LeerJobLog(apath)
		if err != nil {
			return err
		}
		res := comparador.CompararJobLogs(esperados, actuales, ignore)
		if asJSON {
			enc := json.NewEncoder(os.Stdout)
			enc.SetIndent("", "  ")
			return enc.Encode(res)
		}
		if res.PASS {
			fmt.Println("PASS — JobLog contract coincide (orden + severidad + tipo verificados)")
			return nil
		}
		fmt.Printf("FAIL — %d divergencias JobLog:\n", len(res.Divergencias))
		for _, d := range res.Divergencias {
			fmt.Printf("  %s\n", d.Actual)
		}
		os.Exit(1)
		return nil
	case "replay":
		if len(args) < 2 {
			return fmt.Errorf("uso: oraculo joblog replay <ID>")
		}
		fmt.Printf("replay: usa python3 -m probe.joblog_recorder replay %s\n", args[1])
		return nil
	default:
		return fmt.Errorf("joblog subcomando desconocido: %s", args[0])
	}
}

func usage() {
	fmt.Print(`oraculo — iNative oráculo de conformidad contra IBM i

Uso (descubrimiento, Python):
  python -m probe.captura <fuente.rpgle> <nombre-json>   # captura snapshot dorado → esperado/
  python3 -m probe.joblog_recorder record --id JOBLOG-0001 --command "CALL PGM(QTEMP/X)"  # JobLog Recorder (Record)
  python3 -m probe.joblog_recorder replay JOBLOG-0001  # JobLog Replay (sin IBM i)

Uso (CLI Go):
  oraculo version    Muestra la versión del oráculo y del contrato
  oraculo fixture <f.json>   Valida e imprime un fixture (esquema §20)
  oraculo diff --fixture f.json --expected e.json --actual a.json [--json]
                     Compara snapshots de display esperados vs locales (comparador §20)
  oraculo joblog diff --expected fixtures/joblog/normalized/RPG-RUNTIME-001.json --actual actual.json [--json]
                     Compara JobLogs deterministas (ID, type, severity, orden, texto §19)
  oraculo joblog replay <ID>  Hint replay (delegado a Python recorder)
  oraculo help       Muestra esta ayuda

Estructura del repositorio:
  probe/          Python: descubrimiento (conect, runner, colectores, normalizar, captura)
                  probe/joblog_recorder.py  JobLog Recorder (INITIAL→FINAL→DIFF §4)
  fixtures/joblog/{raw,normalized,manifests}  Corpus IBM i (§14-§18)
  fixtures/       fuentes + manifest + snapshots esperados (exportados desde iNative)
  conformance/    suite de conformidad por familia de observables (plan §19)
  esperado/       resultados normalizados esperados (snapshots versionados)
  reportes/       informe de conformidad (coincidencias/divergencias)
  internal/       contratos Go (runner, colectores, normalizador, fixture, comparador, joblog)
`)
}
