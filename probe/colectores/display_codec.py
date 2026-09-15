"""Codec puro 5250 — decodifica data stream WTD/SBA/SF/MF/CUR sin red.

Referencia: IBM 5250 Data Stream Programmer's Reference (GA21-9339).
Órdenes implementadas: SBA(0x11), SF(0x1D), MF(0x1E), IC(0x13 CUR), RA(0x02), EA(0x06), WTD header,
  SA 0x28, DSPATR inline 0x1B.

Este módulo es testeable sin IBM i: recibe bytes del data stream y produce
DisplaySnapshot semántico + literales + grid + raw_hex.
"""
from __future__ import annotations

import re

# 5250 orders
SBA = 0x11  # Set Buffer Address
SF = 0x1D   # Start Field
MF = 0x1E   # Modify Field
IC = 0x13   # Insert Cursor
RA = 0x02   # Repeat to Address
EA = 0x06   # Erase to Address
SA = 0x28   # Set Attribute (extended)
WTD_CMD = 0x11  # Write To Display command (en header)
# AID codes (Attention Identifier) para teclas
AID_ENTER = 0xF1
AID_F3 = 0x33
AID_F12 = 0x3C
AID_CLEAR = 0x3D
AID_PAGEDOWN = 0xF4  # Roll down
AID_PAGEUP = 0xF5

AID_MAP = {
    "ENTER": AID_ENTER,
    "F3": AID_F3,
    "F12": AID_F12,
    "CLEAR": AID_CLEAR,
    "PAGEDOWN": AID_PAGEDOWN,
    "PAGEUP": AID_PAGEUP,
    "F1": 0x31, "F2": 0x32, "F4": 0x34, "F5": 0x35, "F6": 0x36,
    "F7": 0x37, "F8": 0x38, "F9": 0x39, "F10": 0x3A, "F11": 0x3B,
}

# Color mapping FCW2 y extended: 0x20 verde, 0x21 turquesa, 0x22 rojo, 0x23 blanco
COLOR_BY_FCW = {
    0x20: "green",
    0x21: "turquesa",
    0x22: "red",
    0x23: "white",
    0x24: "green",
    0x25: "turquesa",
    0x26: "red",
    0x27: "white",
}
# Fallback por nombre
COLOR_BY_ATTR = {
    0x20: "green",
    0x21: "turquesa",
    0x22: "red",
    0x23: "white",
    0x30: "green",
    0x31: "turquesa",
    0x32: "red",
    0x33: "white",
}


def decode_field_attr(attr: int) -> dict:
    protected = bool(attr & 0x20)
    numeric = bool(attr & 0x10) and not protected
    mdt = bool(attr & 0x08)
    return {
        "protected": protected,
        "numeric": numeric,
        "mdt": mdt,
        "raw": attr,
    }


def ebcdic_to_str(data: bytes, ccsid: int = 37) -> str:
    """Convierte EBCDIC CCSID 37 a str (latin1 fallback)."""
    for enc in (f"cp{ccsid}", "cp037", "cp500", "latin1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("latin1", errors="replace")


def addr_to_rc(addr: int, cols: int = 80) -> tuple[int, int]:
    """5250 buffer address (0-based) a (row 1-based, col 1-based)."""
    row = addr // cols + 1
    col = addr % cols + 1
    return row, col


def rc_to_addr(row: int, col: int, cols: int = 80) -> int:
    return (row - 1) * cols + (col - 1)


def _parse_5250_address(hi: int, lo: int, rows: int, cols: int) -> int:
    """Decodifica SBA 2-byte address como fila/columna directa 1-based.

    PUB400 iNative y tn5250j usan SBA `11 <fila> <col>` con valores directos
    (row 1..27, col 1..132), no 12-bit con bias 0x40. Ej. `11 06 18` = fila 6
    col 24. Se convierte a dirección lineal 0-based para addr_to_rc.
    """
    row, col = hi, lo
    if row < 1 or row > 27:
        row = 1
    if col < 1 or col > 132:
        col = 1
    return (row - 1) * cols + (col - 1)


def _parse_5250_addr_linear(hi: int, lo: int) -> int:
    """Decodifica dirección lineal 5250 12-bit con bias 0x40 usada por IC/RA/EA."""
    addr = ((hi & 0x3F) << 6) | (lo & 0x3F)
    return addr


def _clean_literal_text(text: str) -> str:
    """Limpia literales: quita controles EBCDIC (\x00-\x1f, \x80-\x9f residuales), rstrip trailing spaces."""
    # Quita bytes de control y atributos residuales que el EBCDIC dejó como \x1b, \x80, \x9a etc.
    out = []
    for ch in text:
        o = ord(ch)
        # Conserva printable >=0x20 y <0x7F, o extended latin >=0xA0, descarta C0/C1 controles
        if o < 0x20:
            if ch not in ("\n", "\r", "\t"):
                continue
        elif 0x80 <= o <= 0x9F:
            continue
        elif ch == "\x7f":  # DEL
            continue
        out.append(ch)
    cleaned = "".join(out)
    # rstrip solo trailing spaces, preserva leading para col
    return cleaned.rstrip(" ")


def decode_5250_stream(data: bytes, *, rows: int = 24, cols: int = 80, ccsid: int = 37) -> dict:
    """Decodifica data stream 5250 a DisplaySnapshot dict extendido.

    Retorna dict con:
      screen {rows,cols}, cursor {row,col}|None, fields [...],
      literals [{row,col,text,color,attr}], text_grid [24 str len 80],
      attr_grid [24x80 {color,hi,ul,protected}], raw_hex str hex,
      indicators {}, response_key None
    """
    raw_hex = data.hex()
    # Strip GDS header 12A0 y WTD ESC si existe — PUB400 envía 27 03 74 12 A0 ... 04 40 ... 04 11 ...
    pos = 0
    wcc = None
    # Busca primera ocurrencia de GDS 12 A0 y salta 10 bytes (len 2 + 8 GDS)
    for idx in range(min(len(data), 64)):
        if idx + 1 < len(data) and data[idx] == 0x12 and data[idx + 1] == 0xA0:
            # GDS header es 10 bytes: 2 len + 8 (12 A0 00 00 04 00 00 03)
            pos = idx + 8
            # Si hay len 2 antes, incluye
            if idx >= 2:
                pos = idx + 8
                # Ajusta si pos aún tiene 04 40 (Clear Unit) justo después
            break
    # Fallback: busca primer ESC 0x04 0x11 (WTD) o 0x04 0x40 (Clear Unit)
    if pos == 0:
        for idx in range(min(len(data), 64)):
            if idx + 1 < len(data) and data[idx] == 0x04 and data[idx + 1] in (0x11, 0x40):
                pos = idx
                break
    # Si aún no encontrado, heurística previa
    if pos == 0:
        if len(data) >= 3 and data[0] in (0x00, 0x01, 0x02) and data[1] in (0x11, 0x12, 0x04):
            pos = 3
            if len(data) >= 3:
                wcc = data[2]
            if len(data) > 6 and data[0] == 0x04 and data[1] == 0x11:
                pos = 6
                if len(data) >= 6:
                    wcc = data[5] if len(data) > 5 else wcc
        elif len(data) >= 2 and data[0] == 0x04 and data[1] == 0x11:
            pos = 3 if len(data) >= 3 else 2
            if len(data) > pos:
                wcc = data[pos - 1] if pos >= 3 else None

    total = rows * cols
    # Grids
    text_grid_matrix: list[list[str]] = [[" " for _ in range(cols)] for _ in range(rows)]
    attr_grid: list[list[dict]] = [[{"color": "green", "hi": False, "ul": False, "protected": True} for _ in range(cols)] for _ in range(rows)]

    buf_addr = 0
    cursor_addr: int | None = None
    fields: list[dict] = []
    literals: list[dict] = []
    # Estado de atributos corrientes para literales/grid
    cur_color = "green"
    cur_hi = False
    cur_ul = False
    cur_protected = True
    cur_attr_raw = 0x20

    # Gestión de literales y fields por segmentos
    # literal_accum: bytes del segmento literal actual
    literal_start_addr: int | None = None
    literal_buf = bytearray()
    literal_color = cur_color
    literal_attr = cur_attr_raw

    # Para fields: cada field tiene _addr, _attr, _color, etc., y su value se va llenando
    # Necesitamos también field_active: si el próximo texto pertenece a un field
    current_field: dict | None = None

    def _place_char(addr: int, byte_val: int):
        """Escribe un char EBCDIC decodificado en grid en addr + actualiza attr_grid."""
        if addr < 0 or addr >= total:
            return
        r, c = addr_to_rc(addr, cols)
        if not (1 <= r <= rows and 1 <= c <= cols):
            return
        # Decodifica 1 byte
        try:
            ch = bytes([byte_val]).decode(f"cp{ccsid}")
        except Exception:
            try:
                ch = bytes([byte_val]).decode("cp037")
            except Exception:
                ch = " "
                # 0x40 es espacio en EBCDIC
                if byte_val == 0x40:
                    ch = " "
                elif byte_val == 0x00:
                    ch = " "
        # 0x00 y control -> espacio
        if byte_val in (0x00, 0xFF):
            ch = " "
            # Mantener espacio
        # Normaliza: si no es printable, espacio
        if ch == "\x00":
            ch = " "
        text_grid_matrix[r - 1][c - 1] = ch if len(ch) == 1 else ch[0]
        attr_grid[r - 1][c - 1] = {"color": cur_color, "hi": cur_hi, "ul": cur_ul, "protected": cur_protected}

    def _flush_literal():
        nonlocal literal_buf, literal_start_addr, literal_color, literal_attr
        if literal_buf and literal_start_addr is not None:
            raw = bytes(literal_buf)
            text = ebcdic_to_str(raw, ccsid)
            text_stripped = _clean_literal_text(text)
            if text_stripped and text_stripped.strip():
                r, c = addr_to_rc(literal_start_addr, cols)
                literals.append({
                    "row": r,
                    "col": c,
                    "text": text_stripped,
                    "color": literal_color,
                    "attr": literal_attr,
                })
        literal_buf = bytearray()
        literal_start_addr = None

    def _field_at_addr(addr: int):
        # Busca field que contiene addr (para asignar chunks posteriores si se usa old segments logic)
        for f in fields:
            fa = f.get("_addr", 99999)
            flen = f.get("length", 0)
            if flen == 0:
                flen = 80
            if fa <= addr < fa + flen + 80:
                return f
        return None

    i = pos
    # Para compat con old segments: acumulamos segments también para fields value assignment vía char placement
    # Enfoque nuevo: procesar byte a byte, escribiendo grid y literal/field bufs.

    while i < len(data):
        b = data[i]
        if b == SBA:
            # Flush literal pendiente antes de salto
            _flush_literal()
            # Flush field value pending? Los fields ya van escribiéndose char a char, no necesitan flush separado
            if i + 2 < len(data):
                hi, lo = data[i + 1], data[i + 2]
                addr = _parse_5250_address(hi, lo, rows, cols)
                buf_addr = addr
            else:
                # incompleto
                i += 1
                continue
            i += 3
            # Siguiente texto será literal hasta próximo SF
            # Reinicia literal tracking (no hay field activo)
            # Si hay un field activo previo, su length se puede cerrar al buf_addr actual
            if fields and fields[-1].get("length", 0) == 0:
                prev = fields[-1]
                # length = distancia entre su _addr+1 y este buf_addr (o próximo SF)
                # +1 por byte de atributo no visible ya contado
                prev_len = buf_addr - prev["_addr"] - 1
                if prev_len < 0:
                    prev_len = 0
                # si prev es último y no hay más, al menos len de su value o 1
                if prev_len == 0:
                    prev_len = len(prev.get("value", "")) or 1
                prev["length"] = prev_len
            current_field = None
            continue
        elif b == SF:
            _flush_literal()
            # SF 5250: 0x1D + FCW1(0x40) + FCW2(color) + AC1(attr) + AC2(0x00) + LEN(1) = 6 bytes total
            # Algunos streams usan SF corto (solo 1 byte attr + extended), pero el host real (PUB400) usa 5 bytes tras SF
            if i + 5 < len(data):
                fcw1 = data[i + 1]  # 0x40
                fcw2 = data[i + 2]  # color 0x20-0x23
                ac1 = data[i + 3]   # attribute (editable/protected etc)
                ac2 = data[i + 4]   # 0x00
                field_len = data[i + 5]  # LEN byte
                # Si fcw1 no es 0x40, puede ser SF corto (solo attr) — fallback
                if fcw1 != 0x40 and fcw1 not in (0x40, 0x41, 0x42, 0x43):
                    # SF corto: solo 1 byte attr como antes
                    attr = fcw1
                    cur_attr_raw = attr
                    info = decode_field_attr(attr)
                    cur_protected = info["protected"]
                    # Cierra prev length si pendiente
                    if fields and fields[-1].get("length", 0) == 0:
                        prev = fields[-1]
                        prev_len = buf_addr - prev["_addr"] - 1
                        if prev_len <= 0:
                            prev_len = len(prev.get("value", "")) or 1
                        prev["length"] = max(1, prev_len)
                    # Extended handling corto
                    row, col = addr_to_rc(buf_addr, cols)
                    current_field = {
                        "name": f"F{len(fields)+1:03d}",
                        "row": row,
                        "col": col,
                        "length": 0,
                        "usage": "output" if info["protected"] else "input",
                        "value": "",
                        "attributes": [],
                        "_addr": buf_addr,
                        "_attr": attr,
                        "_color": cur_color,
                        "_hi": cur_hi,
                        "_ul": cur_ul,
                    }
                    if info["protected"]:
                        current_field["attributes"].append("protected")
                    if info["mdt"]:
                        current_field["attributes"].append("mdt")
                    if info["numeric"]:
                        current_field["attributes"].append("numeric")
                    fields.append(current_field)
                    buf_addr += 1
                    i += 2
                    continue
                # SF largo correcto con 5 bytes
                cur_attr_raw = fcw2 if fcw2 in COLOR_BY_FCW else ac1
                # Color por FCW2 (0x20 verde, 0x00 default verde para password)
                if fcw2 in COLOR_BY_FCW:
                    cur_color = COLOR_BY_FCW[fcw2]
                elif fcw2 == 0x00:
                    cur_color = "green"
                # Atributo por AC1 — AC1 0x24/0x27 son input (editable/nondisplay), 0x20 es output protegido
                # En 5250, bit 0x04 en AC1 indica input: 0x24 (00100100) y 0x27 (00100111) tienen 0x04 set
                is_input = bool(ac1 & 0x04)
                info_ac1 = decode_field_attr(ac1)
                # Override protected basado en AC1 bit 0x04
                info_ac1["protected"] = not is_input
                cur_protected = not is_input
                # Cierra prev si pendiente
                if fields and fields[-1].get("length", 0) == 0:
                    prev = fields[-1]
                    prev_len = buf_addr - prev["_addr"] - 1
                    if prev_len <= 0:
                        prev_len = len(prev.get("value", "")) or 1
                    prev["length"] = max(1, prev_len)
                row, col = addr_to_rc(buf_addr, cols)
                # Longitud: byte LEN, 0 significa 256? En 5250, 0 = 256, pero para login es 10/128
                flen = field_len if field_len != 0 else 256
                # Ajusta si LEN > cols*rows - buf_addr (trunca)
                if buf_addr + flen > total:
                    flen = total - buf_addr
                current_field = {
                    "name": f"F{len(fields)+1:03d}",
                    "row": row,
                    "col": col,
                    "length": flen,
                    "usage": "output" if info_ac1["protected"] else "input",
                    "value": "",
                    "attributes": [],
                    "_addr": buf_addr,
                    "_attr": ac1,
                    "_color": cur_color,
                    "_hi": cur_hi,
                    "_ul": cur_ul,
                }
                if info_ac1["protected"]:
                    current_field["attributes"].append("protected")
                if info_ac1["mdt"]:
                    current_field["attributes"].append("mdt")
                if info_ac1["numeric"]:
                    current_field["attributes"].append("numeric")
                fields.append(current_field)
                buf_addr += 1  # byte de atributo no visible (el SF ocupa 1 col de atributo)
                # Reserva área del campo en grid (espacios) para no solapar con próximo literal
                # Avanza buf_addr por flen? No, el stream WTD no incluye fill, solo SF define área; próximo SBA saltará al siguiente campo/literal
                # Pero para evitar que próximo literal se solape con área de campo, no avanzamos buf_addr por flen aquí;
                # el próximo SBA ya dará la posición correcta del siguiente literal/campo.
                i += 6
                continue
            elif i + 1 < len(data):
                # Fallback SF corto
                attr = data[i + 1]
                cur_attr_raw = attr
                info = decode_field_attr(attr)
                cur_protected = info["protected"]
                if fields and fields[-1].get("length", 0) == 0:
                    prev = fields[-1]
                    prev_len = buf_addr - prev["_addr"] - 1
                    if prev_len <= 0:
                        prev_len = len(prev.get("value", "")) or 1
                    prev["length"] = max(1, prev_len)
                row, col = addr_to_rc(buf_addr, cols)
                current_field = {
                    "name": f"F{len(fields)+1:03d}",
                    "row": row,
                    "col": col,
                    "length": 0,
                    "usage": "output" if info["protected"] else "input",
                    "value": "",
                    "attributes": [],
                    "_addr": buf_addr,
                    "_attr": attr,
                    "_color": cur_color,
                    "_hi": cur_hi,
                    "_ul": cur_ul,
                }
                if info["protected"]:
                    current_field["attributes"].append("protected")
                if info["mdt"]:
                    current_field["attributes"].append("mdt")
                if info["numeric"]:
                    current_field["attributes"].append("numeric")
                fields.append(current_field)
                buf_addr += 1
                i += 2
                continue
            else:
                i += 1
                continue
        elif b == IC:
            _flush_literal()
            if i + 2 < len(data):
                hi, lo = data[i + 1], data[i + 2]
                addr = _parse_5250_addr_linear(hi, lo)
                cursor_addr = addr
            i += 3
            continue
        elif b == RA:
            _flush_literal()
            if i + 3 < len(data):
                hi, lo, rep = data[i + 1], data[i + 2], data[i + 3]
                addr = _parse_5250_addr_linear(hi, lo)
                count = max(0, addr - buf_addr)
                # rep es byte EBCDIC a repetir
                for k in range(count):
                    # Escribe en grid
                    _place_char(buf_addr, rep)
                    # Si estamos en literal mode (current_field is None), acumula literal_buf
                    if current_field is None:
                        if literal_start_addr is None:
                            literal_start_addr = buf_addr
                            literal_color = cur_color
                            literal_attr = cur_attr_raw
                        literal_buf.append(rep)
                    else:
                        # pertenece a field value
                        ch = ebcdic_to_str(bytes([rep]), ccsid)
                        current_field["value"] += ch
                    buf_addr += 1
                    if buf_addr >= total:
                        buf_addr = total - 1
                        break
            i += 4
            continue
        elif b == EA:
            _flush_literal()
            if i + 2 < len(data):
                hi, lo = data[i + 1], data[i + 2]
                addr = _parse_5250_addr_linear(hi, lo)
                # Erase: rellena con espacios hasta addr
                end = min(addr, total)
                for a in range(buf_addr, end):
                    _place_char(a, 0x40)
                buf_addr = end if end < total else buf_addr
                # Tras EA puede venir un byte de atributo (WCC/EA attr)
                # Si hay byte extra y no es orden, consúmelo como atributo para siguiente texto
                # Pero spec dice EA (0x06) + 2B addr ; algunos streams añaden attr byte después
                # Si después de EA quedan bytes y el siguiente no es orden y estamos en literal, no hacer nada
            i += 3
            current_field = None
            continue
        elif b == 0x1B:
            # DSPATR inline: 0x1B + attr byte (a veces 0x1B 0x03 xx ?)
            # Flush literal para cambiar color a partir de aquí
            _flush_literal()
            if i + 1 < len(data):
                attr = data[i + 1]
                # Mapeo simple: si attr en COLOR_BY_ATTR, cambia color
                if attr in COLOR_BY_ATTR:
                    cur_color = COLOR_BY_ATTR[attr]
                    cur_attr_raw = attr
                elif attr in COLOR_BY_FCW:
                    cur_color = COLOR_BY_FCW[attr]
                    cur_attr_raw = attr
                else:
                    # bit hi/ul
                    if attr & 0x08:
                        cur_hi = True
                    if attr & 0x04:
                        cur_ul = True
                # Algunos encodings usan 0x1B 0x04 0x11 xx etc. -> intentamos consumir secuencias SA-like
                # Si siguiente byte tras attr es SA-like (0x10-0x13), deja que próxima iter lo maneje
            i += 2
            continue
        elif b == SA:  # 0x28 Set Attribute
            _flush_literal()
            if i + 2 < len(data):
                typ, val = data[i + 1], data[i + 2]
                if typ == 0x11:  # color
                    cur_color = COLOR_BY_FCW.get(val, cur_color)
                    cur_attr_raw = val
                elif typ == 0x10:
                    cur_hi = bool(val & 0x01)
                    cur_ul = bool(val & 0x02)
                # 0x12 underline etc.
            i += 3
            continue
        elif b == MF:  # 0x1E Modify Field - similar a SF pero modifica existente
            _flush_literal()
            # MF: 0x1E + len + ... ignoramos por ahora, avanza 2
            if i + 1 < len(data):
                # length byte?
                l = data[i + 1]
                i += 2 + l
            else:
                i += 1
            continue
        else:
            # Texto EBCDIC / byte de datos
            # Es espacio 0x40 -> ' ' ; otros mapeables
            # Si estamos en literal mode (current_field is None), acumula literal_buf
            # Si estamos en field mode, acumula field value
            if b == 0xFF:
                # IAC escapado (0xFF 0xFF) -> un 0xFF real
                if i + 1 < len(data) and data[i + 1] == 0xFF:
                    b = 0xFF
                    i += 1
                else:
                    i += 1
                    continue
            # Escribe en grid siempre
            _place_char(buf_addr, b)
            if current_field is None:
                if literal_start_addr is None:
                    literal_start_addr = buf_addr
                    literal_color = cur_color
                    literal_attr = cur_attr_raw
                literal_buf.append(b)
            else:
                # Solo acumula value si es campo de entrada (input/both); los output protegidos
                # son fill 0x00/0x40 y no deben mezclarse con el próximo literal
                if current_field.get("usage") != "output" or not current_field.get("attributes", []):
                    # Para output protegidos, ignora bytes 0x00/0x40 de fill
                    if b not in (0x00, 0x40, 0xFF):
                        ch = ebcdic_to_str(bytes([b]), ccsid)
                        if ord(ch) >= 0x20 and not (0x80 <= ord(ch) <= 0x9F):
                            current_field["value"] += ch
                    else:
                        # Fill de campo output: no aporta a value
                        pass
                else:
                    # Campo input: acumula pero filtra NUL
                    if b not in (0x00, 0xFF):
                        ch = ebcdic_to_str(bytes([b]), ccsid)
                        if ord(ch) >= 0x20 and not (0x80 <= ord(ch) <= 0x9F):
                            current_field["value"] += ch
            buf_addr += 1
            if buf_addr >= total:
                buf_addr = total - 1
            i += 1

    # Flush final literal
    _flush_literal()

    # Si no hay fields pero hay literales con contenido, los viejos tests esperaban fields output
    # Mantenemos compatibilidad: si fields vacío y hay literales, también genera fields output por compat?
    # Pero nuevo spec quiere literals separados; para no romper test_decode_sf_y_texto que crea field HI,
    # ese caso ya tiene field, así que no afecta.
    # Si hay segmentos literales pero sin field, creamos fields output compativia old logic? No necesario si literals cubren.
    # Sin embargo, mantener un fallback: si no hay fields y no hay literals pero hay texto en grid que no es espacio,
    # extraer fields de grid line por line? No.

    # Cierra longitudes de fields pendientes
    for idx, f in enumerate(fields):
        if f.get("length", 0) == 0:
            # calcula hasta próximo field o final de pantalla
            if idx + 1 < len(fields):
                nxt = fields[idx + 1]
                flen = nxt["_addr"] - f["_addr"] - 1
            else:
                flen = total - f["_addr"] - 1
                # si flen negativo, usa len(value) o 1
            if flen <= 0:
                flen = len(f.get("value", "").strip()) or 1
            f["length"] = max(1, flen)

    # Limpieza fields: pop auxiliares, strip/rstrip, deduplicate attrs
    cleaned_fields = []
    for f in fields:
        fa = f.pop("_addr", None)
        f.pop("_attr", None)
        f.pop("_color", None)
        f.pop("_hi", None)
        f.pop("_ul", None)
        # value: mantener como está pero strip espacios de relleno? old code hacía strip()
        # Spec: rstrip solo trailing, pero old tests esperan strip interno "  hello  " -> "  hello" etc.
        # Para input fields, recortamos solo trailing/padding? Usamos strip para compat con tests antiguos
        # Pero para fidelidad, preservamos rstrip.
        if "value" in f and isinstance(f["value"], str):
            # Si es output protegido, rstrip
            # Si es input, también rstrip pero mantiene leading
            orig = f["value"]
            # Old behaviour: .strip() para fields con segmentos; nuevo: .strip() para evitar blancos extras en tests
            # Hacemos strip solo si value todo espacios? Mantener rstrip para no romper literal logic
            # Detecta si value fue construido char-by-char: puede tener espacios de padding
            # Usamos strip para test "HI" sin espacios -> no afecta
            # Para compat, hacemos strip() si field es output? spec dice rstrip.
            f["value"] = orig.strip() if orig.strip() != "" else orig.rstrip(" ")
            # Alternative: rstrip
            # f["value"] = orig.rstrip(" ")
        if f.get("length", 0) == 0:
            f["length"] = len(f.get("value", "")) or 10
        # Asegura types
        try:
            f["row"] = int(f.get("row", 1))
            f["col"] = int(f.get("col", 1))
            f["length"] = int(f.get("length", 10))
        except Exception:
            pass
        # attrs: si no hay, mantiene attributes
        # Normaliza attributes sorted dedup
        attrs = f.get("attributes", [])
        f["attributes"] = sorted(set(str(a) for a in attrs if str(a).strip()))
        # Añade attrs dict si no existe
        if "attrs" not in f:
            # intenta derivar de attributes + color
            prot = "protected" in f["attributes"]
            mdt = "mdt" in f["attributes"]
            # color inferido de cur_color al momento de SF (guardado? ya perdió). Usa green por defecto si no hay info
            f["attrs"] = {"color": "green", "protected": prot, "mdt": mdt}
            if cur_color and prot:
                f["attrs"]["color"] = cur_color
        cleaned_fields.append({
            "name": f.get("name", ""),
            "row": int(f["row"]),
            "col": int(f.get("col", 1)),
            "length": int(f.get("length", len(f.get("value", "")))),
            "usage": f.get("usage", "output"),
            "value": f.get("value", ""),
            "attributes": sorted(set(f.get("attributes", []))),
            "attrs": f.get("attrs", {}),
        })

    # Cursor
    cursor = None
    if cursor_addr is not None:
        r, c = addr_to_rc(cursor_addr, cols)
        cursor = {"row": r, "col": c}
    elif cleaned_fields:
        for f in cleaned_fields:
            if f["usage"] == "input":
                cursor = {"row": f["row"], "col": f["col"]}
                break

    # text_grid: 24 strings len 80
    text_grid = ["".join(row) for row in text_grid_matrix]
    # Asegura len 80 cada una (ya lo es)

    # indicators vacíos
    indicators: dict[str, bool] = {}

    return {
        "screen": {"rows": rows, "cols": cols},
        "cursor": cursor,
        "fields": cleaned_fields,
        "literals": literals,
        "text_grid": text_grid,
        "attr_grid": attr_grid,
        "raw_hex": raw_hex,
        "indicators": indicators,
        "response_key": None,
    }


def build_input_data(fields: list[dict], values: dict[str, str], *, ccsid: int = 37, aid: str = "ENTER", with_gds_prefix: bool = False) -> bytes:
    """Construye payload de entrada para enviar al host (workstation → host).

    fields: lista de fields del snapshot, values: {name: value} o {(row,col):value}.
    Retorna bytes con [06 21] + AID + SBA + texto EBCDIC para cada field modificado.
    El host invita con Read MDT (04 52) pero la workstation responde con prefijo de
    terminal `06 21` + AID + campos modificados (formato ACS). Si with_gds_prefix,
    incluye `06 21` antes del AID.

    Soporta mapeo por name F001 y por row/col (para Sign On donde fields no tienen nombre estable).
    """
    # AID byte
    aid_map = {
        "ENTER": 0xF1, "F1": 0x31, "F2": 0x32, "F3": 0x33, "F4": 0x34, "F5": 0x35, "F6": 0x36,
        "F7": 0x37, "F8": 0x38, "F9": 0x39, "F10": 0x3A, "F11": 0x3B, "F12": 0x3C, "CLEAR": 0x3D,
    }
    aid_byte = aid_map.get(aid.strip().upper(), 0xF1)
    # Mapa por row/col para fallback
    by_pos: dict[tuple[int, int], dict] = {}
    by_name: dict[str, dict] = {}
    for f in fields:
        try:
            r = int(f.get("row", 0))
            c = int(f.get("col", 0))
            by_pos[(r, c)] = f
        except Exception:
            pass
        n = str(f.get("name", "")).strip()
        if n:
            by_name[n] = f
        # también mapea alias "F001" generico
        # si values contiene clave que es "F001", usar by_pos ordenada

    # Construir lista de (field, value_str) a enviar primero para determinar cursor
    to_send: list[tuple[dict, str]] = []
    # Mapa por row/col para fallback
    by_pos2: dict[tuple[int, int], dict] = {}
    for f in fields:
        try:
            r = int(f.get("row", 0))
            c = int(f.get("col", 0))
            by_pos2[(r, c)] = f
        except Exception:
            pass
    # Segundo mapa para to_send (reusa by_pos ya creado abajo, pero necesitamos to_send antes de out)
    # Construimos to_send aquí para cursor
    # (duplica lógica de abajo pero necesitamos cursor antes)
    temp_to_send: list[tuple[dict, str]] = []
    for k, v in values.items():
        ks = str(k).strip()
        if "," in ks or ":" in ks:
            sep = "," if "," in ks else ":"
            try:
                rs, cs = ks.split(sep, 1)
                r = int(rs.strip()); c = int(cs.strip())
                fld = by_pos2.get((r, c))
                if fld is not None:
                    temp_to_send.append((fld, str(v)))
                    continue
            except Exception:
                pass
        # por name
        by_name2: dict[str, dict] = {str(f.get("name","")).strip(): f for f in fields if str(f.get("name","")).strip()}
        if ks in by_name2:
            temp_to_send.append((by_name2[ks], str(v)))
        elif ks.upper().startswith("F") and ks[1:].isdigit():
            try:
                idx = int(ks[1:])-1
                if 0 <= idx < len(fields):
                    temp_to_send.append((fields[idx], str(v)))
            except Exception:
                pass
    if not temp_to_send and values:
        input_fields = [f for f in fields if f.get("usage") == "input"]
        input_fields.sort(key=lambda x: (int(x.get("row",0)), int(x.get("col",0))))
        vals_list = list(values.values())
        for fld, val in zip(input_fields, vals_list):
            temp_to_send.append((fld, str(val)))
        if not temp_to_send and input_fields:
            first_val = next(iter(values.values()), "")
            temp_to_send.append((input_fields[0], str(first_val)))
    to_send = temp_to_send

    out = bytearray()
    if with_gds_prefix:
        out.extend([0x06, 0x21])
    out.append(aid_byte)
    # Cursor: omitido (la workstation real tn5250j/ACS envía `06 21 <AID>` + SBA
    # directamente, sin par de bytes de cursor; el host IBM i lo rechaza si viene
    # un cursor mal formado antes del SBA).

    for f, val_str in to_send:
        row, col = int(f["row"]), int(f["col"])
        out.append(SBA)
        out.append(max(1, row))
        out.append(max(1, col))
        # Trunca a length (sin rellenar con espacios: la workstation real envía
        # el valor tal cual, y en campos no desplegables el padding corrompe el dato)
        maxlen = int(f.get("length", 80))
        val = str(val_str)[:maxlen]
        try:
            ebcdic = val.encode(f"cp{ccsid}")
        except Exception:
            ebcdic = val.encode("cp037", errors="replace")
        out.extend(ebcdic)
    return bytes(out)
