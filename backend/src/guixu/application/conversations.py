from __future__ import annotations

from typing import Any

from guixu.infrastructure.db.conversation_repository import ConversationRepository


class ConversationService:
    """Application facade for durable Conversation state.

    The service deliberately has no model gateway or task coordinator dependency.
    PHASE D only persists state and references; later phases may compose these
    methods with an orchestrator.
    """

    def __init__(self, repository: ConversationRepository) -> None:
        self.repository = repository

    def create_conversation(self, *, title: str = "未命名整理", model_profile_id: str | None = None,
                            scope: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None,
                            context: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.repository.create(title, model_profile_id=model_profile_id, scope=scope, metadata=metadata, context=context)

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        return self.repository.get(conversation_id)

    def list_conversations(self, view: str = "active") -> list[dict[str, Any]]:
        return self.repository.list(view)

    def rename_conversation(self, conversation_id: str, title: str) -> dict[str, Any]:
        return self.repository.rename(conversation_id, title)

    def set_model_profile(self, conversation_id: str, model_profile_id: str) -> dict[str, Any]:
        return self.repository.set_model_profile(conversation_id, model_profile_id)

    def archive_conversation(self, conversation_id: str) -> dict[str, Any]:
        return self.repository.archive(conversation_id)

    def activate_conversation(self, conversation_id: str) -> dict[str, Any]:
        return self.repository.activate(conversation_id)

    def soft_delete_conversation(self, conversation_id: str) -> dict[str, Any]:
        return self.repository.soft_delete(conversation_id)

    def restore_conversation(self, conversation_id: str) -> dict[str, Any]:
        return self.repository.restore(conversation_id)

    def append_message(self, conversation_id: str, role: str, content: str, **kwargs: Any) -> dict[str, Any]:
        return self.repository.append_message(conversation_id, role, content, **kwargs)

    def list_messages(self, conversation_id: str, *, include_redacted: bool = False) -> list[dict[str, Any]]:
        self.repository.get(conversation_id)
        return self.repository.list_messages(conversation_id, include_redacted=include_redacted)

    def get_context(self, conversation_id: str) -> dict[str, Any]:
        return self.repository.get_context(conversation_id)

    def update_context(self, conversation_id: str, expected_revision: int, changes: dict[str, Any]) -> dict[str, Any]:
        return self.repository.update_context(conversation_id, expected_revision, changes)

    def create_plan_version(self, conversation_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.repository.create_plan_version(conversation_id, **kwargs)

    def get_plan_version(self, plan_version_id: str) -> dict[str, Any]:
        return self.repository.get_plan_version(plan_version_id)

    def list_plan_versions(self, conversation_id: str) -> list[dict[str, Any]]:
        self.repository.get(conversation_id)
        return self.repository.list_plan_versions(conversation_id)

    def get_current_plan_version(self, conversation_id: str) -> dict[str, Any]:
        self.repository.get(conversation_id)
        return self.repository.get_current_plan_version(conversation_id)

    def approve_plan_version(self, conversation_id: str, plan_version_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.repository.approve_plan_version(conversation_id, plan_version_id, **kwargs)

    def create_execution_round(self, conversation_id: str, plan_version_id: str, execution_plan_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.repository.create_execution_round(conversation_id, plan_version_id, execution_plan_id, **kwargs)

    def list_execution_rounds(self, conversation_id: str) -> list[dict[str, Any]]:
        self.repository.get(conversation_id)
        return self.repository.list_execution_rounds(conversation_id)

    def attach_file_to_conversation(self, conversation_id: str, file_id: str) -> dict[str, Any]:
        return self.repository.attach_file(conversation_id, file_id)

    def list_conversation_files(self, conversation_id: str, *, include_removed: bool = False) -> list[dict[str, Any]]:
        self.repository.get(conversation_id)
        return self.repository.list_conversation_files(conversation_id, include_removed=include_removed)

    def verify_conversation_file(self, conversation_id: str, file_id: str) -> dict[str, Any]:
        return self.repository.verify_file(conversation_id, file_id)

    def link_task(self, conversation_id: str, task_id: str, plan_version_id: str | None = None) -> dict[str, Any]:
        return self.repository.link_task(conversation_id, task_id, plan_version_id)
