from app import export_csv, export_report, search


def test_search_returns_results() -> None:
    assert search("x") == ["x-0", "x-1", "x-2"]


def test_export_report_joins_rows() -> None:
    assert export_report(["a", "b"]) == "a\nb"


def test_export_csv_quotes_commas() -> None:
    assert export_csv([["a", "b,c"]]) == "a,'b,c'\r\n"
