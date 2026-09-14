from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from guixu.api.app import create_app
from guixu.main import find_project_root


def main() -> None:
    root = find_project_root()
    token = os.environ.get("GUIXU_DEV_SESSION", "guixu-dev-session")
    port = int(os.environ.get("GUIXU_DEV_PORT", "8765"))
    app = create_app(
        project_root=root,
        data_dir=Path(os.environ.get("GUIXU_DATA_DIR", root / "artifacts" / "runtime")),
        session_token=token,
        allowed_origins={"http://127.0.0.1:5173", f"http://127.0.0.1:{port}"},
        allow_typed_grants=os.environ.get("GUIXU_DEV_GRANTS") == "1",
    )
    uvicorn.run(app, host="127.0.0.1", port=port, workers=1, access_log=False)


if __name__ == "__main__":
    main()
