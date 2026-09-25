from __future__ import annotations

import os
import sys
from pathlib import Path

from guixu.infrastructure.db.database import Database
from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
from guixu.infrastructure.filesystem.executor import FileOperationExecutor


class ExitAtCheckpoint:
    def __init__(self, delegate: SqliteOperationJournal, checkpoint: str, occurrence: int = 1) -> None:
        self.delegate = delegate
        self.checkpoint = checkpoint
        self.occurrence = occurrence
        self.matches = 0

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def transition(self, operation, state, payload=None):
        self.delegate.transition(operation, state, payload)
        if state == self.checkpoint:
            self.matches += 1
            if self.matches == self.occurrence:
                os._exit(91)


def main() -> None:
    project_root = Path(sys.argv[1])
    database_path = Path(sys.argv[2])
    plan_id = sys.argv[3]
    checkpoint = sys.argv[4]
    occurrence = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    database = Database(database_path, project_root / "contracts" / "database.sql")
    journal = SqliteOperationJournal(database)
    plan = journal.load_plan(plan_id)
    FileOperationExecutor(ExitAtCheckpoint(journal, checkpoint, occurrence), chunk_size=4096).execute(plan, plan.plan_hash)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
