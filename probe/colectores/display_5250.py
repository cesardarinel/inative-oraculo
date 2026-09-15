"""Cliente TN5250 + decodificador — captura DisplaySnapshot con coordenadas.

Negocia TELNET (IAC WILL/DO/WONT/DONT, SB TERMINAL-TYPE, NAWS, EOR, BINARY),
envía EBCDIC + AIDs, recibe data stream y decodifica vía display_codec.
"""
from __future__ import annotations

import socket
import struct
import time
from dataclasses import dataclass, field

from .display_codec import AID_MAP, decode_5250_stream, ebcdic_to_str

# Telnet constants
IAC = 0xFF
DO = 0xFD
DONT = 0xFE
WILL = 0xFB
WONT = 0xFC
SB = 0xFA
SE = 0xF0
EOR = 0x19  # 25 = EOR
BINARY = 0x00
ECHO = 0x01
SGA = 0x03
TERMINAL_TYPE = 0x18
NAWS = 0x1F
NEW_ENVIRON = 0x27

# 5250 specific: device name negotiation
DEV_NAME_OPT = 0x00  # custom

# AID bytes for sending
AID_BYTES = {
    "ENTER": bytes([0xF1]),
    "F1": bytes([0x31]), "F2": bytes([0x32]), "F3": bytes([0x33]),
    "F4": bytes([0x34]), "F5": bytes([0x35]), "F6": bytes([0x36]),
    "F7": bytes([0x37]), "F8": bytes([0x38]), "F9": bytes([0x39]),
    "F10": bytes([0x3A]), "F11": bytes([0x3B]), "F12": bytes([0x3C]),
    "CLEAR": bytes([0x3D]), "PAGEDOWN": bytes([0xF4]), "PAGEUP": bytes([0xF5]),
    "HELP": bytes([0xF3]), "ROLLUP": bytes([0xF4]), "ROLLDOWN": bytes([0xF5]),
}


@dataclass
class DisplaySnapshot:
    """Snapshot semántico extendido — incluye literales, grid y raw_hex (03-fidelidad)."""

    rows: int = 24
    cols: int = 80
    cursor: dict | None = None
    fields: list[dict] = field(default_factory=list)
    literals: list[dict] = field(default_factory=list)  # {row,col,text,color,attr}
    text_grid: list[str] = field(default_factory=list)  # 24 x 80
    attr_grid: list[list[dict]] = field(default_factory=list)  # 24x80
    raw_hex: str = ""
    indicators: dict[str, bool] = field(default_factory=dict)
    response_key: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "screen": {"rows": self.rows, "cols": self.cols},
            "cursor": self.cursor,
            "fields": self.fields,
            "indicators": dict(sorted(self.indicators.items())),
            "response_key": self.response_key,
        }
        # Campos extendidos — siempre presentes para comparador
        d["literals"] = list(self.literals)
        d["text_grid"] = list(self.text_grid) if self.text_grid else []
        d["attr_grid"] = [list(row) for row in self.attr_grid] if self.attr_grid else []
        d["raw_hex"] = self.raw_hex
        return d

    def observables(self, *, name: str = "screen") -> dict:
        return {"kind": "display", "name": name, "value": self.to_dict()}

    def observables_extended(self, *, name_prefix: str = "screen") -> list[dict]:
        """Emite observables extendidos: display + display_literals/grid/raw."""
        base = self.observables(name=name_prefix)
        out = [base]
        if self.literals:
            out.append({"kind": "display_literals", "name": "literals", "value": list(self.literals)})
        if self.text_grid:
            out.append({"kind": "display_grid", "name": "grid", "value": list(self.text_grid)})
        if self.raw_hex:
            out.append({"kind": "display_raw", "name": "raw", "value": self.raw_hex})
        return out

    @classmethod
    def from_dict(cls, d: dict) -> "DisplaySnapshot":
        screen = d.get("screen", {})
        return cls(
            rows=int(screen.get("rows", 24)),
            cols=int(screen.get("cols", 80)),
            cursor=d.get("cursor"),
            fields=list(d.get("fields", [])),
            literals=list(d.get("literals", [])),
            text_grid=list(d.get("text_grid", [])),
            attr_grid=list(d.get("attr_grid", [])),
            raw_hex=str(d.get("raw_hex", "")),
            indicators=dict(d.get("indicators", {})),
            response_key=d.get("response_key"),
        )


class TN5250Client:
    """Cliente TN5250 minimalista sobre socket ya conectado."""

    def __init__(self, sock: socket.socket, cfg, cols: int = 80, rows: int = 24):
        self.sock = sock
        self.cfg = cfg
        self.cols = cols
        self.rows = rows
        self.ccsid = int(getattr(cfg, "ccsid", 37) or 37)
        self._buf = bytearray()
        self._negotiated = False
        self._last_snapshot: dict | None = None

    # ---- Telnet negotiation ----
    def negotiate(self, timeout: float = 5.0) -> None:
        """Negocia TELNET básico para sesión 5250."""
        if self._negotiated:
            return
        self.sock.settimeout(timeout)
        # Envía WILL BINARY, WILL EOR, WILL SGA, DO TERMINAL-TYPE, DO NAWS
        to_send = bytearray()
        for opt in (BINARY, EOR, SGA):
            to_send.extend([IAC, WILL, opt])
        to_send.extend([IAC, DO, TERMINAL_TYPE])
        to_send.extend([IAC, DO, NAWS])
        to_send.extend([IAC, WILL, ECHO])
        self._send_raw(bytes(to_send))
        # Envía NAWS con tamaño
        self._send_naws()
        # Envía TERMINAL-TYPE respuesta si el server lo pide (poll)
        end = time.time() + timeout
        while time.time() < end:
            try:
                data = self.sock.recv(4096)
                if not data:
                    break
                self._handle_telnet(data)
                # Si recibimos SB TERMINAL-TYPE SEND, respondemos
                if len(data) > 2:
                    break
            except socket.timeout:
                break
        self._negotiated = True
        self.sock.settimeout(30)

    def _send_raw(self, data: bytes) -> None:
        self.sock.sendall(data)

    def send_frame(self, payload: bytes) -> None:
        """Envía un frame de workstation→host completo como un ACS real:
        GDS (len + 12A0 00 00 04 00 00 03) + payload + IAC EOR.

        El host IBM i (PUB400) espera las respuestas de lectura (login, teclas,
        campos) envueltas en GDS con opcode 03 y prefijo de terminal `06 21`
        antes del AID. Frames raw (sin GDS) se rechazan ('Function key not
        allowed') o se ignoran silenciosamente.
        """
        gds_header = bytes([0x12, 0xA0, 0x00, 0x00, 0x04, 0x00, 0x00, 0x03])
        total_len = 10 + len(payload)
        frame = bytearray()
        frame.append((total_len >> 8) & 0xFF)
        frame.append(total_len & 0xFF)
        frame.extend(gds_header)
        frame.extend(payload)
        frame.extend(bytes([IAC, 0xEF]))
        self.sock.sendall(bytes(frame))

    def send_aid(self, key: str) -> None:
        """Envía una tecla (AID) como workstation→host en GDS con prefijo 06 21."""
        key_u = key.strip().upper()
        aid_b = AID_BYTES.get(key_u, AID_BYTES["ENTER"])
        aid = aid_b[0] if isinstance(aid_b, (bytes, bytearray)) else aid_b
        self.send_frame(bytes([0x06, 0x21, aid]))

    def send_query_reply(self) -> None:
        """Envía una Query Reply (RFC 1205 §5.3) en GDS."""
        reply = (
            b"\x00\x00\x88\x00\x40\xd9\x70\x80\x04\xf3\x00\x05\xd9\x70\x80\x06\x00\x00"
        )
        self.send_frame(reply)

    def _send_naws(self) -> None:
        # SB NAWS cols(2B) rows(2B) IAC SE
        payload = struct.pack("!HHHH", 0, 0, self.cols, self.rows)  # device cols/rows
        # Realmente NAWS es cols, rows en network order (2 bytes cada uno)
        naws = bytes([IAC, SB, NAWS]) + struct.pack("!HH", self.cols, self.rows) + bytes([IAC, SE])
        try:
            self._send_raw(naws)
        except Exception:
            pass

    def _handle_telnet(self, data: bytes) -> bytes:
        """Procesa IAC sequences en data, responde a DO/WILL, retorna payload sin IAC."""
        out = bytearray()
        i = 0
        while i < len(data):
            b = data[i]
            if b == IAC and i + 1 < len(data):
                cmd = data[i + 1]
                if cmd == WILL or cmd == DO:
                    if i + 2 < len(data):
                        opt = data[i + 2]
                        # Responde: DO -> WILL, WILL -> DO para opciones que soportamos
                        if opt in (BINARY, EOR, SGA, TERMINAL_TYPE, NAWS):
                            resp = DO if cmd == WILL else WILL
                        else:
                            resp = WONT if cmd == WILL else DONT
                        try:
                            self._send_raw(bytes([IAC, resp, opt]))
                        except Exception:
                            pass
                        # Si es TERMINAL-TYPE SEND, responde
                        i += 3
                        continue
                elif cmd == SB:
                    # Busca IAC SE
                    se_idx = -1
                    for j in range(i + 2, len(data) - 1):
                        if data[j] == IAC and data[j + 1] == SE:
                            se_idx = j
                            break
                    if se_idx != -1:
                        sb_data = data[i + 2: se_idx]
                        self._handle_sb(sb_data)
                        i = se_idx + 2
                        continue
                    else:
                        # Incompleto, espera más
                        break
                elif cmd == IAC:
                    out.append(IAC)
                    i += 2
                    continue
                else:
                    # EOR, etc. lo ignoramos pero no lo pasamos como payload
                    if cmd == EOR:
                        # Marcador fin de registro 5250
                        pass
                    i += 2
                    continue
            else:
                out.append(b)
                i += 1
        return bytes(out)

    def _handle_sb(self, sb_data: bytes) -> None:
        if not sb_data:
            return
        opt = sb_data[0]
        if opt == TERMINAL_TYPE and len(sb_data) >= 2 and sb_data[1] == 0x01:  # SEND
            # Responde IS "IBM-3477-FC"
            term = b"IBM-3477-FC"
            resp = bytes([IAC, SB, TERMINAL_TYPE, 0x00]) + term + bytes([IAC, SE])
            try:
                self._send_raw(resp)
            except Exception:
                pass
        elif opt == NEW_ENVIRON:
            # IBM i envía DEVNAME; responde con nombre de dispositivo
            devname = (getattr(self.cfg, "user", "QPADEV") or "QPADEV")[:10].upper()
            # Simplified: IS VAR "DEVNAME" VALUE "xxx"
            payload = bytes([0x00]) + devname.encode("ascii")  # tipo 0 = IS
            resp = bytes([IAC, SB, NEW_ENVIRON, 0x00]) + payload + bytes([IAC, SE])
            try:
                self._send_raw(resp)
            except Exception:
                pass

    # ---- 5250 data ----
    def _recv_until_eor(self, timeout: float = 10.0) -> bytes:
        """Lee del socket hasta IAC EOR (0xFF 0xEF)."""
        self.sock.settimeout(timeout)
        buf = bytearray()
        while True:
            chunk = self.sock.recv(8192)
            if not chunk:
                break
            # Busca IAC EOR en chunk
            eor_idx = -1
            for idx in range(len(chunk) - 1):
                if chunk[idx] == IAC and chunk[idx + 1] == 0xEF:  # EOR = 239
                    eor_idx = idx
                    break
            if eor_idx != -1:
                buf.extend(chunk[:eor_idx])
                # Procesa telnet antes de devolver
                payload = self._handle_telnet(bytes(buf))
                return payload
            # También busca IAC 0x19 EOR (242,25) variante
            for idx in range(len(chunk) - 1):
                if chunk[idx] == IAC and chunk[idx + 1] == EOR:
                    eor_idx = idx
                    break
            if eor_idx != -1:
                buf.extend(chunk[:eor_idx])
                payload = self._handle_telnet(bytes(buf))
                return payload
            # No EOR aún, acumula y procesa telnet incrementalmente
            filtered = self._handle_telnet(chunk)
            buf.extend(filtered)
            if len(buf) > 64 * 1024:
                break
        return bytes(buf)

    def send_text(self, text: str) -> None:
        """Envía texto EBCDIC como comando CL (SBA al campo, AID ENTER) en GDS."""
        try:
            ebcdic = text.encode(f"cp{self.ccsid}", errors="replace")
        except Exception:
            ebcdic = text.encode("cp037", errors="replace")
        # Busca campo input (command line) del último snapshot para colocar el texto
        payload = bytes([0x06, 0x21, 0xF1])
        if self._last_snapshot and self._last_snapshot.get("fields"):
            for f in self._last_snapshot["fields"]:
                if f.get("usage") in ("input", "both"):
                    addr = rc_to_addr(int(f["row"]), int(f["col"]), 80)
                    payload += bytes([0x11, 0x40 | ((addr >> 6) & 0x3F), 0x40 | (addr & 0x3F), ])
                    payload += ebcdic
                    break
        else:
            payload += ebcdic
        self.send_frame(payload)

    def send_fields(self, values: dict[str, str], snapshot_fields: list[dict] | None = None, *, aid: str = "ENTER") -> None:
        """Envía valores de campos + AID en GDS, prefijo 06 21 (formato ACS real).

        Mapea por row/col además de por nombre F001 — Sign-On fields no tienen
        nombre estable (03-pantallas-fidelidad §Dependencias).
        Frame: GDS + `06 21 <AID> <SBA dato 1> <SBA dato 2> ...` + IAC EOR.
        """
        from .display_codec import build_input_data
        fields = snapshot_fields or (self._last_snapshot.get("fields", []) if self._last_snapshot else [])
        bits = build_input_data(fields, values, ccsid=self.ccsid, aid=aid, with_gds_prefix=True)
        self.send_frame(bits)

    def capture(self, timeout: float = 10.0) -> dict:
        """Captura siguiente data stream y decodifica a DisplaySnapshot dict extendido."""
        raw = self._recv_until_eor(timeout=timeout)
        if not raw:
            return DisplaySnapshot(rows=self.rows, cols=self.cols).to_dict()
        snap = decode_5250_stream(raw, rows=self.rows, cols=self.cols, ccsid=self.ccsid)
        # raw_hex ya viene en snap, pero asegura que sea el payload post-telnet
        if not snap.get("raw_hex"):
            snap["raw_hex"] = raw.hex()
        self._last_snapshot = snap
        return snap

    def connect_and_login(self, timeout: float = 20.0) -> dict | None:
        """Negocia y espera pantalla de login; retorna primer snapshot si llega."""
        self.negotiate(timeout=5.0)
        try:
            snap = self.capture(timeout=timeout)
            return snap
        except Exception:
            return None

    def login(self, user: str, password: str, *, timeout: float = 15.0, snap: dict | None = None) -> dict:
        """Realiza login completo (sign-on → fields → handshake Query → MAIN).

        Tras enviar user/password+ENTER, el host ejecuta el handshake de Query
        (RFC 1205 §5.3): pide capacidades, el cliente responde Query Reply y el
        host apaga la luz de mensaje, y solo entonces muestra el menú principal.
        Este helper lo maneja para iNative local y PUB400.
        Retorna snapshot del MAIN.
        """
        if snap is None:
            snap = self.capture(timeout=timeout)  # sign-on
        fields = snap.get("fields", [])
        # Envía user+password al primer y segundo campo input
        vals: dict[str, str] = {}
        input_fields = [f for f in fields if f.get("usage") == "input"]
        if len(input_fields) >= 2:
            vals[input_fields[0].get("name") or f"{input_fields[0]['row']},{input_fields[0]['col']}"] = user
            vals[input_fields[1].get("name") or f"{input_fields[1]['row']},{input_fields[1]['col']}"] = password
        elif len(input_fields) == 1:
            vals[input_fields[0].get("name") or f"{input_fields[0]['row']},{input_fields[0]['col']}"] = user
        else:
            vals = {"F001": user, "F002": password}
        self.send_fields(vals, snapshot_fields=fields, aid="ENTER")
        # Maneja handshake de Query: lee frames hasta que uno sea MAIN (tiene campos/literales)
        end = time.time() + timeout
        while time.time() < end:
            try:
                frame = self.capture(timeout=5)
            except Exception:
                break
            if not frame:
                continue
            # Query request: contiene 04 F3 00 05 D9 70; no es pantalla → responder Query Reply
            raw = bytes.fromhex(frame.get("raw_hex", "") or "")
            if b"\x04\xf3" in raw or b"\xd9\x70" in raw:
                # Responder Query Reply arbitrario (el host solo espera algo con EOR)
                self.send_query_reply()
                continue
            # Light off: opcode 0C en los últimos bytes del frame raw, sin campos ni literales
            if not frame.get("fields") and not frame.get("literals") and len(raw) >= 10 and (raw[9] == 0x0C or raw[9] == 0x0B or raw[9] == 0x10):
                continue
            # Pantalla real (MAIN): hay campos/literales/grid
            if frame.get("fields") or frame.get("literals") or any(l.strip() for l in frame.get("text_grid", [])):
                return frame
            # Si no hay nada, intenta más
        return self.capture(timeout=timeout)

    def send_query_reply(self) -> None:
        """Envía una Query Reply arbitraria (RFC 1205 §5.3)."""
        reply = (
            b"\x00\x00\x88\x00\x40\xd9\x70\x80\x12\xa0\x00\x00\x04\x00\x00\x03"
            b"\x04\xf3\x00\x05\xd9\x70\x80\x06\x00\x00"
        )
        self._send_raw(reply + bytes([IAC, 0xEF]))

    def execute_command(self, cmd: str, *, timeout: float = 15.0) -> dict:
        """Envía comando CL y captura pantalla resultante (usa campo MAIN si hay snapshot)."""
        # Si hay snapshot previo con campo OPT/CMD, usa send_fields para colocar texto en posición correcta
        if self._last_snapshot and self._last_snapshot.get("fields"):
            # Busca campo de comando (OPT, CMD, Selection) — usa el primer input field
            fields = self._last_snapshot["fields"]
            input_fields = [f for f in fields if f.get("usage") == "input"]
            if input_fields:
                # Usa el último input (normalmente command line) o el primero
                target = input_fields[-1] if len(input_fields) == 1 else input_fields[0]
                # Intenta mapear por nombre si existe
                key = target.get("name", "")
                if key:
                    self.send_fields({key: cmd}, snapshot_fields=fields, aid="ENTER")
                else:
                    self.send_fields({f"{target['row']},{target['col']}": cmd}, snapshot_fields=fields, aid="ENTER")
                return self.capture(timeout=timeout)
        # Fallback sin snapshot: envía texto + ENTER en GDS
        self.send_text(cmd)
        return self.capture(timeout=timeout)

    def press_key(self, key: str, *, timeout: float = 10.0) -> dict:
        self.send_aid(key)
        return self.capture(timeout=timeout)

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass


def capturar_display(con, *, timeout: float = 15.0) -> list[dict]:
    """Helper usado por captura.py: intenta TN5250, devuelve lista de snapshots.

    Si TN5250 no conecta, retorna lista vacía (el orquestador usará fallback SSH).
    """
    try:
        client = con.tn5250()
        client.negotiate()
        snap = client.capture(timeout=timeout)
        if snap and (snap.get("fields") or snap.get("literals") or snap.get("text_grid")):
            return [snap]
        return [snap] if snap else []
    except Exception as e:
        print(f"[display_5250] TN5250 no disponible: {e}")
        return []


def to_observable(snapshots: list[dict], *, name_prefix: str = "pantalla") -> list[dict]:
    out: list[dict] = []
    for i, snap in enumerate(snapshots):
        name = f"{name_prefix}{i+1}" if len(snapshots) > 1 else "pantalla1"
        out.append({"kind": "display", "name": name, "value": snap})
        # Emite también literales/grid/raw si existen (03-fidelidad)
        if snap.get("literals"):
            out.append({"kind": "display_literals", "name": "literals", "value": snap.get("literals")})
        if snap.get("text_grid"):
            out.append({"kind": "display_grid", "name": "grid", "value": snap.get("text_grid")})
        if snap.get("raw_hex"):
            out.append({"kind": "display_raw", "name": "raw", "value": snap.get("raw_hex")})
    return out
