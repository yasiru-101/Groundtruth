"""Demo service under Groundtruth stewardship."""


def search(query: str) -> list[str]:
    return [f"{query}-{i}" for i in range(3)]


def export_report(rows: list[str]) -> str:
    return "\n".join(rows)
