"""Carga de configuración del oráculo desde oracle.env / variables de entorno.

Las credenciales NUNCA se versionan; viven en oracle.env (ignorado por git).
"""
import os
from dataclasses import dataclass
from pathlib import Path

import dotenv

DEFAULT_ENV_FILE = Path(__file__).resolve().parent.parent / "oracle.env"


@dataclass(frozen=True)
class Config:
    host: str
    port: int = 22
    release: str = "7.5"
    user: str = ""
    password: str = ""
    lib: str = ""
    ccsid: int = 37
    tn5250_port: int = 23
    tn5250_ssl: bool = False
    odbc_dsn: str = ""
    odbc_uid: str = ""
    odbc_pwd: str = ""

    @property
    def ssh_port(self) -> int:
        return self.port

    @property
    def current_library_cl(self) -> str:
        # Comando CL para posicionarse en la biblioteca de la aplicación.
        return f"CHGCURLIB CURLIB({self.lib})" if self.lib else "CHGCURLIB *CRTDFT"

    def validate(self) -> list[str]:
        """Valida configuración mínima y devuelve lista de errores."""
        errs: list[str] = []
        if not self.host:
            errs.append("ORACLE_IBM_HOST vacío")
        if not self.user:
            errs.append("ORACLE_IBM_USER vacío")
        if self.ccsid not in (37, 273, 284, 500, 1140, 1141, 1147, 1148):
            errs.append(f"CCSID {self.ccsid} no soportado (usa 37, 273, 1140, etc.)")
        return errs


def load(env_file: Path | None = None) -> Config:
    env_file = env_file or DEFAULT_ENV_FILE
    if env_file.exists():
        dotenv.load_dotenv(env_file)
    def _bool(v: str, default: bool = False) -> bool:
        if v == "":
            return default
        return v.strip().lower() in ("1", "true", "yes", "on")

    return Config(
        host=os.getenv("ORACLE_IBM_HOST", ""),
        port=int(os.getenv("ORACLE_IBM_PORT", "22")),
        release=os.getenv("ORACLE_IBM_RELEASE", "7.5"),
        user=os.getenv("ORACLE_IBM_USER", ""),
        password=os.getenv("ORACLE_IBM_PASSWORD", "") or os.getenv("ORACLE_IBM_PASS", ""),
        lib=os.getenv("ORACLE_IBM_LIB", ""),
        ccsid=int(os.getenv("ORACLE_IBM_CCSID", "37")),
        tn5250_port=int(os.getenv("ORACLE_IBM_TN5250_PORT", "23")),
        tn5250_ssl=_bool(os.getenv("ORACLE_IBM_TN5250_SSL", "false")),
        odbc_dsn=os.getenv("ORACLE_IBM_ODBC_DSN", ""),
        odbc_uid=os.getenv("ORACLE_IBM_ODBC_UID", ""),
        odbc_pwd=os.getenv("ORACLE_IBM_ODBC_PWD", ""),
    )
