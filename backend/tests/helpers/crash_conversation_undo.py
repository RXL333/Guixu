from __future__ import annotations

import os
import sys
from pathlib import Path

from guixu.application import conversational_undo
from guixu.application.conversational_undo import ConversationalUndoService
from guixu.infrastructure.db.conversation_repository import ConversationRepository
from guixu.infrastructure.db.database import Database
from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
from guixu.infrastructure.filesystem.executor import FileOperationExecutor


class ExitAfterUndoneOperations:
    def __init__(self, delegate: SqliteOperationJournal, crash_after: int) -> None:
        self.delegate = delegate
        self.crash_after = crash_after
        self.undone = 0

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def transition(self, operation, state, payload=None) -> None:
        self.delegate.transition(operation, state, payload)
        if state == "UNDONE":
            self.undone += 1
            if self.undone == self.crash_after:
                os._exit(91)


def main() -> None:
    project_root = Path(sys.argv[1])
    database_path = Path(sys.argv[2])
    conversation_id, undo_plan_id, plan_hash = sys.argv[3:6]
    crash_after = int(sys.argv[6])
    database = Database(database_path, project_root / "contracts" / "database.sql")
    journal = SqliteOperationJournal(database)

    class CrashingExecutor:
        def __init__(self, inner_journal) -> None:
            self.executor = FileOperationExecutor(ExitAfterUndoneOperations(inner_journal, crash_after))

        def execute(self, plan, approved_hash, **kwargs):
            return self.executor.execute(plan, approved_hash, **kwargs)

    # The real service creates the durable UNDO execution round and sets the
    # plan to EXECUTING before this injected executor terminates the process.
    conversational_undo.FileOperationExecutor = CrashingExecutor
    service = ConversationalUndoService(database, journal)
    service.execute(conversation_id, undo_plan_id, plan_hash)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
