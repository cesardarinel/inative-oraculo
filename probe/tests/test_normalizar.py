"""Tests probe/normalizar.py — no requieren IBM i."""
from probe.normalizar import (
    normalizar_display,
    normalizar_joblog,
    normalizar_libl,
    normalizar_objects,
    normalizar_db,
    normalizar_observables,
    normalizar_texto,
)


def test_normalizar_texto_colapsa():
    assert normalizar_texto("  hola   mundo  ") == "hola mundo"
    assert normalizar_texto("CPF2103\t Biblioteca\n creada") == "CPF2103 Biblioteca creada"


def test_normalizar_display_ordena_y_rstrip():
    snap = {
        "screen": {"rows": 24, "cols": 80},
        "cursor": {"row": 6, "col": 21},
        "fields": [
            {"name": "B", "row": 10, "col": 5, "length": 5, "usage": "input", "value": "zzz  ", "attributes": ["mdt"]},
            {"name": "A", "row": 5, "col": 20, "length": 10, "usage": "input", "value": "  hello  ", "attributes": ["protected", "mdt", "protected"]},
        ],
        "indicators": {"03": True, "01": False},
        "response_key": "ENTER",
    }
    out = normalizar_display(snap)
    # Orden por (row,col)
    assert out["fields"][0]["name"] == "A"
    assert out["fields"][1]["name"] == "B"
    # rstrip solo trailing
    assert out["fields"][0]["value"] == "  hello"
    # attrs sorted + dedup
    assert out["fields"][0]["attributes"] == ["mdt", "protected"]
    # indicators sorted keys
    assert list(out["indicators"].keys()) == ["01", "03"]


def test_normalizar_display_preserva_row_col():
    snap = {"screen": {"rows": 24, "cols": 80}, "fields": [{"name": "X", "row": 5, "col": 20, "length": 10, "usage": "output", "value": "DSPLIBL", "attributes": []}], "indicators": {}}
    out = normalizar_display(snap)
    assert out["fields"][0]["row"] == 5
    assert out["fields"][0]["col"] == 20
    assert out["fields"][0]["length"] == 10


def test_normalizar_joblog_upper_y_colapso():
    jl = [{"id": "cpf1124", "sev": "0", "text": "  Job   started  "}, {"id": "RNQ1218", "sev": 40, "text": "error"}]
    out = normalizar_joblog(jl)
    assert out[0]["id"] == "CPF1124"
    assert out[0]["text"] == "Job started"
    assert out[1]["sev"] == 40


def test_normalizar_joblog_ignore():
    jl = [{"id": "CPF1124", "sev": 0, "text": "Job started"}, {"id": "CPF2103", "sev": 0, "text": "ignore me"}]
    out = normalizar_joblog(jl, ignore=["CPF2103"])
    assert len(out) == 1
    assert out[0]["id"] == "CPF1124"


def test_normalizar_libl_dedup_upper():
    assert normalizar_libl(["qgpl", "QTEMP", "qgpl", "MYLIB"]) == ["QGPL", "QTEMP", "MYLIB"]


def test_normalizar_libl_ignore():
    assert normalizar_libl(["QGPL", "QTEMP", "MYLIB"], ignore=["qtemp"]) == ["QGPL", "MYLIB"]


def test_normalizar_objects_sorted():
    out = normalizar_objects(["MYLIB/B *PGM", "MYLIB/A *FILE", "MYLIB/B *PGM"])
    assert out == ["MYLIB/A *FILE", "MYLIB/B *PGM"]


def test_normalizar_db_lower_keys():
    rows = [{"KEY": 1, "NAME": "Juan"}, {"KEY": 2, "NAME": "Ana"}]
    out = normalizar_db(rows)
    assert "key" in out[0]
    assert "name" in out[0]


def test_normalizar_observables_dispatcher():
    obs = [
        {"kind": "display", "name": "pantalla1", "value": {"screen": {"rows": 24, "cols": 80}, "fields": [], "indicators": {}}},
        {"kind": "return", "value": "0"},
        {"kind": "libl", "value": ["QGPL", "QTEMP"]},
    ]
    out = normalizar_observables(obs)
    assert out[1]["value"] == 0  # return casteado a int
    assert out[2]["value"] == ["QGPL", "QTEMP"]
