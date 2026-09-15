# 06 — Colectores (observables)

> `probe/colectores/` (Python) + `internal/colectores/` (Go) — capturan los observables definidos en `03-matriz-compatibilidad.md`.

## 6.1 Mensajes de compilación — `mensajes.py`

Formatos reales PUB400 7.5 (2026-08-26):

```python
# RPG (CRTBNDRPG) — RNF/RNQ/RNS:
#   *RNF7030 30      7 000007  The name or indicator VARNOMBRE is not defined.
#   *RNF3316 30 a      000005  The item has already been defined
_PATRON_LINEA = re.compile(r"^\s*\*?(?P<cod>[A-Z]{3}\d{4})\s+(?P<sev>\d{1,2})\s+(?P<pos>[0-9A-Za-z]{1,6})\s+(?P<seq>\d{1,6})\s+(?P<texto>\S.*)$")
#  linea = int(seq) or int(pos); clave dedup = (cod,seq,texto) para descartar resumen *RNF7031 00 1
#  cross-ref *RNF7031 V A(3) 4D → no matchea → se ignora

# DDS (CRTDSPF/CRTPF) — CPD/CPF:
#   * CPD5238      30        1      Message . . . . :   No valid record found...
_PATRON_DDS = re.compile(r"^\*\s*(?P<cod>[A-Z]{3}\d{4})\s+(?P<sev>\d{1,2})\s+(?P<linea>\d{1,6})\s+Message\s*(?:\.\s*)+:\s*(?P<texto>.*)$")
```

→ `Mensaje {codigo, severidad, linea, col=None, texto}` → `observables()` → `{kind:"mensajes", name:cod, value:texto, severidad, linea}`.

Test: `probe/tests/test_colectores_parsers.py` valida `parsear_listing` con líneas reales de `5770WDS`.

## 6.2 JobLog — `joblog.py`

Tres estrategias (en orden, `capturar_joblog`):

1. **ODBC** `SELECT MESSAGE_ID, MESSAGE_TYPE, SEVERITY, MESSAGE_TEXT FROM QSYS2.JOBLOG_INFO ORDER BY ORDINAL_POSITION FETCH FIRST 500 ROWS ONLY`.
2. **Spool** `DSPJOBLOG OUTPUT(*PRINT)` + `CRTPF QTEMP/JOBLOGPRT RCDLEN(132)` + `CPYSPLF FILE(QPJOBLOG) TOFILE(QTEMP/JOBLOGPRT) SPLNBR(*LAST)` + `SELECT * FROM QTEMP.JOBLOGPRT` o `CPYTOIMPF → /tmp/joblog.txt`.
3. **SSH** `DSPJOBLOG` directo.

Parser `parse_joblog_text` (`_MSG_RE = r"^\s*(?P<id>[A-Z]{2,3}\d{4})\s+(?:(?P<sev>\d{1,2})\s+)?(?P<text>.+?)\s*$"`): filtra cabeceras `JOB LOG/PAGE/5722SS1/QSYS` si no contienen código, hereda `CPF→30 / RNQ,RNS→40` si `sev` ausente, y acumula continuaciones de línea.

→ `[{"id":upper,"sev":int,"text":strip}]` → observable `{kind:"joblog", name:"mensajes", value:[…]}`.

## 6.3 LIBL / Objects / Catalogo / DB

| Colector | Fuente IBM i | Retorna |
|----------|--------------|---------|
| `libl.py: capturar_libl` | `QSYS2.LIBRARY_LIST_INFO` (o `DSPLIBL`) | `list[str]` libs en orden |
| `objects.py: capturar_objects` | `QSYS2.OBJECT_STATISTICS('lib','*PGM/*FILE')` | `list[str]` objetos |
| `catalogo.py: ColectorCatalogo` | `DSPMSGD/RTVMSGD QCPFMSG` rangos `CPF,RNF,RNQ…` | `[{kind:"mensajes",name:code,value:text,severidad}]` |
| `db.py: capturar_db(con, lib, tbl)` | `SELECT * FROM lib.tbl` vía ODBC | `list[dict]` rows |
| `db.py: ejecutar_sql` | SQL ad-hoc de `input type:sql` en fixture | `rows` → `observables_db` en captura |

## 6.4 Display — `display.py` / `display_5250.py` / `display_codec.py`

Semántico §9.2/§18 — **estado** no píxeles.

- `DisplaySnapshot` (Python `display.py`): `{rows,cols,cursor{c:row,col}, fields[{name,row,col,length,usage,value,attributes}], indicators{01:bool}, response_key}` → `observables()` canónico (attrs sorted).
- `DisplaySnapshot` extendido (`display_5250.py`): añade `literals[{row,col,text,color,attr}] + text_grid[24] + attr_grid[24×80] + raw_hex` — siempre presentes para `03-fidelidad`.
- `TN5250Client` (`display_5250.py:108-449`): negocia TELNET (`IAC WILL/DO/BINARY/EOR/SGA, TERMINAL-TYPE IBM-3477-FC, NAWS 80×24, NEW_ENVIRON DEVNAME`), envuelve frames en GDS `12A0 00 00 04 00 00 03` + `06 21 <AID>` + `IAC EOR (FF EF)`, decodifica data stream vía `display_codec.decode_5250_stream` (EBCDIC cp37→utf-8, orders `SBA/SF/RA`).
- Helpers `capturar_display(con)` y `to_observable(snapshots)` emiten `display` + `display_literals/grid/raw` si existen.

Contratos Go espejo (`internal/colectores/display.go`): `DisplaySnapshot`, `ScreenField`, `CursorPos` — usados por el comparador.

## 6.5 Interfaz Go

`internal/colectores/colectores.go`:

```go
const (KindDatos="datos"; KindMensajes="mensajes"; …; KindDisplay="display")
type Observable struct{ Kind, Name, Value string }
type Colector interface{ Kind() string; Colectar(conexion any) ([]Observable, error) }
```
