"""Entry point: python -m groundtruth.api"""

from __future__ import annotations

import uvicorn

from groundtruth.api.settings import ApiSettings


def main() -> None:
    settings = ApiSettings()
    uvicorn.run(
        "groundtruth.api.app:create_app",
        host=settings.api_host,
        port=settings.api_port,
        factory=True,
        reload=False,
    )


if __name__ == "__main__":
    main()
