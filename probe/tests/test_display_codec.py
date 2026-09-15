"""Tests probe/colectores/display_codec.py y display_5250.py — sin red."""
from probe.colectores.display_codec import (
    decode_5250_stream,
    ebcdic_to_str,
    addr_to_rc,
    rc_to_addr,
    build_input_data,
)


def test_addr_roundtrip():
    for cols in (80, 132):
        for row, col in [(1, 1), (5, 20), (24, 80), (1, 80)]:
            addr = rc_to_addr(row, col, cols)
            r2, c2 = addr_to_rc(addr, cols)
            assert (r2, c2) == (row, col)


def test_ebcdic_roundtrip():
    # CCSID 37
    s = "HELLO 123"
    enc = s.encode("cp037")
    assert ebcdic_to_str(enc, 37) == s


def test_decode_empty_stream():
    snap = decode_5250_stream(b"", rows=24, cols=80)
    assert snap["screen"] == {"rows": 24, "cols": 80}
    assert snap["fields"] == []


def test_decode_sf_y_texto():
    # WTD(00 11 00) + SF(1D 10) + "HI" en EBCDIC
    hi_ebcdic = "HI".encode("cp037")
    raw = bytes([0x00, 0x11, 0x00, 0x1D, 0x10]) + hi_ebcdic
    snap = decode_5250_stream(raw, rows=24, cols=80, ccsid=37)
    assert len(snap["fields"]) >= 1
    # El field debe contener HI
    vals = [f["value"] for f in snap["fields"]]
    assert any("HI" in v for v in vals)


def test_decode_cursor_ic():
    # WTD + IC(13) addr(5,20) -> row 5 col 20
    raw = bytes([0x00, 0x11, 0x00, 0x13, 0x40 | ((rc_to_addr(5, 20, 80) >> 6) & 0x3F), 0x40 | (rc_to_addr(5, 20, 80) & 0x3F)])
    snap = decode_5250_stream(raw, rows=24, cols=80)
    assert snap["cursor"] == {"row": 5, "col": 20}


def test_build_input_data():
    fields = [
        {"name": "CUSTOMER_ID", "row": 5, "col": 20, "length": 10, "usage": "input"},
        {"name": "OTRO", "row": 6, "col": 10, "length": 5, "usage": "output"},
    ]
    payload = build_input_data(fields, {"CUSTOMER_ID": "1001"}, ccsid=37)
    # Debe contener 1001 en EBCDIC
    assert "1001".encode("cp037") in payload
    # OTRO no debe estar porque es output y no está en values
    assert b"OTRO" not in payload
