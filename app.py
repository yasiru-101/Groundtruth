"""Demo service under Groundtruth stewardship."""


import csv
import io


def search(query: str, page: int = 1) -> list[str]:
    return [f"{query}-{i}" for i in range(3)]


def export_report(rows: list[str]) -> str:
    return "\n".join(rows)


def export_csv(rows: list[list[str]]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue()
