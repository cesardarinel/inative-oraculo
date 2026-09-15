"""Normalización de observables por Kind para comparación determinista.

Reglas guía §2.3:
- fixture.ignore contiene paths case-insensitive; el filtrado lo hace el comparador,
  aquí solo aplicamos transformaciones canónicas.
- display: NO colapsa espacios globales; solo rstrip value, preserva row/col/len/attrs,
  ordena fields por (row,col), attrs sorted.
- joblog: colapsa espacios en text, upper id.
- libl/objects: upper + dedup preservando orden (libl) o sorted (objects).
- db: ordena por clave si se da, lower keys.
"""
from __future__ import annotations

import re


def normalizar_texto(texto: str) -> str:
    """Colapsa espacios múltiples y recorta; para joblog/mensajes."""
    return re.sub(r"\s+", " ", texto).strip()


def normalizar_observable(obs: dict) -> dict:
    """Compatibilidad: copia con 'norm' para observables de mensajes antiguos."""
    copia = dict(obs)
    if "value" in copia:
        copia["norm"] = normalizar_texto(str(copia["value"]))
    if "texto" in copia:
        copia["norm"] = normalizar_texto(str(copia["texto"]))
    return copia


# ---- Display ----

# Normalización de colores (03-fidelidad): verde/turquesa ↔ 0x20/0x21
_COLOR_NORM = {
    "green": "green",
    "verde": "green",
    "0x20": "green",
    "0x30": "green",
    "turquesa": "turquesa",
    "turquoise": "turquesa",
    "0x21": "turquesa",
    "0x31": "turquesa",
    "red": "red",
    "rojo": "red",
    "0x22": "red",
    "white": "white",
    "blanco": "white",
    "0x23": "white",
}

def _norm_color(c: str) -> str:
    if not c:
        return "green"
    return _COLOR_NORM.get(str(c).strip().lower(), str(c).strip().lower())


def normalizar_display(snapshot: dict, ignore: list[str] | None = None) -> dict:
    """Normaliza DisplaySnapshot canónico. No altera semántica posicional.

    Extendido 03-fidelidad: preserva row/col, no reordena literals, normaliza
    color (green/turquesa↔0x20/0x21), rstrip solo trailing en text pero mantiene col,
    preserva text_grid/text_grid y raw_hex.
    """
    _ = ignore  # ignore lo evalúa el comparador; aquí no filtramos fields
    raw = dict(snapshot)
    screen = dict(raw.get("screen", {"rows": 24, "cols": 80}))
    cursor = raw.get("cursor")
    if cursor is not None:
        cursor = {"row": int(cursor.get("row", 1)), "col": int(cursor.get("col", 1))}
    fields_in = raw.get("fields", [])
    fields_out: list[dict] = []
    for f in fields_in:
        fd = dict(f)
        if "value" in fd and isinstance(fd["value"], str):
            fd["value"] = fd["value"].rstrip(" ")
        attrs = fd.get("attributes", []) or fd.get("attrs", []) or []
        if isinstance(attrs, dict):
            # dict puede ser {"color":..., "protected":...} → conserva color separado
            col = attrs.get("color")
            if col:
                fd["_color"] = _norm_color(str(col))
            attrs = [k for k, v in attrs.items() if v and k != "color"] if isinstance(attrs, dict) else []
            # si attrs es dict de flags boolean
            if isinstance(attrs, dict):
                attrs = [k for k, v in attrs.items() if v]
        fd["attributes"] = sorted(set(str(a).strip().lower() for a in attrs if str(a).strip()))
        # Si había color en attrs dict, reinyecta normalizado como atributo de comparación laxa?
        # Lo guardamos también en campo "color" para comparador
        if "_color" in fd:
            fd["color"] = fd.pop("_color")
        elif "color" in f:
            fd["color"] = _norm_color(str(f["color"]))
        # También preserva attrs dict normalizado si venía
        if "attrs" in f and isinstance(f["attrs"], dict):
            c = f["attrs"].get("color")
            if c:
                fd["attrs"] = dict(f["attrs"])
                fd["attrs"]["color"] = _norm_color(str(c))
        if "usage" in fd:
            fd["usage"] = str(fd["usage"]).lower()
        for k in ("row", "col", "length", "len"):
            if k in fd:
                try:
                    fd[k] = int(fd[k])
                except Exception:
                    pass
        if "len" in fd and "length" not in fd:
            fd["length"] = fd.pop("len")
        # Estructura final limpia: mantén solo keys conocidas + attrs/color si existen
        clean = {kk: fd[kk] for kk in ("name", "row", "col", "length", "usage", "value", "attributes", "color", "attrs") if kk in fd}
        # Asegura defaults
        if "attributes" not in clean:
            clean["attributes"] = []
        fields_out.append(clean)
    fields_out.sort(key=lambda x: (int(x.get("row", 0)), int(x.get("col", 0))))
    # Literals: preservar orden y row/col, rstrip text trailing, normalizar color
    literals_in = raw.get("literals", [])
    literals_out: list[dict] = []
    for lit in literals_in:
        ld = dict(lit)
        if "text" in ld and isinstance(ld["text"], str):
            ld["text"] = ld["text"].rstrip(" ")
        if "color" in ld:
            ld["color"] = _norm_color(str(ld["color"]))
        # Normaliza attr hex si viene como int
        if "attr" in ld:
            try:
                av = ld["attr"]
                if isinstance(av, int):
                    ld["attr"] = av
                elif isinstance(av, str) and av.lower().startswith("0x"):
                    ld["attr"] = int(av, 16)
            except Exception:
                pass
        for k in ("row", "col"):
            if k in ld:
                try:
                    ld[k] = int(ld[k])
                except Exception:
                    pass
        literals_out.append(ld)
    # text_grid: 24 strings len 80, preserva tal cual pero asegura rstrip no se aplique (son celdas)
    text_grid = raw.get("text_grid", [])
    if isinstance(text_grid, list):
        # Normaliza cada fila a str len 80 (si viene truncada)
        ng = []
        for row in text_grid:
            s = str(row) if row is not None else ""
            # No rstrip global, pero asegura longitud cols
            cols = int(screen.get("cols", 80))
            if len(s) < cols:
                s = s + " " * (cols - len(s))
            elif len(s) > cols:
                s = s[:cols]
            ng.append(s)
        text_grid = ng
    else:
        text_grid = []
    # attr_grid: 24x80
    attr_grid = raw.get("attr_grid", [])
    raw_hex = raw.get("raw_hex", "")
    if raw_hex is not None:
        raw_hex = str(raw_hex).lower()
    else:
        raw_hex = ""
    indicators = raw.get("indicators", {})
    if isinstance(indicators, dict):
        indicators = {str(k).zfill(2): bool(v) for k, v in sorted(indicators.items())}
    else:
        indicators = {}
    out = {
        "screen": {"rows": int(screen.get("rows", 24)), "cols": int(screen.get("cols", 80))},
        "cursor": cursor,
        "fields": fields_out,
        "indicators": indicators,
        "response_key": raw.get("response_key"),
    }
    # Solo añade extendidos si existen (para compat)
    if literals_out:
        out["literals"] = literals_out
    elif "literals" in raw:
        out["literals"] = literals_out
    if text_grid:
        out["text_grid"] = text_grid
    elif "text_grid" in raw:
        out["text_grid"] = text_grid
    if attr_grid:
        out["attr_grid"] = attr_grid
    elif "attr_grid" in raw:
        out["attr_grid"] = attr_grid
    if raw_hex:
        out["raw_hex"] = raw_hex
    elif "raw_hex" in raw:
        out["raw_hex"] = raw_hex
    return out


def observable_display(snapshot: dict, *, name: str = "screen", ignore: list[str] | None = None) -> dict:
    norm = normalizar_display(snapshot, ignore)
    return {"kind": "display", "name": name, "value": norm}


# ---- Joblog ----

def normalizar_joblog(joblog: list[dict], ignore: list[str] | None = None) -> list[dict]:
    ignore_lower = [s.lower() for s in (ignore or [])]
    out: list[dict] = []
    for e in joblog:
        mid = str(e.get("id", "")).strip().upper()
        text = normalizar_texto(str(e.get("text", "")))
        sev = e.get("sev", 0)
        try:
            sev = int(sev)
        except Exception:
            sev = 0
        # Filtra si ignore contiene id
        if any(ig in mid.lower() or ig in text.lower() for ig in ignore_lower):
            continue
        out.append({"id": mid, "sev": sev, "text": text})
    return out


# ---- Libl ----

def normalizar_libl(libl: list[str], ignore: list[str] | None = None) -> list[str]:
    ignore_lower = set(s.lower() for s in (ignore or []))
    seen: set[str] = set()
    out: list[str] = []
    for lib in libl:
        u = str(lib).strip().upper()
        if not u or u.lower() in ignore_lower:
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ---- Objects ----

def normalizar_objects(objects: list[str], ignore: list[str] | None = None) -> list[str]:
    ignore_lower = [s.lower() for s in (ignore or [])]
    out: list[str] = []
    for o in objects:
        s = str(o).strip().upper()
        if not s:
            continue
        if any(ig in s.lower() for ig in ignore_lower):
            continue
        out.append(s)
    return sorted(set(out))


# ---- DB ----

def normalizar_db(rows: list[dict], ignore: list[str] | None = None) -> list[dict]:
    ignore_lower = set(s.lower() for s in (ignore or []))
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            out.append(r)
            continue
        filtered = {k: v for k, v in r.items() if k.lower() not in ignore_lower}
        # Lower keys para determinismo
        filtered = {str(k).lower(): v for k, v in filtered.items()}
        out.append(filtered)
    # Orden por primera clave si existe
    if out and isinstance(out[0], dict) and out[0]:
        first_key = next(iter(out[0].keys()))
        try:
            out.sort(key=lambda x: str(x.get(first_key, "")))
        except Exception:
            pass
    return out


# ---- Generic dispatcher ----

def _normalizar_literals(val, ignore):
    if not isinstance(val, list):
        return val
    out = []
    for lit in val:
        if not isinstance(lit, dict):
            out.append(lit)
            continue
        d = dict(lit)
        if "text" in d and isinstance(d["text"], str):
            d["text"] = d["text"].rstrip(" ")
        if "color" in d:
            d["color"] = _norm_color(str(d["color"]))
        out.append(d)
    return out


def _normalizar_grid(val, ignore):
    if not isinstance(val, list):
        return val
    # Grids son listas de strings 24x80; normaliza trimming trailing espacios opcional si ignore contiene grid?
    # Por spec, compara línea a línea; aquí solo asegura que sean str
    return [str(s) for s in val]


def normalizar_observables(observables: list[dict], ignore: list[str] | None = None) -> list[dict]:
    """Aplica normalización por kind; deja pasar kinds desconocidos."""
    out: list[dict] = []
    for obs in observables:
        kind = str(obs.get("kind", "")).lower()
        val = obs.get("value")
        name = obs.get("name", kind)
        if kind == "display" and isinstance(val, dict):
            out.append(observable_display(val, name=name, ignore=ignore))
        elif kind in ("display_literals", "display_literals") and isinstance(val, list):
            out.append({"kind": "display_literals", "name": name, "value": _normalizar_literals(val, ignore)})
        elif kind == "display_grid" and isinstance(val, list):
            out.append({"kind": "display_grid", "name": name, "value": _normalizar_grid(val, ignore)})
        elif kind == "display_raw" and isinstance(val, str):
            out.append({"kind": "display_raw", "name": name, "value": str(val).lower().strip()})
        elif kind == "joblog" and isinstance(val, list):
            out.append({"kind": "joblog", "name": name, "value": normalizar_joblog(val, ignore)})
        elif kind == "libl" and isinstance(val, list):
            out.append({"kind": "libl", "name": name, "value": normalizar_libl(val, ignore)})
        elif kind == "objects" and isinstance(val, list):
            out.append({"kind": "objects", "name": name, "value": normalizar_objects(val, ignore)})
        elif kind == "db" and isinstance(val, list):
            out.append({"kind": "db", "name": name, "value": normalizar_db(val, ignore)})
        elif kind == "return":
            try:
                v = int(val) if val is not None else 0
            except Exception:
                v = val
            out.append({"kind": "return", "name": name, "value": v})
        else:
            out.append(obs)
    return out
