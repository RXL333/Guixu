from __future__ import annotations

import os
import sys
from pathlib import Path

from guixu.infrastructure.db.database import Database
from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
from guixu.infrastructure.filesystem.executor import FileOperationExecutor


class ExitAtCheckpoint:
    def __init__(self, delegate: SqliteOperationJournal, checkpoint: str) -> None:
        self.delegate = delegate
        self.checkpoint = checkpoint

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def transition(self, operation, state, payload=None):
        self.delegate.transition(operation, state, payload)
        if state == self.checkpoint:
            os._exit(91)


def main() -> None:
    project_root = Path(sys.argv[1])
    database_path = Path(sys.argv[2])
    plan_id = sys.argv[3]
    checkpoint = sys.argv[4]
    database = Database(database_path, project_root / "contracts" / "database.sql")
    journal = SqliteOperationJournal(database)
    plan = journal.load_plan(plan_id)
    FileOperationExecutor(ExitAtCheckpoint(journal, checkpoint), chunk_size=4096).execute(plan, plan.plan_hash)
    raise SystemExit(0)


if __name__ == "__main__":
    main()

