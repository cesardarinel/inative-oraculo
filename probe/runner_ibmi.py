"""Runner IBM i: compila y ejecuta fixtures (RPGLE/DSPF/PF) en el sistema real."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .conect import ConectarIBMi

IFS_SRC = "/home/{user}/oracle/src"
IFS_OBJ = "/home/{user}/oracle/obj"

# Receptor persistente del spool de compilación (en la lib del usuario).
SPOOL_PF = "LST"
# Marcadores que el script emite para separar exits por paso.
M_CRT = "@CRT"


def nombre_objeto(nombre: str) -> str:
    """Sanitiza un nombre a objeto IBM i válido: A-Z0-9#$@_ máx 10."""
    import re
    up = re.sub(r"[^A-Z0-9#$@_]", "", nombre.upper())
    return up[:10] or "ORACULO"


@dataclass
class ListingResultado:
    ok: bool
    listing: str
    exit_code: int


class RunnerIBMi:
    def __init__(self, con: ConectarIBMi):
        self.con = con
        self.ifs_src = IFS_SRC.format(user=con.cfg.user)
        self.ifs_obj = IFS_OBJ.format(user=con.cfg.user)

    def preparar_dirs(self) -> None:
        self.con.sshes(f"mkdir -p {self.ifs_src} {self.ifs_obj}")

    # ---- Subida genérica ----
    def subir_fuente(self, fuente: str | Path, nombre: str, *, ext: str | None = None) -> str:
        """Copia fuente local al IFS. ext se infiere del archivo si no se da."""
        self.preparar_dirs()
        local = Path(fuente)
        if not local.exists():
            raise FileNotFoundError(f"Fuente no existe: {local}")
        suffix = ext or local.suffix.lstrip(".") or "rpgle"
        name = nombre.lower()
        ifs = f"{self.ifs_src}/{name}.{suffix.lower()}"
        self.con.escribir_ifs(ifs, local.read_text(encoding="utf-8"))
        return ifs

    def subir_texto(self, contenido: str, nombre: str, ext: str = "rpgle") -> str:
        """Sube contenido en memoria al IFS."""
        self.preparar_dirs()
        ifs = f"{self.ifs_src}/{nombre.lower()}.{ext.lower()}"
        self.con.escribir_ifs(ifs, contenido)
        return ifs

    # ---- Compilación ----
    def compilar_listing(self, cmd: str) -> ListingResultado:
        """Compila y captura el listing REAL (líneas RNF/RNX/RNS/CPF...).

        Descubrimiento PUB400 (26-ago-2026): `system -b "<cmd>"` imprime el
        listing completo por stdout (cabecera 5770WDS incluida); con `system`
        a secas solo llega el resumen CPF/RNS por stderr y el detalle queda
        atrapado en un sub-job batch cuyo spool es inaccesible por JOB(*).
        """
        _, out, err = self.con.sshes_raw(f'system -b "{cmd}"', timeout=180)
        listing = out + "\n" + err
        falla = ("Compilation failed" in listing or "RNS9310" in listing
                 or "CPF0006" in listing or "SQL9001" in listing
                 or "CPF7311" in listing or "CPF7302" in listing)
        return ListingResultado(ok=not falla, listing=listing,
                                exit_code=1 if falla else 0)

    def crtbndrpg(self, fuente_ifs: str, *, obj: str | None = None) -> ListingResultado:
        lib = self.con.cfg.lib
        objeto = obj or nombre_objeto(Path(fuente_ifs).stem)
        cmd = (
            f"CRTBNDRPG PGM({lib}/{objeto}) SRCSTMF('{fuente_ifs}') "
            f"OPTION(*EVENTF) TGTCCSID({self.con.cfg.ccsid})"
        )
        return self.compilar_listing(cmd)

    def crtbndcl(self, fuente_ifs: str, *, obj: str | None = None) -> ListingResultado:
        """Compila un CL ILE (CRTBNDCL) y captura su listing real."""
        lib = self.con.cfg.lib
        objeto = obj or nombre_objeto(Path(fuente_ifs).stem)
        cmd = f"CRTBNDCL PGM({lib}/{objeto}) SRCSTMF('{fuente_ifs}')"
        return self.compilar_listing(cmd)

    # ---- Fuente vía source physical file (comandos sin SRCSTMF) ------------

    def subir_miembro(self, contenido: str, mbr: str, *, ext: str = "dspf",
                      srcpf: str = "QDSPFSRC") -> tuple[str, str, str]:
        """Sube contenido a un miembro de source physical file (vía STMF).

        Necesario para comandos que NO soportan SRCSTMF (p.ej. CRTDSPF,
        CRTPF): CPYFRMSTMF convierte ASCII→EBCDIC al miembro QSYS.
        Devuelve (lib, srcpf, mbr-upper).
        """
        lib = self.con.cfg.lib
        self.preparar_dirs()
        rc, _, _ = self.con.sshes_raw(
            f"system 'CHKOBJ OBJ({lib}/{srcpf}) OBJTYPE(*FILE)'", timeout=30)
        if rc != 0:
            rc, out, err = self.con.sshes_raw(
                f"system 'CRTSRCPF FILE({lib}/{srcpf}) RCDLEN(112)'", timeout=60)
            if rc != 0:
                raise RuntimeError(f"CRTRSRCPF {srcpf}: {out}{err}")
        stmf = f"{self.ifs_src}/{mbr.lower()}.{ext.lower()}"
        self.con.escribir_ifs(stmf, contenido)
        tombr = (f"/qsys.lib/{lib.lower()}.lib/{srcpf.lower()}.file/"
                 f"{mbr.lower()}.mbr")
        cmd = f"CPYFRMSTMF FROMSTMF('{stmf}') TOMBR('{tombr}') MBROPT(*REPLACE)"
        rc, out, err = self.con.sshes_raw(f'system "{cmd}"', timeout=60)
        if rc != 0:
            raise RuntimeError(f"CPYFRMSTMF {mbr}: {out}{err}")
        return lib, srcpf, mbr.upper()

    def crtdspf_miembro(self, lib: str, srcpf: str, mbr: str, *,
                        obj: str | None = None) -> ListingResultado:
        """CRTDSPF desde source physical file (SRCSTMF no existe en CRTDSPF)."""
        cmd = (f"CRTDSPF FILE({lib}/{obj or mbr}) "
               f"SRCFILE({lib}/{srcpf}) SRCMBR({mbr})")
        return self.compilar_listing(cmd)

    def crtdspf(self, fuente_ifs: str, *, obj: str | None = None) -> ListingResultado:
        lib = self.con.cfg.lib
        objeto = obj or nombre_objeto(Path(fuente_ifs).stem)
        cmd = f"CRTDSPF FILE({lib}/{objeto}) SRCSTMF('{fuente_ifs}')"
        return self.compilar_listing(cmd)

    def crtpf(self, fuente_ifs: str, *, obj: str | None = None) -> ListingResultado:
        lib = self.con.cfg.lib
        objeto = obj or nombre_objeto(Path(fuente_ifs).stem)
        cmd = f"CRTPF FILE({lib}/{objeto}) SRCSTMF('{fuente_ifs}')"
        return self.compilar_listing(cmd)

    def crtsqlrpgle(self, fuente_ifs: str, *, obj: str | None = None,
                    rpgppopt: str = "*NONE") -> ListingResultado:
        lib = self.con.cfg.lib
        objeto = obj or nombre_objeto(Path(fuente_ifs).stem)
        # RPGPPOPT: *NONE (shipped) NO procesa /COPY,/IF → RNF7030/RNF7503
        # clásicos; *LVL2 procesa directivas antes del precompilador (doc 20 §2.2).
        cmd = (f"CRTSQLRPGI OBJ({lib}/{objeto}) SRCSTMF('{fuente_ifs}') "
               f"COMMIT(*NONE) RPGPPOPT({rpgppopt})")
        return self.compilar_listing(cmd)

    # ---- Comandos genéricos ----
    def ejecutar_cl(self, cmd: str, *, timeout: int = 60) -> ListingResultado:
        """Ejecuta comando CL arbitrario vía SSH (batch)."""
        exit_code, out, err = self.con.sshes(f"system -s \"{cmd}\"", timeout=timeout)
        return ListingResultado(ok=exit_code == 0, listing=out + "\n" + err, exit_code=exit_code)

    def call_pgm(self, pgm: str, *, lib: str | None = None, parms: str = "") -> ListingResultado:
        lib = lib or self.con.cfg.lib
        cmd = f"CALL PGM({lib}/{pgm})"
        if parms:
            cmd += f" PARM({parms})"
        return self.ejecutar_cl(cmd)

    # ---- Limpieza ----
    def limpiar_objeto(self, nombre: str, tipo: str = "*PGM", *, lib: str | None = None) -> None:
        lib = lib or self.con.cfg.lib
        try:
            self.ejecutar_cl(f"DLTOBJ OBJ({lib}/{nombre}) OBJTYPE({tipo})")
        except Exception:
            pass

    def limpiar_ifs(self, ifs_path: str) -> None:
        try:
            self.con.sshes(f"rm -f {ifs_path}", timeout=10)
        except Exception:
            pass
