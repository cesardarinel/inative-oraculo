¡Perfecto! Quieres que el **programador desarrolle un "recolector de datos" autónomo** que, al ejecutarse una sola vez, se conecte al IBM i real, ejecute una batería de pruebas predefinida, capture **absolutamente todo** lo que devuelve el sistema y genere un documento de especificaciones listo para que el equipo de iNative lo implemente.

Aquí tienes el **plan de ingeniería para ese recolector** (que llamaremos `inative-capturer`). El programador solo tendrá que escribirlo, configurar la conexión y ejecutarlo. El resto es 100% automático.

---

# PLAN: CONSTRUCCIÓN DEL "RECOLECTOR AUTÓNOMO" PARA iNATIVE

## 1. Objetivo del Recolector
Desarrollar un binario/script en **Go** (para que sea fácil de integrar con iNative) que:
- Se conecte vía **SSH** a un IBM i real.
- Cree una biblioteca temporal de pruebas (o use una existente).
- Inyecte **4 fuentes de prueba** (casos de éxito, error de sintaxis, error de enlace, y warning).
- Ejecute los comandos **exactos** que usa la extensión Code for IBM i.
- Capture:
  1. **Stdout/Stderr** de la sesión SSH.
  2. **JobLog** completo via `QSYS2.JOBLOG_INFO`.
  3. **EVFEVENT** (tabla de errores estructurados).
  4. **Spool de compilación** (QSYSPRT).
- Genere un archivo `especificaciones_ibmi.json` y un `docs/COMPILADOR_IBM_I_ESPECIFICACIONES.md` con **mapeos exactos** para iNative.

---

## 2. Estructura del Código (El Programa en Go)

El programador debe crear un paquete `cmd/capturer/main.go` con esta arquitectura:

```go
// cmd/capturer/main.go

package main

import (
    "encoding/json"
    "fmt"
    "log"
    "os"
    "time"
    "golang.org/x/crypto/ssh"
)

// ---------- CONFIGURACIÓN ----------
type Config struct {
    Host     string `json:"host"`
    User     string `json:"user"`
    Password string `json:"password,omitempty"`
    KeyFile  string `json:"keyfile,omitempty"`
    Lib      string `json:"lib"` // Ej: "TESTINAT"
}

// ---------- ESTRUCTURAS DE CAPTURA ----------
type TestCase struct {
    Name        string   // "HOLA", "ERROR_SINT", "ERROR_LINK"
    SourceCode  string   // Código RPGLE
    ShouldFail  bool     // ¿Esperamos error?
    Commands    []string // Comandos a ejecutar (ej. CRTBNDRPG)
}

type CaptureResult struct {
    TestCase   string
    Commands   []CommandResult
    JobLog     []JobLogEntry
    EventFile  []EventFileEntry
    SpoolData  string
    RawOutput  string
}

type CommandResult struct {
    Command string
    Stdout  string
    Stderr  string
    ExitCode int
}

type JobLogEntry struct {
    MessageID   string `json:"message_id"`
    Severity    int    `json:"severity"`
    MessageText string `json:"message_text"`
    FromLine    int    `json:"from_line"`
    FromColumn  int    `json:"from_column"`
}

type EventFileEntry struct {
    EvtType   string `json:"evt_type"`   // E, W, I
    EvtLine   int    `json:"evt_line"`
    EvtColumn int    `json:"evt_column"`
    EvtMsgId  string `json:"evt_msgid"`
    EvtMsgTxt string `json:"evt_msgxt"`
    EvtSeverity int  `json:"evt_severity"`
}

// ---------- LÓGICA PRINCIPAL ----------
func main() {
    // 1. Cargar config (host, user, pass)
    cfg := loadConfig("capturer_config.json")

    // 2. Conectar SSH al IBM i
    client := connectSSH(cfg)

    // 3. Crear biblioteca de pruebas
    runCommand(client, fmt.Sprintf("CRTLIB LIB(%s) TYPE(*TEST)", cfg.Lib))
    runCommand(client, fmt.Sprintf("CRTSRCPF FILE(%s/QRPGLESRC) RCDLEN(112)", cfg.Lib))

    // 4. Ejecutar todos los casos de prueba
    testCases := getTestCases()
    results := []CaptureResult{}
    for _, tc := range testCases {
        res := executeTestCase(client, cfg.Lib, tc)
        results = append(results, res)
    }

    // 5. Generar documentación
    generateSpecs(results, "docs/COMPILADOR_IBM_I_ESPECIFICACIONES.md")
    saveJSON(results, "especificaciones_ibmi.json")

    fmt.Println("✅ Captura completada. Documentación generada.")
}
```

---

## 3. Los 4 Casos de Prueba que Debe Embeber

El programador debe incrustar estos códigos fuente como strings en el binario:

| Caso | Nombre | Código | Propósito |
|------|--------|--------|-----------|
| **1** | `HOLA` | `**free; ctl-opt main(Main); dcl-proc Main; dsply 'HOLA'; end-proc;` | Capturar salida exitosa (CPF0000). |
| **2** | `ERROR_SINT` | `**free; ctl-opt main(Main); dsply 'HOLA` (falta cierre de comilla) | Capturar EVFEVENT con error de sintaxis (RNF7030). |
| **3** | `ERROR_LINK` | `**free; dcl-pr NoExiste extproc; end-pr; dcl-proc Main; NoExiste(); end-proc;` | Capturar error de enlace (CPF829B). |
| **4** | `WARNING_TEST` | `**free; dcl-s MiVar char(1); dcl-proc Main; MiVar = 'HOLA'; end-proc;` | Capturar warnings (RNFXXXX). |

---

## 4. Función `executeTestCase` (El Corazón del Recolector)

Esta función debe hacer **exactamente** lo que hace la extensión:

```go
func executeTestCase(client *ssh.Client, lib string, tc TestCase) CaptureResult {
    result := CaptureResult{TestCase: tc.Name}

    for _, cmd := range tc.Commands {
        // Reemplazar placeholders
        cmd = strings.ReplaceAll(cmd, "&LIB", lib)
        cmd = strings.ReplaceAll(cmd, "&N", tc.Name)

        // 1. Ejecutar el comando
        stdout, stderr, code := runCommand(client, cmd)
        result.Commands = append(result.Commands, CommandResult{
            Command: cmd,
            Stdout:  stdout,
            Stderr:  stderr,
            ExitCode: code,
        })
    }

    // 2. Capturar JobLog
    jobLogSQL := `
    SELECT MESSAGE_ID, SEVERITY, MESSAGE_TEXT, FROM_LINE, FROM_COLUMN
    FROM TABLE(QSYS2.JOBLOG_INFO('*')) 
    WHERE JOB_NAME = QSYS2.JOB_NAME 
      AND (MESSAGE_ID LIKE 'CPF%' OR MESSAGE_ID LIKE 'RNF%' OR MESSAGE_ID LIKE 'CPD%')
    ORDER BY ORDINAL_POSITION`
    result.JobLog = queryJobLog(client, jobLogSQL)

    // 3. Capturar EVFEVENT (crítico para VS Code)
    eventSQL := fmt.Sprintf("SELECT * FROM %s.EVFEVENT WHERE MBRNAME = '%s'", lib, tc.Name)
    result.EventFile = queryEventFile(client, eventSQL)

    // 4. Capturar Spool
    spoolSQL := fmt.Sprintf(`
    SELECT DATA FROM TABLE(QSYS2.SPOOLED_FILE_INFO('*ALL', '*ALL', '%s', '*CURRENT'))
    WHERE SPOOLED_FILE_NAME LIKE '%s%%'`, lib, tc.Name)
    result.SpoolData = querySpool(client, spoolSQL)

    return result
}
```

---

## 5. Comandos Exactos a Probar (Los que usa la extensión)

La extensión Code for IBM i ejecuta estos comandos típicamente:

```go
func getTestCases() []TestCase {
    return []TestCase{
        {
            Name: "HOLA",
            SourceCode: "**free; ctl-opt main(Main); dcl-proc Main; dsply 'HOLA'; end-proc;",
            ShouldFail: false,
            Commands: []string{
                // 1. Compilación normal
                "CRTBNDRPG PGM(&LIB/&N) SRCFILE(&LIB/QRPGLESRC) SRCMBR(&N) OPTION(*EVENTF) DBGVIEW(*SOURCE)",
                // 2. Compilación solo a módulo
                "CRTRPGMOD MODULE(&LIB/&N) SRCFILE(&LIB/QRPGLESRC) SRCMBR(&N)",
            },
        },
        {
            Name: "ERROR_SINT",
            SourceCode: "**free; ctl-opt main(Main); dsply 'HOLA",
            ShouldFail: true,
            Commands: []string{
                "CRTBNDRPG PGM(&LIB/&N) SRCFILE(&LIB/QRPGLESRC) SRCMBR(&N) OPTION(*EVENTF)",
            },
        },
        // ... similares para ERROR_LINK y WARNING_TEST
    }
}
```

---

## 6. Generación de Documentación Automática

La función `generateSpecs` debe crear un Markdown con:

1. **Tabla de Mapeo de Comandos**: Comando enviado → Stdout esperado.
2. **Esquema EVFEVENT**: Columnas y tipos de datos.
3. **Mapeo JobLog**: `MESSAGE_ID` → `SEVERITY` → `TEXTO`.
4. **Ejemplos de Spool**: Cómo se ve el listado de compilación.
5. **Scripts SQL para iNative**: Cómo crear las tablas `EVFEVENT`, `JOBLOG` y `SPOOL` en SQLite.

**Estructura del archivo Markdown**:

```markdown
# Especificaciones de Compilador IBM i para iNative

## 1. Comandos y Respuestas (Stdout)

### Caso: Compilación exitosa (HOLA)
**Comando enviado**:
`CRTBNDRPG PGM(TESTINAT/HOLA) ...`

**Stdout capturado**:
```
Program HOLA created in library TESTINAT.
```

**JobLog**:
| MESSAGE_ID | SEVERITY | MESSAGE_TEXT |
|------------|----------|--------------|
| CPF0000    | 0        | *COMP Normal completion. |

**EVFEVENT**:
(No hay registros para éxito)

---

## 2. Esquema de EVFEVENT (Errores en línea)
...
```

---

## 7. Instrucciones para el Programador (Setup)

1. **Crear el archivo `capturer_config.json`**:
   ```json
   {
       "host": "pub400.com",
       "user": "MIUSUARIO",
       "password": "MIPASS",
       "keyfile": "",
       "lib": "TESTINAT"
   }
   ```

2. **Ejecutar**:
   ```bash
   go mod init inative-capturer
   go get golang.org/x/crypto/ssh
   go run cmd/capturer/main.go
   ```

3. **Resultados**:
   - `especificaciones_ibmi.json` → Datos crudos (para depuración).
   - `docs/COMPILADOR_IBM_I_ESPECIFICACIONES.md` → Documento listo para el equipo de iNative.

---

## 8. Resumen de Entregables para el Programador

| Archivo | Propósito |
|---------|-----------|
| `cmd/capturer/main.go` | Código fuente del recolector. |
| `capturer_config.json` | Configuración de conexión (no se sube al repo). |
| `go.mod` / `go.sum` | Dependencias (ssh, etc.). |
| `docs/COMPILADOR_IBM_I_ESPECIFICACIONES.md` | Documento final generado automáticamente. |
| `especificaciones_ibmi.json` | Backup de los datos capturados. |

---

## 9. Beneficios de este Enfoque

- **Cero intervención manual**: El programador solo escribe el código una vez y lo ejecuta.
- **Datos reales vs. suposiciones**: No adivinamos formatos; capturamos exactamente lo que el IBM i devuelve.
- **Reproducible**: Si el IBM i cambia (ej. parche de sistema), se vuelve a ejecutar y se regenera la doc.
- **Facilita la implementación en iNative**: El equipo tiene una especificación "contrato" que deben cumplir al pie de la letra.
