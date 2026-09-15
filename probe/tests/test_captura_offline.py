"""Test offline de captura.py sin IBM i — usa mocks de ConectarIBMi."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from probe.captura import capturar_fixture


def _fake_conectar(fixtures_dir: Path):
    """Mock de ConectarIBMi que no toca red."""
    mock = MagicMock()
    mock.cfg.host = "mock.host"
    mock.cfg.release = "7.5"
    mock.cfg.ccsid = 37
    mock.cfg.lib = "C3S411"
    mock.cfg.user = "C3S41"
    # SSH mocks
    mock.sshes.return_value = (0, "", "")
    mock.try_odbc.return_value = None
    mock.existe_ifs.return_value = False
    # TN5250 mock
    tn = MagicMock()
    tn.negotiate.return_value = None
    tn.capture.return_value = {
        "screen": {"rows": 24, "cols": 80},
        "cursor": {"row": 6, "col": 21},
        "fields": [{"name": "CUSTOMER_ID", "row": 5, "col": 20, "length": 10, "usage": "input", "value": "1001", "attributes": []}],
        "indicators": {"01": False},
        "response_key": "ENTER",
    }
    tn.press_key.return_value = tn.capture.return_value
    tn.execute_command.return_value = tn.capture.return_value
    mock.tn5250.return_value = tn
    mock.close.return_value = None
    return mock


def test_captura_fixture_offline_hola(tmp_path: Path = None):
    import tempfile
    fixture = Path(__file__).resolve().parent.parent.parent / "conformance/dspf/HELLO-5250-001.json"
    if not fixture.exists():
        fixture = Path("/mnt/D/proyectos/Personales/iNative-oraculo/conformance/dspf/HELLO-5250-001.json")
    assert fixture.exists(), f"fixture no existe: {fixture}"

    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td) / "esperado"
        fake_con = _fake_conectar(Path(td))

        # Patch ConectarIBMi, load config y RunnerIBMi para no tocar IFS real
        with patch("probe.captura.ConectarIBMi", return_value=fake_con), \
             patch("probe.captura.load") as mock_load, \
             patch("probe.captura.RunnerIBMi") as mock_runner_cls, \
             patch("probe.colectores.joblog.capturar_joblog", return_value=[{"id": "CPF1124", "sev": 0, "text": "Job started"}]), \
             patch("probe.colectores.libl.capturar_libl", return_value=["C3S411", "QTEMP", "QGPL"]), \
             patch("probe.colectores.objects.capturar_objects", return_value=["C3S411/HOLA *PGM"]):

            from probe.config import Config
            mock_load.return_value = Config(host="mock.host", release="7.5", user="C3S41", password="x", lib="C3S411", ccsid=37)

            mock_runner = MagicMock()
            mock_runner.subir_fuente.return_value = "/tmp/fake.rpgle"
            # crtbndrpg no se llama si source no existe local, pero lo mockeamos igual
            from probe.runner_ibmi import ListingResultado
            mock_runner.crtbndrpg.return_value = ListingResultado(ok=True, listing="", exit_code=0)
            mock_runner_cls.return_value = mock_runner

            dest = capturar_fixture(fixture_path=fixture, out_dir=out_dir, env_file=None, use_tn5250=True)

            assert dest.exists()
            data = json.loads(dest.read_text(encoding="utf-8"))
            assert data["contrato_version"] == 1
            assert data["fixture"] == "HELLO-5250-001" or "HOLA" in data["fixture"]
            assert "observables" in data
            kinds = [o["kind"] for o in data["observables"]]
            assert "display" in kinds
            assert "joblog" in kinds
            assert "return" in kinds
            assert "libl" in kinds
            # display debe tener row/col
            disp = [o for o in data["observables"] if o["kind"] == "display"][0]
            assert disp["value"]["fields"][0]["row"] == 5
            assert disp["value"]["fields"][0]["col"] == 20

            print(f"OFFLINE captura OK -> {dest} kinds={kinds}")
