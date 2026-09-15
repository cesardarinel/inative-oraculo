// Package main — inative-capturer: recolector autónomo contra IBM i real.
//
// Implementa el plan de documentacion/vscode.md: se conecta vía SSH a un
// IBM i real (PUB400), crea la biblioteca de pruebas, inyecta 4 fuentes RPGLE,
// ejecuta los comandos exactos de Code for IBM i, captura stdout/stderr +
// JobLog (QSYS2.JOBLOG_INFO) + EVFEVENT + Spool (listing) y genera
// especificacion JSON + Markdown listo para iNative.
//
// Uso:
//   cp capturer_config.json.example capturer_config.json  # rellena host/user/pass
//   go run ./cmd/capturer
//   go run ./cmd/capturer --config capturer_config.json --out especificaciones_ibmi.json --docs docs/COMPILADOR_IBM_I_ESPECIFICACIONES.md
//   go run ./cmd/capturer --dry-run   # genera JSON mock sin tocar IBM i (útil en CI)
//
package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	"golang.org/x/crypto/ssh"
)

// ---------- CONFIG ----------

type Config struct {
	Host     string `json:"host"`
	Port     int    `json:"port"`
	User     string `json:"user"`
	Password string `json:"password,omitempty"`
	KeyFile  string `json:"keyfile,omitempty"`
	Lib      string `json:"lib"`
	CCSID    int    `json:"ccsid"`
}

func defaultConfig() Config {
	return Config{Port: 22, Lib: "TESTINAT", CCSID: 37}
}

func loadConfig(path string) (Config, error) {
	cfg := defaultConfig()
	// intenta oracle.env primero si no existe json
	if path == "" {
		path = "capturer_config.json"
	}
	data, err := os.ReadFile(path)
	if err != nil {
		// fallback: env / oracle.env
		if os.IsNotExist(err) {
			// intenta oracle.env
			if envCfg, ok := loadOracleEnv(); ok {
				return envCfg, nil
			}
		}
		return cfg, fmt.Errorf("no se pudo leer %s: %w (crea capturer_config.json desde .example)", path, err)
	}
	if err := json.Unmarshal(data, &cfg); err != nil {
		return cfg, fmt.Errorf("json inválido %s: %w", path, err)
	}
	if cfg.Port == 0 {
		cfg.Port = 22
	}
	if cfg.CCSID == 0 {
		cfg.CCSID = 37
	}
	if cfg.Lib == "" {
		cfg.Lib = "TESTINAT"
	}
	return cfg, nil
}

func loadOracleEnv() (Config, bool) {
	// lee oracle.env si existe (formato KEY=VAL)
	cfg := defaultConfig()
	p := "oracle.env"
	b, err := os.ReadFile(p)
	if err != nil {
		return cfg, false
	}
	m := map[string]string{}
	for _, line := range strings.Split(string(b), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		kv := strings.SplitN(line, "=", 2)
		if len(kv) == 2 {
			m[strings.TrimSpace(kv[0])] = strings.TrimSpace(kv[1])
		}
	}
	if v := m["ORACLE_IBM_HOST"]; v != "" {
		cfg.Host = v
	}
	if v := m["ORACLE_IBM_PORT"]; v != "" {
		fmt.Sscanf(v, "%d", &cfg.Port)
	}
	if v := m["ORACLE_IBM_USER"]; v != "" {
		cfg.User = v
	}
	if v := m["ORACLE_IBM_PASSWORD"]; v != "" {
		cfg.Password = v
	}
	if v := m["ORACLE_IBM_LIB"]; v != "" {
		cfg.Lib = v
	}
	if v := m["ORACLE_IBM_CCSID"]; v != "" {
		fmt.Sscanf(v, "%d", &cfg.CCSID)
	}
	if cfg.Host == "" || cfg.User == "" {
		return cfg, false
	}
	return cfg, true
}

// ---------- ESTRUCTURAS DE CAPTURA ----------

type TestCase struct {
	Name       string   `json:"name"`
	SourceCode string   `json:"source_code"`
	ShouldFail bool     `json:"should_fail"`
	Commands   []string `json:"commands"`
}

type CaptureResult struct {
	TestCase  string          `json:"test_case"`
	Source    string          `json:"source_code"`
	ShouldFail bool           `json:"should_fail"`
	Commands  []CommandResult `json:"commands"`
	JobLog    []JobLogEntry   `json:"joblog"`
	EventFile []EventFileEntry `json:"evfevent"`
	SpoolData string          `json:"spool_data"`
	RawOutput string          `json:"raw_output"`
	OK        bool            `json:"ok"`
	Error     string          `json:"error,omitempty"`
}

type CommandResult struct {
	Command  string `json:"command"`
	Stdout   string `json:"stdout"`
	Stderr   string `json:"stderr"`
	ExitCode int    `json:"exit_code"`
}

type JobLogEntry struct {
	MessageID   string `json:"message_id"`
	Severity    int    `json:"severity"`
	MessageText string `json:"message_text"`
	FromLine    int    `json:"from_line"`
	FromColumn  int    `json:"from_column"`
}

type EventFileEntry struct {
	EvtType     string `json:"evt_type"`
	EvtLine     int    `json:"evt_line"`
	EvtColumn   int    `json:"evt_column"`
	EvtMsgID    string `json:"evt_msgid"`
	EvtMsgTxt   string `json:"evt_msgtxt"`
	EvtSeverity int    `json:"evt_severity"`
}

// ---------- 4 CASOS EMBEBIDOS ----------

func getTestCases() []TestCase {
	return []TestCase{
		{
			Name:       "HOLA",
			SourceCode: "**free\nctl-opt main(Main);\ndcl-proc Main;\n  dsply 'HOLA MUNDO ILE';\nend-proc;",
			ShouldFail: false,
			Commands: []string{
				"CRTBNDRPG PGM(&LIB/&N) SRCSTMF('/home/&USER/oracle/src/&L_&N.rpgle') OPTION(*EVENTF) DBGVIEW(*SOURCE) TGTCCSID(37)",
				"CRTRPGMOD MODULE(&LIB/&N) SRCFILE(&LIB/QRPGLESRC) SRCMBR(&N)",
			},
		},
		{
			Name:       "ERROR_SINT",
			SourceCode: "**free\nctl-opt main(Main);\ndcl-proc Main;\n  dsply 'HOLA   // Falta la comilla de cierre\nend-proc;",
			ShouldFail: true,
			Commands: []string{
				"CRTBNDRPG PGM(&LIB/&N) SRCSTMF('/home/&USER/oracle/src/&L_&N.rpgle') OPTION(*EVENTF)",
			},
		},
		{
			Name:       "ERROR_LINK",
			SourceCode: "**free\nctl-opt main(Main);\ndcl-pr FuncionInexistente extproc;\nend-pr;\ndcl-proc Main;\n  FuncionInexistente();\nend-proc;",
			ShouldFail: true,
			Commands: []string{
				"CRTBNDRPG PGM(&LIB/&N) SRCSTMF('/home/&USER/oracle/src/&L_&N.rpgle') OPTION(*EVENTF)",
			},
		},
		{
			Name:       "WARNING_TEST",
			SourceCode: "**free\nctl-opt main(Main);\ndcl-s MiVar char(10);\ndcl-proc Main;\n  MiVar = 'HOLA';\nend-proc;",
			ShouldFail: false,
			Commands: []string{
				"CRTBNDRPG PGM(&LIB/&N) SRCSTMF('/home/&USER/oracle/src/&L_&N.rpgle') OPTION(*EVENTF)",
			},
		},
	}
}

// ---------- SSH ----------

func connectSSH(cfg Config) (*ssh.Client, error) {
	var auth []ssh.AuthMethod
	if cfg.Password != "" {
		auth = append(auth, ssh.Password(cfg.Password))
	}
	if cfg.KeyFile != "" {
		key, err := os.ReadFile(cfg.KeyFile)
		if err != nil {
			return nil, fmt.Errorf("keyfile: %w", err)
		}
		signer, err := ssh.ParsePrivateKey(key)
		if err != nil {
			return nil, fmt.Errorf("parse key: %w", err)
		}
		auth = append(auth, ssh.PublicKeys(signer))
	}
	if len(auth) == 0 {
		return nil, fmt.Errorf("sin auth: define password o keyfile")
	}
	sshCfg := &ssh.ClientConfig{
		User:            cfg.User,
		Auth:            auth,
		HostKeyCallback: ssh.InsecureIgnoreHostKey(),
		Timeout:         30 * time.Second,
	}
	addr := fmt.Sprintf("%s:%d", cfg.Host, cfg.Port)
	client, err := ssh.Dial("tcp", addr, sshCfg)
	if err != nil {
		return nil, fmt.Errorf("dial %s: %w", addr, err)
	}
	return client, nil
}

func runCommand(client *ssh.Client, cmd string) CommandResult {
	// Usa PASE/QSH con system -b para que el listing llegue por stdout (probe/runner_ibmi.py:65)
	return runRaw(client, cmd)
}

func runRaw(client *ssh.Client, cmd string) CommandResult {
	sess, err := client.NewSession()
	if err != nil {
		return CommandResult{Command: cmd, Stderr: err.Error(), ExitCode: 255}
	}
	defer sess.Close()
	var outB, errB bytes.Buffer
	sess.Stdout = &outB
	sess.Stderr = &errB
	// QSH prefix: igual que probe/conect.py pero sin CHGCURLIB forzado (ya va en cmd si hace falta)
	err = sess.Run(cmd)
	code := 0
	if err != nil {
		if ee, ok := err.(*ssh.ExitError); ok {
			code = ee.ExitStatus()
		} else {
			code = 1
		}
	}
	return CommandResult{Command: cmd, Stdout: outB.String(), Stderr: errB.String(), ExitCode: code}
}

func runQSH(client *ssh.Client, cl string) CommandResult {
	// Envoltura QSH: system -b "..." para listing completo, system -s para CL normal
	if strings.HasPrefix(strings.ToUpper(strings.TrimSpace(cl)), "CRTBND") ||
		strings.HasPrefix(strings.ToUpper(strings.TrimSpace(cl)), "CRTRPG") ||
		strings.HasPrefix(strings.ToUpper(strings.TrimSpace(cl)), "CRTSQL") ||
		strings.HasPrefix(strings.ToUpper(strings.TrimSpace(cl)), "CRTDSPF") ||
		strings.HasPrefix(strings.ToUpper(strings.TrimSpace(cl)), "CRTPF") {
		return runRaw(client, fmt.Sprintf("system -b %q", cl))
	}
	return runRaw(client, fmt.Sprintf("system -s %q", cl))
}

// ---------- HELPERS IFS ----------

func ensureSrcPF(client *ssh.Client, lib, srcpf string) {
	runQSH(client, fmt.Sprintf("CRTSRCPF FILE(%s/%s) RCDLEN(112)", lib, srcpf))
}

func writeIFS(client *ssh.Client, path, content string) error {
	// Usa SFTP si disponible, si no fallback a printf via SSH
	sess, err := client.NewSession()
	if err != nil {
		return err
	}
	defer sess.Close()
	// mkdir -p
	runRaw(client, fmt.Sprintf("mkdir -p %s", filepath.Dir(path)))
	// Escribe via cat > path (escapando)
	sess2, err := client.NewSession()
	if err != nil {
		return err
	}
	defer sess2.Close()
	stdin, err := sess2.StdinPipe()
	if err != nil {
		return err
	}
	var outB bytes.Buffer
	sess2.Stdout = &outB
	sess2.Stderr = &outB
	if err := sess2.Start(fmt.Sprintf("cat > %s", path)); err != nil {
		return err
	}
	if _, err := io.WriteString(stdin, content); err != nil {
		return err
	}
	stdin.Close()
	return sess2.Wait()
}

// ---------- COLECCIÓN ----------

func substitute(cmd string, cfg Config, tc TestCase) string {
	r := strings.ReplaceAll(cmd, "&LIB", cfg.Lib)
	r = strings.ReplaceAll(r, "&N", tc.Name)
	r = strings.ReplaceAll(r, "&L", strings.ToLower(cfg.Lib))
	r = strings.ReplaceAll(r, "&USER", cfg.User)
	return r
}

var reRNF = regexp.MustCompile(`(?m)^\s*\*?(?P<cod>[A-Z]{3}\d{4})\s+(?P<sev>\d{1,2})\s+(?P<pos>[0-9A-Za-z]{1,6})\s+(?P<seq>\d{1,6})\s+(?P<txt>\S.*)$`)

func parseListingForJobLog(listing string) []JobLogEntry {
	var out []JobLogEntry
	for _, line := range strings.Split(listing, "\n") {
		m := reRNF.FindStringSubmatch(line)
		if m == nil {
			continue
		}
		cod := m[1]
		sev := 0
		fmt.Sscanf(m[2], "%d", &sev)
		seq := 0
		fmt.Sscanf(m[4], "%d", &seq)
		txt := strings.TrimSpace(m[5])
		// deduplicación simple por cod+seq+txt
		out = append(out, JobLogEntry{MessageID: cod, Severity: sev, MessageText: txt, FromLine: seq})
	}
	return out
}

func queryJobLog(client *ssh.Client, lib string) []JobLogEntry {
	// Intenta QSYS2.JOBLOG_INFO vía RUNSQL (PASE) con salida a STDOUT
	sql := fmt.Sprintf("SELECT MESSAGE_ID, SEVERITY, MESSAGE_TEXT, FROM_LINE, FROM_COLUMN FROM TABLE(QSYS2.JOBLOG_INFO('*')) WHERE MESSAGE_ID LIKE 'CP%%' OR MESSAGE_ID LIKE 'RNF%%' OR MESSAGE_ID LIKE 'CPD%%' ORDER BY ORDINAL_POSITION FETCH FIRST 100 ROWS ONLY")
	cmd := fmt.Sprintf("system \"RUNSQL SQL('%s') OUTPUT(*STDOUT)\"", strings.ReplaceAll(sql, "'", "''"))
	res := runRaw(client, cmd)
	// Parse salida tabular o línea a línea
	var entries []JobLogEntry
	// regex para líneas tipo: MESSAGE_ID  SEVERITY  MESSAGE_TEXT...
	re := regexp.MustCompile(`([A-Z]{3}\d{4})\s+(\d{1,2})\s+(.+)`)
	for _, line := range strings.Split(res.Stdout+"\n"+res.Stderr, "\n") {
		m := re.FindStringSubmatch(strings.TrimSpace(line))
		if m != nil {
			sev := 0
			fmt.Sscanf(m[2], "%d", &sev)
			entries = append(entries, JobLogEntry{MessageID: m[1], Severity: sev, MessageText: strings.TrimSpace(m[3])})
		}
	}
	_ = lib
	return entries
}

func queryEventFile(client *ssh.Client, lib, mbr string) []EventFileEntry {
	sql := fmt.Sprintf("SELECT EVT_TYPE, EVT_LINE, EVT_COLUMN, EVT_MSGID, EVT_MSGTXT, EVT_SEVERITY FROM %s.EVFEVENT WHERE MBRNAME='%s' ORDER BY EVT_LINE", lib, strings.ToUpper(mbr))
	// Intenta RUNSQL y parsea salida tabular
	cmd := fmt.Sprintf("system \"RUNSQL SQL('%s') OUTPUT(*STDOUT)\"", strings.ReplaceAll(sql, "'", "''"))
	res := runRaw(client, cmd)
	var out []EventFileEntry
	// salida RUNSQL *STDOUT es tabular con cabecera; buscamos líneas con E/W/I + número
	re := regexp.MustCompile(`(?m)^\s*([EWI])\s+(\d+)\s+(\d+)\s+([A-Z]{3}\d{4})\s+(.+?)\s+(\d+)\s*$`)
	for _, m := range re.FindAllStringSubmatch(res.Stdout, -1) {
		line := 0
		col := 0
		sev := 0
		fmt.Sscanf(m[2], "%d", &line)
		fmt.Sscanf(m[3], "%d", &col)
		fmt.Sscanf(m[6], "%d", &sev)
		out = append(out, EventFileEntry{EvtType: m[1], EvtLine: line, EvtColumn: col, EvtMsgID: m[4], EvtMsgTxt: strings.TrimSpace(m[5]), EvtSeverity: sev})
	}
	if len(out) == 0 {
		// fallback: intenta vía db2 si existe
		res2 := runRaw(client, fmt.Sprintf("db2 \"%s\"", sql))
		for _, m := range re.FindAllStringSubmatch(res2.Stdout, -1) {
			line := 0
			col := 0
			sev := 0
			fmt.Sscanf(m[2], "%d", &line)
			fmt.Sscanf(m[3], "%d", &col)
			fmt.Sscanf(m[6], "%d", &sev)
			out = append(out, EventFileEntry{EvtType: m[1], EvtLine: line, EvtColumn: col, EvtMsgID: m[4], EvtMsgTxt: strings.TrimSpace(m[5]), EvtSeverity: sev})
		}
	}
	return out
}

func executeTestCase(client *ssh.Client, cfg Config, tc TestCase) CaptureResult {
	result := CaptureResult{TestCase: tc.Name, Source: tc.SourceCode, ShouldFail: tc.ShouldFail}
	// 0) Prepara IFS + SRCPF
	ensureSrcPF(client, cfg.Lib, "QRPGLESRC")
	ifsPath := fmt.Sprintf("/home/%s/oracle/src/%s_%s.rpgle", cfg.User, strings.ToLower(cfg.Lib), strings.ToLower(tc.Name))
	if err := writeIFS(client, ifsPath, tc.SourceCode); err != nil {
		result.Error = fmt.Sprintf("writeIFS: %v", err)
	}
	// También escribe a SRCPF vía CPYFRMSTMF (ASCII→EBCDIC) para que CRT* con SRCFILE funcione si hace falta
	runRaw(client, fmt.Sprintf("system \"CPYFRMSTMF FROMSTMF('%s') TOMBR('/qsys.lib/%s.lib/QRPGLESRC.file/%s.mbr') MBROPT(*REPLACE)\"", ifsPath, strings.ToLower(cfg.Lib), strings.ToLower(tc.Name)))

	var spoolBuilder strings.Builder
	var rawBuilder strings.Builder
	for _, rawCmd := range tc.Commands {
		cmd := substitute(rawCmd, cfg, tc)
		// expande &L y &N ya hecho; los comandos del plan usan SRCSTMF por defecto
		res := runQSH(client, cmd)
		result.Commands = append(result.Commands, res)
		spoolBuilder.WriteString(res.Stdout)
		spoolBuilder.WriteString("\n")
		spoolBuilder.WriteString(res.Stderr)
		spoolBuilder.WriteString("\n")
		rawBuilder.WriteString(fmt.Sprintf("$ %s\n%s\n%s\n", cmd, res.Stdout, res.Stderr))
	}
	result.SpoolData = spoolBuilder.String()
	result.RawOutput = rawBuilder.String()

	// Heurística OK: exit 0 y sin RNF/CPF con sev>=20
	ok := true
	for _, c := range result.Commands {
		if c.ExitCode != 0 {
			ok = false
		}
		if strings.Contains(c.Stdout, "RNF") || strings.Contains(c.Stderr, "RNF") {
			// chequea sev
			for _, jl := range parseListingForJobLog(c.Stdout + "\n" + c.Stderr) {
				if jl.Severity >= 20 {
					ok = false
				}
			}
		}
	}
	result.OK = ok

	// 2) JobLog (SQL + fallback a parsing del spool)
	jl := queryJobLog(client, cfg.Lib)
	if len(jl) == 0 {
		jl = parseListingForJobLog(result.SpoolData)
	}
	result.JobLog = jl

	// 3) EVFEVENT
	result.EventFile = queryEventFile(client, cfg.Lib, tc.Name)

	// 4) Spool ya está en SpoolData (listing completo)
	return result
}

// ---------- GENERACIÓN DOCS ----------

func generateSpecs(results []CaptureResult, outPath string) error {
	var buf bytes.Buffer
	buf.WriteString("# Especificaciones de Compilador IBM i para iNative\n\n")
	buf.WriteString("> Generado automáticamente por `inative-capturer` (plan `documentacion/vscode.md`). **Fuente de verdad: IBM i real vía SSH.**\n\n")
	buf.WriteString(fmt.Sprintf("> Fecha: %s | Casos: %d\n\n", time.Now().UTC().Format(time.RFC3339), len(results)))
	buf.WriteString("## Índice\n\n1. [Comandos y Respuestas (Stdout)](#1-comandos-y-respuestas-stdout)\n2. [Esquema de EVFEVENT](#2-esquema-de-evfevent)\n3. [Mapeo JobLog](#3-mapeo-joblog-message_id--severity--texto)\n4. [Ejemplos de Spool](#4-ejemplos-de-spool-listing)\n5. [Scripts SQL para iNative (SQLite)](#5-scripts-sql-para-inative-sqlite)\n6. [Requisitos para Code for IBM i](#6-requisitos-para-code-for-ibm-i)\n\n---\n\n")
	buf.WriteString("## 1. Comandos y Respuestas (Stdout)\n\n")
	for _, r := range results {
		status := "✅ éxito"
		if r.ShouldFail {
			status = "❌ debe fallar"
		}
		if !r.OK && !r.ShouldFail {
			status += " (falló inesperadamente)"
		}
		if r.OK && r.ShouldFail {
			status += " (éxito inesperado)"
		}
		buf.WriteString(fmt.Sprintf("### Caso: %s (%s)\n\n", r.TestCase, status))
		buf.WriteString(fmt.Sprintf("**Fuente RPGLE** (`%s`):\n```rpgle\n%s\n```\n\n", r.TestCase, r.Source))
		for i, c := range r.Commands {
			buf.WriteString(fmt.Sprintf("**Comando %d enviado:**\n```\n%s\n```\n\n", i+1, c.Command))
			buf.WriteString("**Stdout capturado:**\n```\n")
			if strings.TrimSpace(c.Stdout) == "" {
				buf.WriteString("(vacío)\n")
			} else {
				buf.WriteString(truncate(c.Stdout, 4000))
				buf.WriteString("\n")
			}
			buf.WriteString("```\n\n")
			buf.WriteString("**Stderr:**\n```\n")
			if strings.TrimSpace(c.Stderr) == "" {
				buf.WriteString("(vacío)\n")
			} else {
				buf.WriteString(truncate(c.Stderr, 2000))
				buf.WriteString("\n")
			}
			buf.WriteString("```\n\n")
			buf.WriteString(fmt.Sprintf("**Exit code:** `%d`\n\n", c.ExitCode))
		}
		buf.WriteString("**JobLog:**\n\n")
		if len(r.JobLog) == 0 {
			buf.WriteString("(sin entradas — compilación limpia)\n\n")
		} else {
			buf.WriteString("| MESSAGE_ID | SEVERITY | FROM_LINE | MESSAGE_TEXT |\n|---|---|---|---|\n")
			for _, jl := range r.JobLog {
				buf.WriteString(fmt.Sprintf("| %s | %d | %d | %s |\n", jl.MessageID, jl.Severity, jl.FromLine, escapePipe(jl.MessageText)))
			}
			buf.WriteString("\n")
		}
		buf.WriteString("**EVFEVENT:**\n\n")
		if len(r.EventFile) == 0 {
			buf.WriteString("(no hay registros — solo aplica con `OPTION(*EVENTF)` y errores)\n\n")
		} else {
			buf.WriteString("| EVT_TYPE | EVT_LINE | EVT_COLUMN | EVT_MSGID | EVT_MSGTXT | EVT_SEVERITY |\n|---|---|---|---|---|---|\n")
			for _, e := range r.EventFile {
				buf.WriteString(fmt.Sprintf("| %s | %d | %d | %s | %s | %d |\n", e.EvtType, e.EvtLine, e.EvtColumn, e.EvtMsgID, escapePipe(e.EvtMsgTxt), e.EvtSeverity))
			}
			buf.WriteString("\n")
		}
		buf.WriteString("**Spool (QSYSPRT) — extracto:**\n```\n")
		snip := truncate(r.SpoolData, 3000)
		if strings.TrimSpace(snip) == "" {
			snip = "(vacío — sin spool, ver JobLog)"
		}
		buf.WriteString(snip)
		buf.WriteString("\n```\n\n---\n\n")
	}
	buf.WriteString("## 2. Esquema de EVFEVENT\n\n")
	buf.WriteString("Archivo físico `LIB/EVFEVENT` (un miembro por compilación, crítico para Code for IBM i):\n\n")
	buf.WriteString("| Columna | Tipo | Valores | Notas |\n|---|---|---|---|\n")
	buf.WriteString("| `EVT_TYPE` | `CHAR(1)` | `E`=error, `W`=warning, `I`=info | `sev>=30→E` |\n")
	buf.WriteString("| `EVT_LINE` | `INTEGER` | 1-indexed | **línea 1 = primera del fuente** |\n")
	buf.WriteString("| `EVT_COLUMN` | `INTEGER` | 0=general | columna 1-indexed |\n")
	buf.WriteString("| `EVT_MSGID` | `CHAR(7)` | `RNF7030`… | código IBM i |\n")
	buf.WriteString("| `EVT_MSGTXT` | `VARCHAR` | texto | mismo que listing |\n")
	buf.WriteString("| `EVT_SEVERITY` | `INTEGER` | 0/10/20/30 | 0=info, 10=w, 20=leve, 30=error |\n")
	buf.WriteString("| `MBRNAME` | `CHAR(10)` | miembro | clave de partición |\n")
	buf.WriteString("| `EVT_FILE` | `CHAR` | IFS vs SRCPF | `SRCSTMF`→ruta IFS |\n\n")
	buf.WriteString("Lectura que hace Code for IBM i:\n```sql\nSELECT EVT_TYPE, EVT_LINE, EVT_COLUMN, EVT_MSGID, EVT_MSGTXT FROM LIB.EVFEVENT WHERE MBRNAME='HOLA' ORDER BY EVT_LINE, EVT_COLUMN;\n```\n\n")
	buf.WriteString("## 3. Mapeo JobLog (MESSAGE_ID → SEVERITY → TEXTO)\n\n")
	// Agrega tabla combinada de todos los casos
	seen := map[string]JobLogEntry{}
	for _, r := range results {
		for _, jl := range r.JobLog {
			seen[jl.MessageID] = jl
		}
	}
	if len(seen) == 0 {
		buf.WriteString("_Sin mensajes capturados (ejecutar con errores para poblar)._ \n\n")
	} else {
		keys := make([]string, 0, len(seen))
		for k := range seen {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		buf.WriteString("| MESSAGE_ID | SEVERITY | MESSAGE_TEXT (ejemplo) |\n|---|---|---|\n")
		for _, k := range keys {
			jl := seen[k]
			buf.WriteString(fmt.Sprintf("| %s | %d | %s |\n", jl.MessageID, jl.Severity, escapePipe(truncate(jl.MessageText, 120))))
		}
		buf.WriteString("\n`0=info/éxito, 10=aviso, 20=error leve, 30=error, 40=escape` — ver `probe/colectores/joblog.py:34-39`.\n\n")
	}
	buf.WriteString("## 4. Ejemplos de Spool (Listing)\n\n")
	buf.WriteString("Patrón RPG (ver `probe/colectores/mensajes.py`):\n```\n*RNF7030 30      7 000007  The name or indicator VARNOMBRE is not defined.\n```\nPatrón DDS:\n```\n* CPD5238      30        1      Message . . . . :   No valid record found...\n```\n\n")
	buf.WriteString("## 5. Scripts SQL para iNative (SQLite)\n\n")
	buf.WriteString("```sql\n-- EVFEVENT\nCREATE TABLE IF NOT EXISTS evfevent (\n  id INTEGER PRIMARY KEY AUTOINCREMENT,\n  mbrname TEXT NOT NULL,\n  evt_type TEXT NOT NULL CHECK(evt_type IN ('E','W','I')),\n  evt_line INTEGER NOT NULL,\n  evt_column INTEGER NOT NULL DEFAULT 0,\n  evt_msgid TEXT NOT NULL,\n  evt_msgtxt TEXT NOT NULL,\n  evt_severity INTEGER NOT NULL,\n  evt_file TEXT,\n  created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))\n);\nCREATE INDEX idx_evfevent_mbr ON evfevent(mbrname, evt_line);\n\n-- JOBLOG\nCREATE TABLE IF NOT EXISTS joblog (\n  id INTEGER PRIMARY KEY AUTOINCREMENT,\n  message_id TEXT NOT NULL,\n  severity INTEGER NOT NULL,\n  message_text TEXT NOT NULL,\n  from_line INTEGER DEFAULT 0,\n  from_column INTEGER DEFAULT 0,\n  ordinal INTEGER\n);\n\n-- SPOOL\nCREATE TABLE IF NOT EXISTS spooled_files (\n  id INTEGER PRIMARY KEY AUTOINCREMENT,\n  job_name TEXT, spooled_file_name TEXT, data TEXT\n);\n```\n\n")
	buf.WriteString("## 6. Requisitos para Code for IBM i\n\n")
	buf.WriteString("- **Stdout** debe ser idéntico al IBM i real (incluida cabecera `5770WDS`) o el plugin no pinta errores.\n")
	buf.WriteString("- **EVT_LINE/COLUMN son 1-indexed.**\n")
	buf.WriteString("- **AST no va a EVFEVENT** — solo errores.\n")
	buf.WriteString("- **Spool en `spooled_files`** para `WRKSPLF`.\n\n")
	buf.WriteString("---\n\n*Autogenerado por `cmd/capturer` — si el JSON y este doc coinciden con PUB400, la simulación es indistinguible.*\n")

	if outPath == "" {
		outPath = "documentacion/COMPILADOR_IBM_I_ESPECIFICACIONES.md"
	}
	if err := os.MkdirAll(filepath.Dir(outPath), 0755); err != nil {
		return err
	}
	return os.WriteFile(outPath, buf.Bytes(), 0644)
}

func saveJSON(results []CaptureResult, outPath string) error {
	payload := map[string]any{
		"generated_at": time.Now().UTC().Format(time.RFC3339),
		"cases":        len(results),
		"results":      results,
	}
	data, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return err
	}
	if outPath == "" {
		outPath = "especificaciones_ibmi.json"
	}
	if err := os.MkdirAll(filepath.Dir(outPath), 0755); err != nil {
		return err
	}
	return os.WriteFile(outPath, data, 0644)
}

// ---------- UTILS ----------

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "\n…(truncado)"
}

func escapePipe(s string) string {
	return strings.ReplaceAll(s, "|", "\\|")
}

// ---------- MOCK (dry-run) ----------

func mockResults() []CaptureResult {
	return []CaptureResult{
		{
			TestCase: "HOLA", Source: "**free\nctl-opt main(Main);\ndcl-proc Main;\n  dsply 'HOLA';\nend-proc;", ShouldFail: false, OK: true,
			Commands: []CommandResult{{Command: "CRTBNDRPG PGM(TESTINAT/HOLA) SRCSTMF('/home/user/oracle/src/testinat_hola.rpgle') OPTION(*EVENTF)", Stdout: "5770WDS V7R5M0 210525\nProgram HOLA created in library TESTINAT.", ExitCode: 0}},
			JobLog: []JobLogEntry{{MessageID: "CPF0000", Severity: 0, MessageText: "*COMP Normal completion."}},
			SpoolData: "5770WDS V7R5M0 210525\n  1 **free\n  2 ctl-opt main(Main);\n",
		},
		{
			TestCase: "ERROR_SINT", Source: "**free\ndsply 'HOLA", ShouldFail: true, OK: false,
			Commands: []CommandResult{{Command: "CRTBNDRPG PGM(TESTINAT/ERROR_SINT) …", Stdout: "*RNF7030 30      4 000004  The name or indicator is not defined.\n*RNF7503 30      4 000004  Expression contains an operand that is not defined.", ExitCode: 1}},
			JobLog: []JobLogEntry{{MessageID: "RNF7030", Severity: 30, MessageText: "The name or indicator VARNOMBRE is not defined.", FromLine: 4}, {MessageID: "RNF7503", Severity: 30, MessageText: "Expression contains an operand that is not defined.", FromLine: 4}},
			EventFile: []EventFileEntry{{EvtType: "E", EvtLine: 4, EvtColumn: 0, EvtMsgID: "RNF7030", EvtMsgTxt: "The name or indicator VARNOMBRE is not defined.", EvtSeverity: 30}},
			SpoolData: "*RNF7030 30      4 000004  The name or indicator VARNOMBRE is not defined.",
		},
		{
			TestCase: "ERROR_LINK", Source: "**free\ndcl-pr NoExiste extproc;\nFuncionInexistente();", ShouldFail: true, OK: false,
			Commands: []CommandResult{{Command: "CRTBNDRPG PGM(TESTINAT/ERROR_LINK) …", Stdout: "*CPD0053 30 Diagnostic  Symbol FuncionInexistente not defined.", ExitCode: 1}},
			JobLog: []JobLogEntry{{MessageID: "CPD0053", Severity: 30, MessageText: "Symbol FuncionInexistente not defined. (CPF829B)"}},
			EventFile: []EventFileEntry{{EvtType: "E", EvtLine: 5, EvtColumn: 0, EvtMsgID: "CPD0053", EvtMsgTxt: "Symbol FuncionInexistente not defined.", EvtSeverity: 30}},
			SpoolData: "*CPD0053 30 a 000005 Symbol FuncionInexistente not defined.",
		},
		{
			TestCase: "WARNING_TEST", Source: "**free\ndcl-s MiVar char(1);\nMiVar='HOLA';", ShouldFail: false, OK: true,
			Commands: []CommandResult{{Command: "CRTBNDRPG PGM(TESTINAT/WARNING_TEST) …", Stdout: "*RNF worrying 10      3 000003  Value truncated.", ExitCode: 0}},
			JobLog: []JobLogEntry{{MessageID: "RNF0000", Severity: 10, MessageText: "Value truncated."}},
			EventFile: []EventFileEntry{{EvtType: "W", EvtLine: 3, EvtColumn: 0, EvtMsgID: "RNF0000", EvtMsgTxt: "Value truncated.", EvtSeverity: 10}},
			SpoolData: "*RNF0000 10      3 000003  Value truncated.",
		},
	}
}

// ---------- MAIN ----------

func main() {
	var (
		cfgPath  = flag.String("config", "capturer_config.json", "ruta a capturer_config.json (fallback oracle.env)")
		outJSON  = flag.String("out", "especificaciones_ibmi.json", "salida JSON crudo")
		outDocs  = flag.String("docs", "documentacion/COMPILADOR_IBM_I_ESPECIFICACIONES.md", "salida Markdown generado")
		dryRun   = flag.Bool("dry-run", false, "no conecta a IBM i; genera JSON mock para probar el pipeline")
		listOnly = flag.Bool("list", false, "lista los 4 casos embebidos y sale")
	)
	flag.Parse()

	if *listOnly {
		for _, tc := range getTestCases() {
			j, _ := json.MarshalIndent(tc, "", "  ")
			fmt.Println(string(j))
		}
		return
	}

	if *dryRun {
		log.Println("[capturer] --dry-run: generando mock sin IBM i")
		results := mockResults()
		if err := saveJSON(results, *outJSON); err != nil {
			log.Fatal(err)
		}
		if err := generateSpecs(results, *outDocs); err != nil {
			log.Fatal(err)
		}
		fmt.Printf("✅ dry-run completado: %s + %s\n", *outJSON, *outDocs)
		return
	}

	cfg, err := loadConfig(*cfgPath)
	if err != nil {
		log.Fatalf("config: %v", err)
	}
	if cfg.Host == "" || cfg.User == "" {
		log.Fatalf("config incompleta: host=%q user=%q (rellena %s o oracle.env)", cfg.Host, cfg.User, *cfgPath)
	}
	log.Printf("[capturer] conectando a %s:%d como %s lib=%s ...", cfg.Host, cfg.Port, cfg.User, cfg.Lib)

	client, err := connectSSH(cfg)
	if err != nil {
		log.Fatalf("SSH: %v", err)
	}
	defer client.Close()
	log.Println("[capturer] SSH conectado")

	// Crea lib + SRCPF
	log.Printf("[capturer] CRTLIB %s", cfg.Lib)
	runQSH(client, fmt.Sprintf("CRTLIB LIB(%s) TYPE(*TEST)", cfg.Lib))
	ensureSrcPF(client, cfg.Lib, "QRPGLESRC")

	testCases := getTestCases()
	var results []CaptureResult
	for _, tc := range testCases {
		log.Printf("[capturer] caso %s (shouldFail=%v) ...", tc.Name, tc.ShouldFail)
		res := executeTestCase(client, cfg, tc)
		results = append(results, res)
		log.Printf("[capturer]  → %s ok=%v jobs=%d evf=%d spool=%dB", tc.Name, res.OK, len(res.JobLog), len(res.EventFile), len(res.SpoolData))
	}

	if err := saveJSON(results, *outJSON); err != nil {
		log.Fatal(err)
	}
	if err := generateSpecs(results, *outDocs); err != nil {
		log.Fatal(err)
	}
	fmt.Printf("✅ Captura completada. JSON: %s  Docs: %s\n", *outJSON, *outDocs)
}
