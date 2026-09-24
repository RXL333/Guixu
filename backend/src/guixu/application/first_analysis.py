from __future__ import annotations

"""The bounded first-organization pipeline for a new Conversation.

This is intentionally narrower than the future Agent runtime.  It composes the
existing safe Task/Planner/Classifier/Journal services and never executes a
filesystem operation.
"""

from pathlib import Path
from typing import Any, Callable

from guixu.application.ai_file_classifier import AIFileClassifier
from guixu.application.ai_taxonomy_planner import AITaxonomyPlanner
from guixu.application.models import ModelError, ModelProfileService
from guixu.application.operations import OperationService
from guixu.application.privacy import PrivacyService
from guixu.application.tasks import TaskService
from guixu.application.taxonomies import TaxonomyService
from guixu.domain.privacy import PrivacyError, scope_hash
from guixu.domain.settings import TaskSettings, load_default_settings
from guixu.infrastructure.db.conversation_repository import ConversationRepository
from guixu.infrastructure.db.database import Database
from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.filesystem.grants import GrantError, SourceRegistry


class FirstAnalysisError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


class FirstOrganizationAnalysisService:
    """Run one real, preview-only organization analysis for a new Conversation."""

    def __init__(
        self,
        *,
        project_root: Path,
        database: Database,
        conversations: ConversationRepository,
        repository: TaskRepository,
        tasks: TaskService,
        registry: SourceRegistry,
        models: ModelProfileService,
        privacy: PrivacyService,
        planner: AITaxonomyPlanner,
        classifier: AIFileClassifier,
        taxonomies: TaxonomyService,
        operations: OperationService,
        journal: SqliteOperationJournal,
    ) -> None:
        self.project_root = project_root
        self.database = database
        self.conversations = conversations
        self.repository = repository
        self.tasks = tasks
        self.registry = registry
        self.models = models
        self.privacy = privacy
        self.planner = planner
        self.classifier = classifier
        self.taxonomies = taxonomies
        self.operations = operations
        self.journal = journal

    def run(
        self,
        conversation_id: str,
        *,
        user_message: str,
        message_id: str,
        acknowledge_privacy: bool,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        progress_events: list[dict[str, Any]] = []

        def emit(event: dict[str, Any]) -> None:
            progress_events.append(event)
            if progress:
                progress(event)

        conversation = self.conversations.get(conversation_id)
        context = self.conversations.get_context(conversation_id)
        if context.get("current_plan_version_id") or context.get("current_execution_round_id"):
            raise FirstAnalysisError("FIRST_ANALYSIS_ALREADY_COMPLETED", "当前会话已经有方案或执行记录，请使用后续调整流程。")
        scopes = [item for item in conversation.get("scopes", []) if item.get("revoked_at") is None]
        if not scopes:
            raise FirstAnalysisError("FIRST_ANALYSIS_SCOPE_REQUIRED", "请先选择并授权一个文件夹。")
        model_profile_id = conversation.get("model_profile_id") or context.get("model_profile_id")
        if not model_profile_id:
            raise FirstAnalysisError("MODEL_PROFILE_REQUIRED", "请先选择一个可用模型。")
        model = self.models.get(str(model_profile_id))
        if not model.get("enabled"):
            raise FirstAnalysisError("MODEL_UNAVAILABLE", "当前模型连接不可用。")
        if not acknowledge_privacy:
            raise FirstAnalysisError("PRIVACY_CONSENT_REQUIRED", "首次分析前需要确认内容授权。")

        scope = scopes[0]
        try:
            grant = self.registry.get(str(scope.get("authorization_ref") or ""), "source")
        except GrantError as exc:
            raise FirstAnalysisError("SCOPE_AUTHORIZATION_REQUIRED", "当前目录授权已失效，请重新选择文件夹。") from exc

        settings = load_default_settings(self.project_root).model_copy(update={
            "operation_mode": "preview_move",
            "classification_source": "auto_plan",
            "max_depth": int(context.get("max_directory_depth") or 2),
        })
        classification_request = {
            "user_instructions": user_message.strip(),
            "intent": "ORGANIZE_REQUEST",
            "conversation_id": conversation_id,
        }

        self._stage(emit, "scan", "扫描授权目录")
        task = self.tasks.create_task(
            f"{conversation.get('title') or '整理会话'} · 首次分析",
            grant.grant_id,
            None,
            settings,
            classification_request,
            str(model_profile_id),
            model,
        )
        self.conversations.link_task(conversation_id, task["id"])
        self._grant_privacy(task, model_profile_id, settings)
        # Granting content consent is itself a task revision.  Start the scan
        # against the persisted revision instead of the pre-consent snapshot.
        task = self.repository.get(task["id"])
        try:
            self.tasks.start(task["id"], task["revision"])
        except Exception as exc:
            raise FirstAnalysisError("SCAN_FAILED", "授权目录扫描失败，请检查目录是否仍然可用。") from exc

        files, total = self.repository.list_files(task["id"], limit=500, offset=0)
        for item in files:
            self.conversations.attach_file(conversation_id, str(item["id"]))
        eligible_modalities = self.repository.eligible_modalities(task["id"])
        if not eligible_modalities:
            raise FirstAnalysisError("NO_SUPPORTED_FILES", "授权目录中没有可分析的受支持文件。", {"file_count": total})
        try:
            self.models.require_capabilities(str(model_profile_id), eligible_modalities)
        except ModelError as exc:
            self._fail_task(task["id"], str(exc))
            raise FirstAnalysisError(
                str(exc),
                "当前模型能力不足或尚未完成探测，请在模型连接页完成能力探测后重试。",
                {"missing_capabilities": getattr(exc, "missing_capabilities", [])},
            ) from exc
        self._stage(emit, "scan_complete", "扫描完成", {"file_count": total, "modalities": sorted(eligible_modalities)})

        self._stage(emit, "evidence", "分析文件内容")
        try:
            drafts = self.planner.plan_task(task["id"])
        except (PrivacyError, ModelError) as exc:
            self._fail_task(task["id"], str(exc))
            raise FirstAnalysisError(str(exc), "文件内容分析未完成，请检查模型连接和内容授权。") from exc
        if not drafts:
            raise FirstAnalysisError("TAXONOMY_EMPTY", "模型没有生成可用的整理分类。")
        self._stage(emit, "taxonomy", "生成分类方案", {"category_count": sum(len(item["nodes"]) for item in drafts)})

        classifications: list[dict[str, Any]] = []
        approved_taxonomies: list[dict[str, Any]] = []
        for draft in drafts:
            current_task = self.repository.get(task["id"])
            approved = self.taxonomies.approve(task["id"], draft["taxonomy_id"], draft["tree_hash"], current_task["revision"])
            approved_taxonomies.append(approved)
            try:
                classifications.extend(self.classifier.classify_taxonomy(task["id"], approved))
            except (PrivacyError, ModelError) as exc:
                self._fail_task(task["id"], str(exc))
                raise FirstAnalysisError(str(exc), "文件分类未完成，请检查模型连接和内容授权。") from exc
        self.repository.advance_after_classification(task["id"])
        self._stage(emit, "classification", "完成文件分类", {
            "classified_count": len(classifications),
            "uncertain_count": sum(1 for item in classifications if item.get("needs_review") or item.get("abstain")),
        })

        self._stage(emit, "preview", "生成整理预览")
        try:
            plan = self.operations.compile(task["id"])
        except (KeyError, ValueError) as exc:
            raise FirstAnalysisError("PLAN_COMPILE_FAILED", "整理预览生成失败，请重新分析。") from exc
        operations = list(plan.operations)
        affected = sum(1 for item in operations if item.action in {"move", "copy"})
        kept = len(operations) - affected
        conflicts = sum(1 for item in operations if item.reason and item.reason not in {"REPORT_ONLY", "SOURCE_EQUALS_TARGET"})
        taxonomy_snapshot = {
            "taxonomy_id": approved_taxonomies[0]["taxonomy_id"],
            "nodes": [node for taxonomy in approved_taxonomies for node in taxonomy["nodes"]],
            "scopes": approved_taxonomies,
        }
        current_context = self.conversations.get_context(conversation_id)
        intent_context = self.conversations.update_context(
            conversation_id,
            current_context["context_revision"],
            {"organization_intent": {"kind": "ORGANIZE_REQUEST", "text": user_message.strip()},
             "strategy_state": {"first_analysis_task_id": task["id"], "stage": "COMPLETED"}},
        )
        version = self.conversations.create_plan_version(
            conversation_id,
            expected_context_revision=intent_context["context_revision"],
            basis_context_revision=intent_context["context_revision"],
            basis_file_state_revision=intent_context["file_state_revision"],
            source="USER_REQUEST",
            plan_kind="FULL",
            status="PROPOSED",
            taxonomy_id=approved_taxonomies[0]["taxonomy_id"],
            taxonomy_snapshot=taxonomy_snapshot,
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            summary=f"首次分析 {total} 个文件，建议分为 {len(taxonomy_snapshot['nodes'])} 个内容类别",
            change_summary={"metrics": {
                "file_count": total,
                "affected_files": affected,
                "kept_files": kept,
                "uncertain_count": sum(1 for item in classifications if item.get("needs_review") or item.get("abstain")),
                "category_count": len(taxonomy_snapshot["nodes"]),
                "plan_kind": "FULL",
                "baseline_execution_round_id": None,
            }},
            affected_file_count=affected,
            kept_file_count=kept,
            conflict_count=conflicts,
            created_by_message_id=message_id,
        )
        self.conversations.link_task(conversation_id, task["id"], version["id"])
        latest_context = self.conversations.get_context(conversation_id)
        if latest_context.get("current_taxonomy_id") != approved_taxonomies[0]["taxonomy_id"]:
            latest_context = self.conversations.update_context(
                conversation_id,
                latest_context["context_revision"],
                {"current_taxonomy_id": approved_taxonomies[0]["taxonomy_id"]},
            )
        assistant = self.conversations.append_message(
            conversation_id,
            "ASSISTANT",
            f"我分析了 {total} 个文件，建议分为 {len(taxonomy_snapshot['nodes'])} 个内容类别，生成整理方案 v{version['version_number']}。其中 {version['conflict_count']} 个文件需要保留或人工确认；当前只生成预览，磁盘文件没有变化。",
            message_type="PLAN_PROPOSAL",
            metadata={"metrics": version["change_summary"]["metrics"], "task_id": task["id"], "progress": progress_events},
            referenced_plan_version_id=version["id"],
        )
        self._stage(emit, "complete", "整理预览已生成", {"plan_version": version["version_number"], "plan_hash": plan.plan_hash})
        return {
            "status": "COMPLETED",
            "intent": "ORGANIZE_REQUEST",
            "task": self.repository.get(task["id"]),
            "files": self.conversations.list_conversation_files(conversation_id),
            "plan_version": version,
            "assistant_message": assistant,
            "context": latest_context,
            "progress": progress_events,
            "metrics": version["change_summary"]["metrics"],
            "disk_files_changed": False,
        }

    @staticmethod
    def _stage(progress: Callable[[dict[str, Any]], None] | None, stage: str, label: str, details: dict[str, Any] | None = None) -> None:
        if progress:
            progress({"stage": stage, "label": label, "status": "COMPLETED", "details": details or {}})

    def _grant_privacy(self, task: dict[str, Any], profile_id: str, settings: TaskSettings) -> None:
        privacy = settings.privacy
        data_types = [
            name for name, enabled in (
                ("extracted_text", privacy.allow_extracted_text),
                ("derivative_images", privacy.allow_derivative_images),
                ("video_frames", privacy.allow_video_frames),
                ("asr_text", privacy.allow_asr_text),
            ) if enabled
        ]
        budget = settings.task_budget.model_dump(mode="python")
        self.privacy.grant(
            task["id"], profile_id, data_types, budget,
            scope_hash(profile_id, data_types, budget), task["revision"], True,
        )

    def _fail_task(self, task_id: str, code: str) -> None:
        try:
            self.repository.fail_scan(task_id, code[:120])
        except Exception:
            pass
