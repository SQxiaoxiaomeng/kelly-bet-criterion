import pytest

from app.providers.tushare_provider import _from_tushare_symbol, _to_tushare_symbol


def test_converts_internal_symbols_to_tushare_symbols() -> None:
    assert _to_tushare_symbol("SSE:600000") == "600000.SH"
    assert _to_tushare_symbol("SZSE:000001") == "000001.SZ"
    assert _from_tushare_symbol("600000.SH") == "SSE:600000"


def test_rejects_unsupported_exchange() -> None:
    with pytest.raises(ValueError, match="UNSUPPORTED_EXCHANGE"):
        _to_tushare_symbol("BSE:430047")
