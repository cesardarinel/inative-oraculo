# 03 — Matriz de compatibilidad (observables)

> Plan maestro §20 / `internal/colectores/colectores.go` — el único conjunto de aspectos comparables entre **IBM i real** y **iNative local**.

## 3.1 Kinds canónicos

| Kind | Const Go | Colector Python | Qué captura | Normaliza |
|------|----------|-----------------|-------------|-----------|
| `datos` | `KindDatos` | `colectores/db.py` | Filas de tablas (`SELECT * FROM lib.tabla`) — `db` obs. | `normalizar_db`: keys→lower, sort por primera clave, filtra `ignore` |
| `mensajes` | `KindMensajes` | `mensajes.py` + `joblog.py` | `RNF/CPF/CPD…` del listing y del JobLog | `mensajes` usa `_PATRON_LINEA/_PATRON_DDS`; `joblog` usa `parse_joblog_text` + `normalizar_joblog` (colapsa espacios, upper id) |
| `indicadores` | `KindIndicadores` | incluido en `display` snapshot | `*IN01`…`*IN99` → `map["01"]bool` | `indicators: sorted keys, zfill(2)` |
| `job` | `KindJob` | `joblog.py` + `return` | `joblog` + `return rc` | `return` → int |
| `objetos` | `KindObjetos` | `objects.py` | `OBJECT_STATISTICS('lib','*PGM/*FILE')` | `normalizar_objects`: upper, dedup, sorted |
| `locks` | `KindLocks` | (reservado) | `QSYS2.OBJECT_LOCKS` | — |
| `transacciones` | `KindTransacciones` | (reservado) | `COMMIT(*NONE)` / journal | — |
| `display` | `KindDisplay` | `display_5250.py` / `display.py` | `DisplaySnapshot` §9.2: `screen/cursor/fields/indicators/response_key` + ext `literals/text_grid/raw_hex` | `normalizar_display`: rstrip values, attrs sorted, fields por (row,col), color→green/turquesa, `text_grid 24x80` |

Kinds extendidos de fidelidad (§9.2/§18, emitidos por `captura.py:340-346` y `display_5250.py:79-88`):

`display` + `display_literals` + `display_grid` + `display_raw` (opcionales, honrados por `compare.display*`).

## 3.2 Reglas de comparación (comparador Go)

`internal/comparador/comparador.go`:

- **Secuencia** de snapshots display: longitud posicional, luego cada snapshot por aspectos activados en `ComparaSet` (`Screens`, `Fields`, `Cursor`, `Attributes`, `Indicators`, `ResponseKey`, `Display/Literals/Grid/Raw`).
- **Fields**: matched por `(row,col)` — compara `name/row/col/length/usage/value`; `attributes` vía `compararAtributos` si `Attributes==true`.
- **Literales**: index por `(row,col)` — `text` case-sensitive (rstrip), `color` con laxismo green↔turquesa (`normalizeColor`, `isGreenTurquoise`).
- **Grid**: 24 filas `text_grid` (exacto 24×80); rstrip laxo si trailing diff.
- **Raw**: `raw_hex` byte-compare lower-trim si `DisplayRaw==true`.
- **`ignore`** es case-insensitive y hace substring match sobre paths dot-separated (`esIgnorable`) — cubre `job.number`, `timestamp`, `display.literals[*].color`, etc.

## 3.3 Qué NO se compara

- AST interno, spool raw sin normalizar, trazas SSH, números de job/spool, timestamps `capturado`, `ordinal_position` del JobLog ajena a `id/text/sev`, `attr_grid` interno.

## 3.4 Referencia cruzada con la spec IBM i

Esta matriz consume directamente los formatos de `COMPILADOR_IBM_I_ESPECIFICACIONES.md`:

- `mensajes`/`job` ← JobLog (§2) + listing (§3) + EVFEVENT (§4)
- `objetos` ← `OBJECT_STATISTICS` / `PROGRAM_EXPORT_IMPORT_INFO` (§5)
- `display` ← TN5250 data stream (§9.2/§18)

Cobertura `conformance/` por familia (plan §19): `authority/`, `chain-read/`, `dspf/`, `pf-lf/`, `messages/`, etc. — ver `conformance/README.md`.
