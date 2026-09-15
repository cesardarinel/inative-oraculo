"""Colector de mensajes desde un listing de compilación capturado de IBM i.

Extrae los códigos del compilador en el formato RenderIBM de iNative:
    *<código> <línea> <col> <texto>
y los normaliza a {kind, name, severidad, valor, linea, col}.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Formato REAL del listing CRTBNDRPG (capturas PUB400 7.5, 26-ago-2026):
#
#   Diagnóstico:  *RNF7030 30      7 000007  The name or indicator ...
#                 *RNF3316 30 a      000005  The item has already been defined
#                 (*COD sev POS SEQ texto)
#     - POS es posición dentro de la línea: dígito o LETRA (a,b,c…).
#     - SEQ es la secuencia de fuente = LÍNEA real (preferida para linea).
#   Resumen final (descartar):   *RNF7031 00      1 The name ... (conteo, no SEQ)
#   Referencia cruzada (ignorar):*RNF7031 V    A(3)   4D
_PATRON_LINEA = re.compile(
    r"^\s*\*?(?P<cod>[A-Z]{3}\d{4})\s+(?P<sev>\d{1,2})\s+"
    r"(?P<pos>[0-9A-Za-z]{1,6})\s+(?P<seq>\d{1,6})\s+(?P<texto>\S.*)$"
)

# Formato de diagnósticos DDS (listings CRTDSPF/CRTPF, captura PUB400 2026):
#   * CPD5238      30        1      Message . . . . :   No valid record found...
#   (*COD  sev  línea-fuente  "Message . . . . :"  texto)
_PATRON_DDS = re.compile(
    r"^\*\s*(?P<cod>[A-Z]{3}\d{4})\s+(?P<sev>\d{1,2})\s+(?P<linea>\d{1,6})\s+"
    r"Message\s*(?:\.\s*)+:\s*(?P<texto>.*)$"
)


def _a_int(valor: str) -> int | None:
    try:
        return int(valor)
    except ValueError:
        return None


@dataclass(frozen=True)
class Mensaje:
    codigo: str
    severidad: int | None
    linea: int | None
    col: int | None
    texto: str

    def observables(self) -> dict:
        base = {
            "kind": "mensajes",
            "name": self.codigo,
            "value": self.texto.strip(),
        }
        if self.severidad is not None:
            base["severidad"] = self.severidad
        if self.linea is not None:
            base["linea"] = self.linea
        if self.col is not None:
            base["col"] = self.col
        return base


def parsear_listing(listing: str) -> list[Mensaje]:
    mensajes: list[Mensaje] = []
    vistos: set[tuple] = set()
    for raw in listing.splitlines():
        m = _PATRON_LINEA.match(raw)
        if not m:
            continue
        # Línea real = SEQ de fuente (la POS puede ser letra a/b/c…).
        linea = _a_int(m.group("seq"))
        if linea is None:
            linea = _a_int(m.group("pos"))
        clave = (m.group("cod"), m.group("seq"), m.group("texto"))
        if clave in vistos:
            continue  # el resumen final repite diagnósticos sin SEQ
        vistos.add(clave)
        mensajes.append(
            Mensaje(
                codigo=m.group("cod"),
                severidad=int(m.group("sev")) if m.group("sev") else None,
                linea=linea,
                col=None,  # el listing RPG no trae columna; trae POS/SEQ
                texto=m.group("texto"),
            )
        )
    return mensajes
