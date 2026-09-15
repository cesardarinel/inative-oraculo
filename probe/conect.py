"""Conexión al IBM i mediante ODBC + SSH/PASE + SFTP + TN5250.

Combinación recomendada: ODBC para Db2/catálogo, SSH (PASE/QSH) para
compilar y capturar joblog/libl/objects, SFTP para IFS, TN5250 para display.
"""
from __future__ import annotations

import socket
import ssl
from pathlib import Path
from typing import TYPE_CHECKING

try:
    import paramiko  # type: ignore
except ImportError:
    paramiko = None  # type: ignore

from .config import Config

if TYPE_CHECKING:
    from .colectores.display_5250 import TN5250Client


class ConectarIBMi:
    """Abstracción de conexión: gestión de SSH, SFTP, ODBC y TN5250.

    El ODBC y TN5250 se inicializan bajo demanda. SSH es la base para
    compilar y ejecutar comandos batch.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._ssh: paramiko.SSHClient | None = None
        self._sftp: paramiko.SFTPClient | None = None
        self._tn: TN5250Client | None = None
        self._tn_sock: socket.socket | None = None

    # ---- SSH ----
    def ssh(self):  # -> paramiko.SSHClient
        if paramiko is None:
            raise RuntimeError("paramiko no instalado: pip install paramiko")
        if self._ssh is None:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=self.cfg.host,
                port=self.cfg.ssh_port,
                username=self.cfg.user,
                password=self.cfg.password,
                look_for_keys=False,
                allow_agent=False,
                timeout=30,
            )
            self._ssh = client
        return self._ssh

    def sshes(self, command: str, *, timeout: int = 120) -> tuple[int, str, str]:
        """Ejecuta un comando en PASE/QSH y devuelve (exit, stdout, stderr)."""
        client = self.ssh()
        full = f"system -s \"{self.cfg.current_library_cl}\" ; export QIBM_QSH_CMD_ESCAPE_MSG=Y ; {command}"
        _, out, err = client.exec_command(full, timeout=timeout, get_pty=True)
        return out.channel.recv_exit_status(), out.read().decode("utf-8", "replace"), err.read().decode("utf-8", "replace")

    def sshes_raw(self, command: str, *, timeout: int = 120) -> tuple[int, str, str]:
        """Ejecuta comando sin prefijo CHGCURLIB (para comandos que ya incluyen lib)."""
        client = self.ssh()
        _, out, err = client.exec_command(command, timeout=timeout, get_pty=True)
        return out.channel.recv_exit_status(), out.read().decode("utf-8", "replace"), err.read().decode("utf-8", "replace")

    def close(self) -> None:
        if self._tn is not None:
            try:
                self._tn.close()
            except Exception:
                pass
            self._tn = None
        if self._tn_sock is not None:
            try:
                self._tn_sock.close()
            except Exception:
                pass
            self._tn_sock = None
        if self._sftp is not None:
            try:
                self._sftp.close()
            except Exception:
                pass
            self._sftp = None
        if self._ssh:
            try:
                self._ssh.close()
            except Exception:
                pass
            self._ssh = None

    def __enter__(self) -> "ConectarIBMi":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- SFTP (intercambio de archivos vía SFTP) ----
    def sftp(self):  # -> paramiko.SFTPClient
        if self._sftp is None:
            self._sftp = self.ssh().open_sftp()
        return self._sftp

    def subir_ifs(self, local: str | Path, remoto: str) -> None:
        self.sftp().put(str(local), remoto)

    def bajar_ifs(self, remoto: str, local: str | Path) -> None:
        self.sftp().get(remoto, str(local))

    def escribir_ifs(self, remoto: str, contenido: str) -> None:
        # Asegura directorio padre existe vía mkdir -p por SSH. Se usa
        # sshes_raw porque el wrapper qsh (system -s "CHGCURLIB...") no tiene
        # mkdir y fallaba en silencio → luego el SFTP open daba ENOENT.
        parent = str(Path(remoto).parent)
        try:
            self.sshes_raw(f"mkdir -p {parent}", timeout=30)
        except Exception:
            pass
        with self.sftp().open(remoto, "w") as fh:
            fh.write(contenido)

    def leer_ifs(self, remoto: str) -> str:
        with self.sftp().open(remoto, "r") as fh:
            return fh.read().decode("utf-8", "replace")

    def existe_ifs(self, remoto: str) -> bool:
        try:
            self.sftp().stat(remoto)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    # ---- TN5250 ----
    def tn5250(self) -> "TN5250Client":
        """Devuelve cliente TN5250 conectado (lazy). Requiere host+user+pass."""
        if self._tn is not None:
            return self._tn
        # Import lazy para no exigir dependencia si no se usa display
        try:
            from .colectores.display_5250 import TN5250Client
        except ImportError as e:
            raise RuntimeError(
                "TN5250 no disponible: falta display_5250. "
                "Instala dependencias o usa transporte SSH batch"
            ) from e

        sock: socket.socket
        if self.cfg.tn5250_ssl:
            ctx = ssl.create_default_context()
            raw = socket.create_connection((self.cfg.host, self.cfg.tn5250_port), timeout=30)
            sock = ctx.wrap_socket(raw, server_hostname=self.cfg.host)
        else:
            sock = socket.create_connection((self.cfg.host, self.cfg.tn5250_port), timeout=30)
        sock.settimeout(30)
        self._tn_sock = sock
        self._tn = TN5250Client(sock, self.cfg, cols=80, rows=24)
        return self._tn

    def has_tn5250(self) -> bool:
        return self._tn is not None

    # ---- ODBC (bajo demanda) ----
    def odbc(self):
        import pyodbc

        dsn = self.cfg.odbc_dsn
        if dsn:
            conn_str = f"DSN={dsn};UID={self.cfg.odbc_uid};PWD={self.cfg.odbc_pwd}"
        else:
            conn_str = (
                f"DRIVER={{IBM i Access ODBC Driver}};"
                f"SYSTEM={self.cfg.host};UID={self.cfg.user};PWD={self.cfg.password};"
                f"CCSID={self.cfg.ccsid};Naming=0;"
            )
        return pyodbc.connect(conn_str)

    def try_odbc(self):
        """Intenta ODBC, devuelve None si no hay driver/conexión."""
        try:
            return self.odbc()
        except Exception:
            return None
