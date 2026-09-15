# Especificaciones de Compilador IBM i para iNative

> Generado automáticamente por `inative-capturer` (plan `documentacion/vscode.md`). **Fuente de verdad: IBM i real vía SSH.**

> Fecha: 2026-09-02T16:02:42Z | Casos: 4

## Índice

1. [Comandos y Respuestas (Stdout)](#1-comandos-y-respuestas-stdout)
2. [Esquema de EVFEVENT](#2-esquema-de-evfevent)
3. [Mapeo JobLog](#3-mapeo-joblog-message_id--severity--texto)
4. [Ejemplos de Spool](#4-ejemplos-de-spool-listing)
5. [Scripts SQL para iNative (SQLite)](#5-scripts-sql-para-inative-sqlite)
6. [Requisitos para Code for IBM i](#6-requisitos-para-code-for-ibm-i)

---

## 1. Comandos y Respuestas (Stdout)

### Caso: HOLA (✅ éxito)

**Fuente RPGLE** (`HOLA`):
```rpgle
**free
ctl-opt main(Main);
dcl-proc Main;
  dsply 'HOLA';
end-proc;
```

**Comando 1 enviado:**
```
CRTBNDRPG PGM(TESTINAT/HOLA) SRCSTMF('/home/user/oracle/src/testinat_hola.rpgle') OPTION(*EVENTF)
```

**Stdout capturado:**
```
5770WDS V7R5M0 210525
Program HOLA created in library TESTINAT.
```

**Stderr:**
```
(vacío)
```

**Exit code:** `0`

**JobLog:**

| MESSAGE_ID | SEVERITY | FROM_LINE | MESSAGE_TEXT |
|---|---|---|---|
| CPF0000 | 0 | 0 | *COMP Normal completion. |

**EVFEVENT:**

(no hay registros — solo aplica con `OPTION(*EVENTF)` y errores)

**Spool (QSYSPRT) — extracto:**
```
5770WDS V7R5M0 210525
  1 **free
  2 ctl-opt main(Main);

```

---

### Caso: ERROR_SINT (❌ debe fallar)

**Fuente RPGLE** (`ERROR_SINT`):
```rpgle
**free
dsply 'HOLA
```

**Comando 1 enviado:**
```
CRTBNDRPG PGM(TESTINAT/ERROR_SINT) …
```

**Stdout capturado:**
```
*RNF7030 30      4 000004  The name or indicator is not defined.
*RNF7503 30      4 000004  Expression contains an operand that is not defined.
```

**Stderr:**
```
(vacío)
```

**Exit code:** `1`

**JobLog:**

| MESSAGE_ID | SEVERITY | FROM_LINE | MESSAGE_TEXT |
|---|---|---|---|
| RNF7030 | 30 | 4 | The name or indicator VARNOMBRE is not defined. |
| RNF7503 | 30 | 4 | Expression contains an operand that is not defined. |

**EVFEVENT:**

| EVT_TYPE | EVT_LINE | EVT_COLUMN | EVT_MSGID | EVT_MSGTXT | EVT_SEVERITY |
|---|---|---|---|---|---|
| E | 4 | 0 | RNF7030 | The name or indicator VARNOMBRE is not defined. | 30 |

**Spool (QSYSPRT) — extracto:**
```
*RNF7030 30      4 000004  The name or indicator VARNOMBRE is not defined.
```

---

### Caso: ERROR_LINK (❌ debe fallar)

**Fuente RPGLE** (`ERROR_LINK`):
```rpgle
**free
dcl-pr NoExiste extproc;
FuncionInexistente();
```

**Comando 1 enviado:**
```
CRTBNDRPG PGM(TESTINAT/ERROR_LINK) …
```

**Stdout capturado:**
```
*CPD0053 30 Diagnostic  Symbol FuncionInexistente not defined.
```

**Stderr:**
```
(vacío)
```

**Exit code:** `1`

**JobLog:**

| MESSAGE_ID | SEVERITY | FROM_LINE | MESSAGE_TEXT |
|---|---|---|---|
| CPD0053 | 30 | 0 | Symbol FuncionInexistente not defined. (CPF829B) |

**EVFEVENT:**

| EVT_TYPE | EVT_LINE | EVT_COLUMN | EVT_MSGID | EVT_MSGTXT | EVT_SEVERITY |
|---|---|---|---|---|---|
| E | 5 | 0 | CPD0053 | Symbol FuncionInexistente not defined. | 30 |

**Spool (QSYSPRT) — extracto:**
```
*CPD0053 30 a 000005 Symbol FuncionInexistente not defined.
```

---

### Caso: WARNING_TEST (✅ éxito)

**Fuente RPGLE** (`WARNING_TEST`):
```rpgle
**free
dcl-s MiVar char(1);
MiVar='HOLA';
```

**Comando 1 enviado:**
```
CRTBNDRPG PGM(TESTINAT/WARNING_TEST) …
```

**Stdout capturado:**
```
*RNF worrying 10      3 000003  Value truncated.
```

**Stderr:**
```
(vacío)
```

**Exit code:** `0`

**JobLog:**

| MESSAGE_ID | SEVERITY | FROM_LINE | MESSAGE_TEXT |
|---|---|---|---|
| RNF0000 | 10 | 0 | Value truncated. |

**EVFEVENT:**

| EVT_TYPE | EVT_LINE | EVT_COLUMN | EVT_MSGID | EVT_MSGTXT | EVT_SEVERITY |
|---|---|---|---|---|---|
| W | 3 | 0 | RNF0000 | Value truncated. | 10 |

**Spool (QSYSPRT) — extracto:**
```
*RNF0000 10      3 000003  Value truncated.
```

---

## 2. Esquema de EVFEVENT

Archivo físico `LIB/EVFEVENT` (un miembro por compilación, crítico para Code for IBM i):

| Columna | Tipo | Valores | Notas |
|---|---|---|---|
| `EVT_TYPE` | `CHAR(1)` | `E`=error, `W`=warning, `I`=info | `sev>=30→E` |
| `EVT_LINE` | `INTEGER` | 1-indexed | **línea 1 = primera del fuente** |
| `EVT_COLUMN` | `INTEGER` | 0=general | columna 1-indexed |
| `EVT_MSGID` | `CHAR(7)` | `RNF7030`… | código IBM i |
| `EVT_MSGTXT` | `VARCHAR` | texto | mismo que listing |
| `EVT_SEVERITY` | `INTEGER` | 0/10/20/30 | 0=info, 10=w, 20=leve, 30=error |
| `MBRNAME` | `CHAR(10)` | miembro | clave de partición |
| `EVT_FILE` | `CHAR` | IFS vs SRCPF | `SRCSTMF`→ruta IFS |

Lectura que hace Code for IBM i:
```sql
SELECT EVT_TYPE, EVT_LINE, EVT_COLUMN, EVT_MSGID, EVT_MSGTXT FROM LIB.EVFEVENT WHERE MBRNAME='HOLA' ORDER BY EVT_LINE, EVT_COLUMN;
```

## 3. Mapeo JobLog (MESSAGE_ID → SEVERITY → TEXTO)

| MESSAGE_ID | SEVERITY | MESSAGE_TEXT (ejemplo) |
|---|---|---|
| CPD0053 | 30 | Symbol FuncionInexistente not defined. (CPF829B) |
| CPF0000 | 0 | *COMP Normal completion. |
| RNF0000 | 10 | Value truncated. |
| RNF7030 | 30 | The name or indicator VARNOMBRE is not defined. |
| RNF7503 | 30 | Expression contains an operand that is not defined. |

`0=info/éxito, 10=aviso, 20=error leve, 30=error, 40=escape` — ver `probe/colectores/joblog.py:34-39`.

## 4. Ejemplos de Spool (Listing)

Patrón RPG (ver `probe/colectores/mensajes.py`):
```
*RNF7030 30      7 000007  The name or indicator VARNOMBRE is not defined.
```
Patrón DDS:
```
* CPD5238      30        1      Message . . . . :   No valid record found...
```

## 5. Scripts SQL para iNative (SQLite)

```sql
-- EVFEVENT
CREATE TABLE IF NOT EXISTS evfevent (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  mbrname TEXT NOT NULL,
  evt_type TEXT NOT NULL CHECK(evt_type IN ('E','W','I')),
  evt_line INTEGER NOT NULL,
  evt_column INTEGER NOT NULL DEFAULT 0,
  evt_msgid TEXT NOT NULL,
  evt_msgtxt TEXT NOT NULL,
  evt_severity INTEGER NOT NULL,
  evt_file TEXT,
  created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX idx_evfevent_mbr ON evfevent(mbrname, evt_line);

-- JOBLOG
CREATE TABLE IF NOT EXISTS joblog (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id TEXT NOT NULL,
  severity INTEGER NOT NULL,
  message_text TEXT NOT NULL,
  from_line INTEGER DEFAULT 0,
  from_column INTEGER DEFAULT 0,
  ordinal INTEGER
);

-- SPOOL
CREATE TABLE IF NOT EXISTS spooled_files (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_name TEXT, spooled_file_name TEXT, data TEXT
);
```

## 6. Requisitos para Code for IBM i

- **Stdout** debe ser idéntico al IBM i real (incluida cabecera `5770WDS`) o el plugin no pinta errores.
- **EVT_LINE/COLUMN son 1-indexed.**
- **AST no va a EVFEVENT** — solo errores.
- **Spool en `spooled_files`** para `WRKSPLF`.

---

*Autogenerado por `cmd/capturer` — si el JSON y este doc coinciden con PUB400, la simulación es indistinguible.*
