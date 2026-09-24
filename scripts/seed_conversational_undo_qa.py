"""Create isolated real-file data for PHASE L browser QA."""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "artifacts" / "runtime-undo-ui"
TEST = ROOT / "backend" / "tests" / "integration" / "test_conversational_undo.py"


def main() -> None:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)
    spec = importlib.util.spec_from_file_location("guixu_undo_qa_fixture", TEST)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    database, _, _, _, service, conversation_id, _, _, _, _ = module._environment(ROOT, TARGET, 5)
    service.request(conversation_id, user_message="撤销刚才那次调整。")
    database.close()
    print(conversation_id)


if __name__ == "__main__":
    main()
