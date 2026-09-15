"""Tests parsers de colectores batch — sin IBM i, solo parsing."""
from probe.colectores.joblog import parse_joblog_text
from probe.colectores.libl import _parse_dsplibl_output
from probe.colectores.objects import capturar_objects  # solo para import
from probe.colectores.display_5250 import DisplaySnapshot


def test_parse_joblog_basic():
    text = """
    CPF1124  00  Job 123456/C3S41/QPADEV0001 started
    CPF2103  00  Library C3S411 created
    RNQ1218  40  Variable not declared
    """
    out = parse_joblog_text(text)
    assert any(o["id"] == "CPF1124" for o in out)
    assert any(o["id"] == "RNQ1218" and o["sev"] == 40 for o in out)


def test_parse_joblog_continuacion():
    text = "CPF9897  00  Mensaje largo\n         continuación de mensaje"
    out = parse_joblog_text(text)
    assert len(out) == 1
    assert "continuación" in out[0]["text"]


def test_parse_joblog_filtra_cabeceras():
    text = "JOB LOG  QSYS  PAGE 001\n CPF1124 Job started"
    out = parse_joblog_text(text)
    assert len(out) == 1
    assert out[0]["id"] == "CPF1124"


def test_parse_dsplibl():
    text = """
    Library List
    C3S411  QTEMP  QGPL  QSYS
    """
    out = _parse_dsplibl_output(text)
    assert "C3S411" in out
    assert "QTEMP" in out
    # Orden preservado sin duplicados
    assert out.index("C3S411") < out.index("QTEMP")


def test_display_snapshot_observables():
    snap = DisplaySnapshot(rows=24, cols=80, cursor={"row": 6, "col": 21},
                           fields=[{"name": "CUSTOMER_ID", "row": 5, "col": 20, "length": 10, "usage": "input", "value": "1001", "attributes": ["mdt"]}],
                           indicators={"01": False}, response_key="ENTER")
    obs = snap.observables(name="pantalla1")
    assert obs["kind"] == "display"
    assert obs["value"]["fields"][0]["name"] == "CUSTOMER_ID"
    assert obs["value"]["fields"][0]["attributes"] == ["mdt"]
