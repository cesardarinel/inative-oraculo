# Especificaciones de Compilador IBM i para iNative

> Generado automáticamente por `inative-capturer` (plan `documentacion/vscode.md`). **Fuente de verdad: IBM i real vía SSH.**

> Fecha: 2026-09-02T17:11:55Z | Casos: 4

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
  dsply 'HOLA MUNDO ILE';
end-proc;
```

**Comando 1 enviado:**
```
system -b "CRTBNDRPG PGM(C3S411/HOLA) SRCSTMF('/home/C3S41/oracle/src/c3s411_HOLA.rpgle') OPTION(*EVENTF) DBGVIEW(*SOURCE) TGTCCSID(37)"
```

**Stdout capturado:**
```
RNS9304: Program HOLA placed in library C3S411. 00 highest severity. Created on 26-09-02 at 19:11:38.
 5770WDS V7R5M0  220415 RN        IBM ILE RPG             C3S411/HOLA              PUB400     26-09-02 19:11:38        Page      1
  Command  . . . . . . . . . . . . :   CRTBNDRPG
    Issued by  . . . . . . . . . . :     C3S41
  Program  . . . . . . . . . . . . :   HOLA
    Library  . . . . . . . . . . . :     C3S411
  Text 'description' . . . . . . . :   *SRCMBRTXT
  Source stream file   . . . . . . :   /home/C3S41/oracle/src/c3s411_HOLA.rpgle
    CCSID  . . . . . . . . . . . . :     1208
  Target CCSID . . . . . . . . . . :   37
  Text 'description' . . . . . . . :
  Last Change  . . . . . . . . . . :   26-09-02  19:11:37
  Generation severity level  . . . :   10
  Default activation group . . . . :   *YES
  Compiler options . . . . . . . . :   *XREF      *GEN       *NOSECLVL  *SHOWCPY
                                       *EXPDDS    *EXT       *NOSHOWSKP *NOSRCSTMT
                                       *DEBUGIO   *UNREF     *EVENTF
  Debugging views  . . . . . . . . :   *SOURCE
  Debug encryption key . . . . . . :   *NONE
  Output . . . . . . . . . . . . . :   *PRINT
  Optimization level . . . . . . . :   *NONE
  Source listing indentation . . . :   *NONE
  Type conversion options  . . . . :   *NONE
  Sort sequence  . . . . . . . . . :   *HEX
  Language identifier  . . . . . . :   *JOBRUN
  Replace program  . . . . . . . . :   *YES
  User profile . . . . . . . . . . :   *USER
  Authority  . . . . . . . . . . . :   *LIBCRTAUT
  Truncate numeric . . . . . . . . :   *YES
  Fix numeric  . . . . . . . . . . :   *NONE
  Target release . . . . . . . . . :   *CURRENT
  Allow null values  . . . . . . . :   *NO
  Define condition names . . . . . :   *NONE
  Enable performance collection  . :   *PEP
  Profiling data . . . . . . . . . :   *NOCOL
  Licensed Internal Code options . :
  Generate program interface . . . :   *NO
  Include directory  . . . . . . . :
  Preprocessor options . . . . . . :   *NONE
  Require prototype for export . . :   *NO
                                                   -=* http://pub400.com *=-
 5770WDS V7R5M0  220415 RN        IBM ILE RPG             C3S411/HOLA              PUB400     26-09-02 19:11:38        Page      2
Line   <---------------------- Source Specifications ----------------------------------------------------->  Do  Change Src Seq
Number ....+....1....+....2....+....3....+....4....+....5....+....6....+....7....+....8....+....9....+...10  Num Date   Id  Number
                          S o u r c e   L i s t i n g
     1 **free                                                                                                               000001
     2 ctl-opt main(Main);                                                                                                  000002
     3 dcl-proc Main;                                                                                                       000003
     4   dsply 'HOLA MUNDO ILE';                                                                                            000004
     5 end-proc;                                                                                                            000005
       * * * * *   E N D   O F   S O U R C E   * * * * *
                                                   -=* http://pub400.com *=-
 5770WDS V7R5M0  220415 RN        IBM ILE RPG             C3S411/HOLA              PUB400     26-09-02 19:11:38        Page      3
          A d d i t i o n a l   D i a g n o s t i c   M e s s a g e s
 Msg id  Sv Number Seq     Message text
 * * * * *   E N D   O F   A D D I T I O N A L   D I A G N O S T I C   M E S S A G E S   * * * * *
                                                   -=* http://pub400.com *=-
 5770WDS V7R5M0  220415 RN        IBM ILE RPG             C3S411/HOLA              PUB400     26-09-02 19:11:38        Page      4
                          C r o s s   R e f e r e n c e
      File
…(truncado)
```

**Stderr:**
```
(vacío)
```

**Exit code:** `0`

**Comando 2 enviado:**
```
system -b "CRTRPGMOD MODULE(C3S411/HOLA) SRCFILE(C3S411/QRPGLESRC) SRCMBR(HOLA)"
```

**Stdout capturado:**
```
RNS9305: Module HOLA placed in library C3S411. 00 highest severity. Created on 26-09-02 at 19:11:39.
 5770WDS V7R5M0  220415 RN        IBM ILE RPG             C3S411/HOLA              PUB400     26-09-02 19:11:39        Page      1
  Command  . . . . . . . . . . . . :   CRTRPGMOD
    Issued by  . . . . . . . . . . :     C3S41
  Module . . . . . . . . . . . . . :   HOLA
    Library  . . . . . . . . . . . :     C3S411
  Text 'description' . . . . . . . :   *SRCMBRTXT
  Source Member  . . . . . . . . . :   HOLA
  Source File  . . . . . . . . . . :   QRPGLESRC
    Library  . . . . . . . . . . . :     C3S411
    CCSID  . . . . . . . . . . . . :     273
  Text 'description' . . . . . . . :
  Last Change  . . . . . . . . . . :   26-09-02  19:11:38
  Generation severity level  . . . :   10
  Compiler options . . . . . . . . :   *XREF      *GEN       *NOSECLVL  *SHOWCPY
                                       *EXPDDS    *EXT       *NOSHOWSKP *NOSRCSTMT
                                       *DEBUGIO   *UNREF     *NOEVENTF
  Debugging views  . . . . . . . . :   *STMT
  Debug encryption key . . . . . . :   *NONE
  Output . . . . . . . . . . . . . :   *PRINT
  Optimization level . . . . . . . :   *NONE
  Source listing indentation . . . :   *NONE
  Type conversion options  . . . . :   *NONE
  Sort sequence  . . . . . . . . . :   *HEX
  Language identifier  . . . . . . :   *JOBRUN
  Replace module . . . . . . . . . :   *YES
  Authority  . . . . . . . . . . . :   *LIBCRTAUT
  Truncate numeric . . . . . . . . :   *YES
  Fix numeric  . . . . . . . . . . :   *NONE
  Target release . . . . . . . . . :   *CURRENT
  Allow null values  . . . . . . . :   *NO
  Storage model . . .  . . . . . . :   *INHERIT
  Binding directory  . . . . . . . :   *NONE
  Define condition names . . . . . :   *NONE
  Enable performance collection  . :   *PEP
  Profiling data . . . . . . . . . :   *NOCOL
  Licensed Internal Code options . :
  Generate program interface . . . :   *NO
  Include directory  . . . . . . . :
  Preprocessor options . . . . . . :   *NONE
  Require prototype for export . . :   *NO
                                                   -=* http://pub400.com *=-
 5770WDS V7R5M0  220415 RN        IBM ILE RPG             C3S411/HOLA              PUB400     26-09-02 19:11:39        Page      2
Line   <---------------------- Source Specifications ----------------------------------------------------->  Do  Change Src Seq
Number ....+....1....+....2....+....3....+....4....+....5....+....6....+....7....+....8....+....9....+...10  Num Date   Id  Number
                          S o u r c e   L i s t i n g
     1 **free                                                                                                    000000     000100
     2 ctl-opt main(Main);                                                                                       000000     000200
     3 dcl-proc Main;                                                                                            000000     000300
     4   dsply 'HOLA MUNDO ILE';                                                                                 000000     000400
     5 end-proc;                                                                                                 000000     000500
       * * * * *   E N D   O F   S O U R C E   * * * * *
                                                   -=* http://pub400.com *=-
 5770WDS V7R5M0  220415 RN        IBM ILE RPG             C3S411/HOLA              PUB400     26-09-02 19:11:39        Page      3
          A d d i t i o n a l   D i a g n o s t i c   M e s s a g e s
 Msg id  Sv Number Seq     Message text
 * * * * *   E N D   O F   A D D I T I O N A L   D I A G N O S T I C   M E S S A G E S   * * * * *
                                                   -=* http://pub400.com *=-
 5770WDS V7R5M0  220415 RN        IBM ILE RPG             C3S411/HOLA              PUB400     26-09-02 19:11:39        Page      4
                          C r o s s   R e f e
…(truncado)
```

**Stderr:**
```
(vacío)
```

**Exit code:** `0`

**JobLog:**

(sin entradas — compilación limpia)

**EVFEVENT:**

(no hay registros — solo aplica con `OPTION(*EVENTF)` y errores)

**Spool (QSYSPRT) — extracto:**
```
RNS9304: Program HOLA placed in library C3S411. 00 highest severity. Created on 26-09-02 at 19:11:38.
 5770WDS V7R5M0  220415 RN        IBM ILE RPG             C3S411/HOLA              PUB400     26-09-02 19:11:38        Page      1
  Command  . . . . . . . . . . . . :   CRTBNDRPG
    Issued by  . . . . . . . . . . :     C3S41
  Program  . . . . . . . . . . . . :   HOLA
    Library  . . . . . . . . . . . :     C3S411
  Text 'description' . . . . . . . :   *SRCMBRTXT
  Source stream file   . . . . . . :   /home/C3S41/oracle/src/c3s411_HOLA.rpgle
    CCSID  . . . . . . . . . . . . :     1208
  Target CCSID . . . . . . . . . . :   37
  Text 'description' . . . . . . . :
  Last Change  . . . . . . . . . . :   26-09-02  19:11:37
  Generation severity level  . . . :   10
  Default activation group . . . . :   *YES
  Compiler options . . . . . . . . :   *XREF      *GEN       *NOSECLVL  *SHOWCPY
                                       *EXPDDS    *EXT       *NOSHOWSKP *NOSRCSTMT
                                       *DEBUGIO   *UNREF     *EVENTF
  Debugging views  . . . . . . . . :   *SOURCE
  Debug encryption key . . . . . . :   *NONE
  Output . . . . . . . . . . . . . :   *PRINT
  Optimization level . . . . . . . :   *NONE
  Source listing indentation . . . :   *NONE
  Type conversion options  . . . . :   *NONE
  Sort sequence  . . . . . . . . . :   *HEX
  Language identifier  . . . . . . :   *JOBRUN
  Replace program  . . . . . . . . :   *YES
  User profile . . . . . . . . . . :   *USER
  Authority  . . . . . . . . . . . :   *LIBCRTAUT
  Truncate numeric . . . . . . . . :   *YES
  Fix numeric  . . . . . . . . . . :   *NONE
  Target release . . . . . . . . . :   *CURRENT
  Allow null values  . . . . . . . :   *NO
  Define condition names . . . . . :   *NONE
  Enable performance collection  . :   *PEP
  Profiling data . . . . . . . . . :   *NOCOL
  Licensed Internal Code options . :
  Generate program interface . . . :   *NO
  Include directory  . . . . . . . :
  Preprocessor options . . . . . . :   *NONE
  Require prototype for export . . :   *NO
                                                   -=* http://pub400.com *=-
 5770WDS V7R5M0  220415 RN        IBM ILE RPG             C3S411/HOLA              PUB400     26-09-02 19:11:38        Page      2
Line   <---------------------- Source Specifications ----------------------------------------------------->  Do  Change Src Seq
Number ....+....1....+....2....+....3....+....4....+....5....+....6....+....7....+....8....+....9....+...10  Num Date   Id  Number
                          S o u r c e   L i s t i n g
     1 **free                                                                                                               000001
     2 ctl-opt main(Main);                                                                                                  000002
     3 dcl-proc Main;                                                                                                       000003
     4   d
…(truncado)
```

---

### Caso: ERROR_SINT (❌ debe fallar)

**Fuente RPGLE** (`ERROR_SINT`):
```rpgle
**free
ctl-opt main(Main);
dcl-proc Main;
  dsply 'HOLA   // Falta la comilla de cierre
end-proc;
```

**Comando 1 enviado:**
```
system -b "CRTBNDRPG PGM(C3S411/ERROR_SINT) SRCSTMF('/home/C3S41/oracle/src/c3s411_ERROR_SINT.rpgle') OPTION(*EVENTF)"
```

**Stdout capturado:**
```
(vacío)
```

**Stderr:**
```
RNS9339: Unable to open file /home/C3S41/oracle/src/c3s411_ERROR_SINT.rpgle.
RNS9310: Compilation failed. Program ERROR_SINT not created in library C3S411.

```

**Exit code:** `255`

**JobLog:**

(sin entradas — compilación limpia)

**EVFEVENT:**

(no hay registros — solo aplica con `OPTION(*EVENTF)` y errores)

**Spool (QSYSPRT) — extracto:**
```

RNS9339: Unable to open file /home/C3S41/oracle/src/c3s411_ERROR_SINT.rpgle.
RNS9310: Compilation failed. Program ERROR_SINT not created in library C3S411.


```

---

### Caso: ERROR_LINK (❌ debe fallar)

**Fuente RPGLE** (`ERROR_LINK`):
```rpgle
**free
ctl-opt main(Main);
dcl-pr FuncionInexistente extproc;
end-pr;
dcl-proc Main;
  FuncionInexistente();
end-proc;
```

**Comando 1 enviado:**
```
system -b "CRTBNDRPG PGM(C3S411/ERROR_LINK) SRCSTMF('/home/C3S41/oracle/src/c3s411_ERROR_LINK.rpgle') OPTION(*EVENTF)"
```

**Stdout capturado:**
```
(vacío)
```

**Stderr:**
```
RNS9339: Unable to open file /home/C3S41/oracle/src/c3s411_ERROR_LINK.rpgle.
RNS9310: Compilation failed. Program ERROR_LINK not created in library C3S411.

```

**Exit code:** `255`

**JobLog:**

(sin entradas — compilación limpia)

**EVFEVENT:**

(no hay registros — solo aplica con `OPTION(*EVENTF)` y errores)

**Spool (QSYSPRT) — extracto:**
```

RNS9339: Unable to open file /home/C3S41/oracle/src/c3s411_ERROR_LINK.rpgle.
RNS9310: Compilation failed. Program ERROR_LINK not created in library C3S411.


```

---

### Caso: WARNING_TEST (✅ éxito (falló inesperadamente))

**Fuente RPGLE** (`WARNING_TEST`):
```rpgle
**free
ctl-opt main(Main);
dcl-s MiVar char(10);
dcl-proc Main;
  MiVar = 'HOLA';
end-proc;
```

**Comando 1 enviado:**
```
system -b "CRTBNDRPG PGM(C3S411/WARNING_TEST) SRCSTMF('/home/C3S41/oracle/src/c3s411_WARNING_TEST.rpgle') OPTION(*EVENTF)"
```

**Stdout capturado:**
```
(vacío)
```

**Stderr:**
```
CPD0074: Value 'WARNING_TE' for PGM exceeds 10 characters.
CPF0006: Errors occurred in command.

```

**Exit code:** `255`

**JobLog:**

(sin entradas — compilación limpia)

**EVFEVENT:**

(no hay registros — solo aplica con `OPTION(*EVENTF)` y errores)

**Spool (QSYSPRT) — extracto:**
```

CPD0074: Value 'WARNING_TE' for PGM exceeds 10 characters.
CPF0006: Errors occurred in command.


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

_Sin mensajes capturados (ejecutar con errores para poblar)._ 

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
