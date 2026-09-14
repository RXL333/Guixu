from __future__ import annotations

import json
from pathlib import Path

from guixu.api.app import create_app


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "artifacts" / "test-workspaces" / "openapi-export"
    app = create_app(project_root=root, data_dir=data_dir, session_token="contract-export", allow_typed_grants=True)
    try:
        destination = root / "contracts" / "openapi-runtime.json"
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", "utf-8")
        temporary.replace(destination)
    finally:
        app.state.database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
