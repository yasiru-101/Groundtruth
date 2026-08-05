"""Demo service under Groundtruth stewardship."""


def search(query: str, page: int = 1) -> list[str]:
    start = max(1, page) * 3
    return [f"{query}-{i}" for i in range(start, start + 3)]


def export_report(rows: list[str]) -> str:
    return "\n".join(rows)
