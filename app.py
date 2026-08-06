"""Demo service under Groundtruth stewardship."""


PAGE_SIZE = 3


def search(query: str, page: int = 1) -> list[str]:
    page = max(1, page)
    start = (page - 1) * PAGE_SIZE
    return [f"{query}-{i}" for i in range(start, start + PAGE_SIZE)]


def export_report(rows: list[str]) -> str:
    return "\n".join(rows)
