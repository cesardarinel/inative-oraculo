# 07 — Normalizador

> `probe/normalizar.py` (Python) + `internal/normalizador/normalizador.go` (Go) — determiniza observables antes de comparar. Sin normalización, los falsos positivos por espacios/orden/casing rompen el PASS.

## 7.1 Principios (guía §2.3)

- `fixture.ignore` se evalúa en normalización y en comparador; paths case-insensitive.
- **Display**: NO colapsa espacios globales; `value` rstrip trailing, preserva `row/col/length`; ordena `fields` por `(row,col)`, `attributes` sorted; no reordena `literals` (posicional), normaliza color `green/turquesa↔0x20/0x21`.
- **JobLog/Mensajes**: colapsa `\s+ → " "` y `strip`; `id` upper.
- **LIBL/Objects**: `upper`, dedup; libl preserva orden, objects `sorted(set)`.
- **DB**: keys → lower, filas ordenadas por primera clave.

## 7.2 Python — `probe/normalizar.py`

| Función | Qué normaliza |
|---------|---------------|
| `normalizar_texto(t)` | `re.sub(r"\s+"," ",t).strip()` |
| `normalizar_display(snapshot, ignore)` | `cursor→int`, `fields: value rstrip + attrs sorted+lower + usage lower + length int + sort(row,col)`, `literals: text rstrip + color norm + attr int + row/col int`, `text_grid: asegura 80 cols por fila`, `raw_hex lower`, `indicators {k.zfill(2):bool} sorted` |
| `observable_display(snapshot)` | envuelve `normalizar_display` en `{kind:"display",name,value}` |
| `normalizar_joblog(joblog, ignore)` | `id upper + text colapsado + sev int`; filtra si `ig in id.lower() or text.lower()` |
| `normalizar_libl(libl)` | upper+dedup preservando orden; filtra `ignore` lower |
| `normalizar_objects(objects)` | upper+dedup+sorted; filtra ignore substring |
| `normalizar_db(rows)` | filtra keys `ignore` lower, lower keys, sort por primera key |
| `normalizar_observables(list, ignore)` | dispatcher por `kind`: `display/literals/grid/raw/joblog/libl/objects/db/return` |

Color: `_COLOR_NORM` colapsa `green/verde/0x20/0x30→green`, `turquesa/turquoise/0x21/0x31→turquesa`, `red/rojo→red`, `white/blanco→white` (para laxismo green↔turquesa del comparador 03-fidelidad).

## 7.3 Go — `internal/normalizador/`

`SerializarDisplay(sn colectores.DisplaySnapshot) string` — serialización JSON estable vía `json.Encoder(SetEscapeHTML false)` canónico; misma snapshot siempre produce misma string independiente de `map` ordering. Define:

```go
type Normalizado struct{ Kind, Name, Value, Norm string }
type Normalizador interface{ Normalizar(observables []any) ([]Normalizado, error) }
```

## 7.4 Por qué importa

Ejemplo: listing RPG trae `*RNF7030 30      7 000007  …` con múltiples espacios; sin `normalizar_texto` el `==` fallaría aunque el texto sea semánticamente idéntico. O fields desordenados por `(row,col)` — distintos recorridos del codec 5250 darían falsos negativos sin el sort canónico.
