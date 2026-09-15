"""Colector de observables de display (pantalla 5250/DSPF).

Alínea el oráculo con el plan maestro §9.2/§18: la pantalla se compara por su
**estado semántico** (DisplaySnapshot), no por píxeles. Este colector documenta
el esquema y la normalización determinista (orden canónico de indicadores y
atributos) que usarán las verticales futuras que capturan pantallas reales de
IBM i (vertical 6 en 10-plan.md).

Para capturar pantallas reales se necesitará un cliente/emulación 5250 que
interactúe con la sesión de IBM i; ese transporte vive fuera de iNative y
pertenece a la integración del oráculo (Capa A/B del plan §18.7).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DisplaySnapshot:
    """Snapshot semántico de pantalla normalizable y comparable."""

    rows: int = 24
    cols: int = 80
    cursor: dict | None = None  # {"row": int, "col": int}
    fields: list[dict] = field(default_factory=list)
    indicators: dict[str, bool] = field(default_factory=dict)
    response_key: str | None = None

    def observables(self) -> dict:
        """Devuelve el snapshot en forma canónica y determinista."""
        fields = []
        for f in self.fields:
            f = dict(f)
            attrs = f.get("attributes", []) or []
            f["attributes"] = sorted(set(attrs))
            fields.append(f)
        return {
            "kind": "display",
            "name": self._nombre(),
            "value": {
                "screen": {"rows": self.rows, "cols": self.cols},
                "cursor": self.cursor,
                "fields": fields,
                "indicators": dict(sorted(self.indicators.items())),
                "response_key": self.response_key,
            },
        }

    def _nombre(self) -> str:
        # El nombre lo asigna el orquestador por caso/sesión; por defecto "screen".
        return "screen"


def normalizar_display(raw: dict) -> dict:
    """Normaliza un snapshot en bruto a la forma canónica de observables."""
    valid = ("rows", "cols", "cursor", "fields", "indicators", "response_key")
    kwargs = {k: raw[k] for k in valid if k in raw}
    return DisplaySnapshot(**kwargs).observables()


# Exposición de esquema para documentación/referencia (plan §9.2).
def esquema() -> dict:
    return {
        "screen": {"rows": int, "cols": int},
        "cursor": {"row": int, "col": int},
        "fields": [
            {"name": str, "row": int, "col": int, "length": int,
             "usage": str, "value": str, "attributes": [str]}
        ],
        "indicators": {"01": bool},
        "response_key": str,
    }
