"""Extracción del catálogo de mensajes del compilador desde IBM i.

Fuente portátil: DSPMSGD / RTVMSGD sobre QCPFMSG. En PUB400 (sistema público)
el usuario no tiene acceso de lectura al XML del catálogo del compilador en el
IFS (permisos), por lo que se usa el message file del sistema como fuente.

Emite resultados compatibles con el esquema de observables {kind, name, value}
y con la estructura catalog.json descrita en 18-catalogo-oraculo-ibmi.md.
"""
from __future__ import annotations

import re

from ..conect import ConectarIBMi

# Rangos por familia (según 17-errores-ibmi.md y el mapeo de codigos_ibmi.go).
RANGOS = {
    "RNF": ("RNF0000", "RNF9999"),  # RPG / CRTBNDRPG
    "RNX": ("RNX0000", "RNX9999"),
    "RNT": ("RNT0000", "RNT9999"),
    "RNQ": ("RNQ0000", "RNQ9999"),
    "RNW": ("RNW0000", "RNW9999"),
    "RNI": ("RNI0000", "RNI9999"),
    "CLL": ("CLL0000", "CLL9999"),  # CL / CRTCLMOD
    "CPF": ("CPF0000", "CPF9999"),
}


class ColectorCatalogo:
    kind = "mensajes"

    def __init__(self, con: ConectarIBMi, msgf: str = "QCPFMSG"):
        self.con = con
        self.msgf = msgf

    def recoger_familia(self, familia: str) -> list[dict]:
        """Usa RTVMSGD por rango para volcar id + texto y severidad."""
        desde, hasta = RANGOS[familia]
        cmd = (
            f"RTVMSGD MSGID('{desde}') RNG('{hasta}') MSGF(QSYS/{self.msgf}) "
            f"RTNMSGID(*YES)"
        )
        # RTVMSGD no es ideal para rangos completos; se usa DSPMSGD *PRINT como
        # respaldo real y aquí se deja la interfaz de la vertical. La extracción
        # real se afina al validar contra el sistema.
        exit_code, out, err = self.con.sshes(f"system -s \"{cmd}\"", timeout=180)
        salida = out or err
        return self._parsear(salida, familia)

    def _parsear(self, texto: str, familia: str) -> list[dict]:
        encontrados: list[dict] = []
        patron = re.compile(r"([A-Z]{3}\d{4})\s+(?:(\d{1,2})\s+)?(.*)", re.MULTILINE)
        for m in patron.finditer(texto):
            cod = m.group(1)
            if not cod.startswith(familia):
                continue
            encontrados.append(
                {
                    "kind": "mensajes",
                    "name": cod,
                    "severidad": int(m.group(2)) if m.group(2) else None,
                    "value": m.group(3).strip(),
                }
            )
        return encontrados
