<script setup lang="ts">
// Explicit development-only UI fixtures. This module is absent from production builds.
// These snapshots never call a model or execute filesystem operations.
import { onBeforeUnmount, ref, watch } from 'vue'
import ConversationWorkspacePage from '../pages/ConversationWorkspacePage.vue'
import { useConversationStore } from '../features/conversations/store'
const store = useConversationStore()
const originalState = JSON.parse(JSON.stringify(store.$state))
const originalActions = Object.fromEntries(Object.entries(store).filter(([key, value]) => typeof value === 'function' && !key.startsWith('$')))
// Block every domain action by default; visual-only selection is explicitly allowed.
for (const key of Object.keys(originalActions)) {
  if (['toggleFile', 'removeFileReference', 'clearFileReferences', 'selectReferencedFiles', 'clearError', 'clearNotice'].includes(key)) continue
  Object.assign(store, { [key]: async () => { store.notice = '界面验收样例：未调用真实服务。' } })
}
// Never leave fixture data or stubbed actions in the live application store.
onBeforeUnmount(() => {
  store.$patch(originalState)
  Object.assign(store, originalActions)
})
const scenario = ref('normal-chat')
const scenarios = ['empty-conversation', 'normal-chat', 'file-selection', 'reference-chips', 'agent-analyzing', 'plan-preview', 'plan-diff', 'plan-version-history', 'waiting-approval', 'execution-running', 'execution-success', 'post-execution-chat', 'undo-preview', 'undo-conflict', 'session-recovery', 'file-workspace-list', 'file-workspace-grid', '5000-files', '500-messages', 'long-text']
const now = '2026-09-22T07:00:00Z'
store.loadConversations = async () => {}
store.loadModels = async () => {}
store.loadConversation = async () => {}
store.appendMessage = async () => { store.notice = '界面验收样例：未发送消息，也未调用模型。'; return false }
store.approveAndExecute = async () => { store.notice = '界面验收样例：不会执行文件操作。'; return false }
store.confirmUndo = async () => { store.notice = '界面验收样例：不会执行撤销。'; return false }
store.reconcileConversation = async () => { store.notice = '界面验收样例：未访问真实目录。'; return null }
function apply() {
  const long = scenario.value === 'long-text'
  store.currentConversation = { id: 'ui-review', title: long ? '摄影照片整理 · 大学毕业旅行与建筑研究资料的长期归档和内容分类要求'.repeat(4) : '摄影照片整理', status: 'ACTIVE', revision: 1, model_profile_id: 'review-model', created_at: now, updated_at: now, scopes: [{ id: 'scope', source_root: 'D:\\Photos\\Trip', display_name: long ? 'D:\\' + '超长文件夹路径\\'.repeat(20) : 'D:\\Photos\\Trip', scope_kind: 'folder', created_at: now }] }
  store.models = [{ id: 'review-model', name: long ? 'Local Model · Long Context Model Name Test' : '界面样例模型', capabilities: {}, enabled: false } as any]
  store.context = { id: 'ctx', conversation_id: 'ui-review', context_revision: 1, file_state_revision: 1, max_directory_depth: 2, created_at: now, updated_at: now } as any
  store.messages = scenario.value === 'empty-conversation' ? [] : [
    { id: 'm1', conversation_id: 'ui-review', role: 'USER', content: '按照内容整理这些照片，不要分得太细。', sequence_number: 1, message_type: 'TEXT', status: 'ACTIVE', created_at: now },
    { id: 'm2', conversation_id: 'ui-review', role: 'ASSISTANT', content: long ? '这是用于检查长回复排版的界面样例。'.repeat(120) : '界面验收样例：照片按风景、人物和建筑分组。下方展示方案的视觉状态，未运行内容分析。', sequence_number: 2, message_type: 'TEXT', status: 'ACTIVE', created_at: now, referenced_file_ids: ['f0', 'f1', 'f2'] },
  ] as any
  if (scenario.value === '500-messages') store.messages = Array.from({ length: 520 }, (_, i) => ({ ...store.messages[i % 2], id: `message-${i}`, sequence_number: i + 1 }))
  const fileCount = scenario.value === '5000-files' ? 5000 : 48
  store.files = Array.from({ length: fileCount }, (_, index) => ({ id: `cf${index}`, conversation_id: 'ui-review', file_id: `f${index}`, first_seen_path: `D:/Photos/Trip/DSC_${String(index + 1).padStart(4, '0')}.jpg`, current_known_path: `D:/Photos/Trip/${['风景', '人物', '建筑'][index % 3]}/${long ? '毕业旅行照片_🌿_中文超长文件名_'.repeat(12) : ''}DSC_${String(index + 1).padStart(4, '0')}.jpg`, current_size_bytes: 2400000 + index * 130000, added_at: now, state: 'ACTIVE' })) as any
  store.selectedFileIds = ['file-selection', 'reference-chips'].includes(scenario.value) ? ['f0', 'f1', 'f2', 'f3', 'f4', 'f5', 'f6'] : []
  store.planVersions = []
  store.viewingPlanVersion = null
  store.planDiff = null
  store.executionRounds = []
  store.pendingUndoPlan = null
  store.recovery = null
  store.error = ''
  store.notice = ''
  store.refinementBusy = scenario.value === 'agent-analyzing'
  store.executionBusy = scenario.value === 'execution-running'
  store.undoBusy = false
  const plan = { id: 'p2', conversation_id: 'ui-review', version_number: 2, basis_context_revision: 1, source: 'USER_REQUEST', status: 'PROPOSED', summary: '将建筑夜景归入风景，其他照片保持不变', affected_file_count: 3, kept_file_count: 45, plan_kind: 'DELTA', baseline_execution_round_id: 'r1', created_at: now, change_summary: { metrics: { affected_files: 12, evidence_reused: 12 } } } as any
  if (['plan-preview', 'plan-diff', 'plan-version-history', 'waiting-approval'].includes(scenario.value)) {
    store.planVersions = [{ ...plan, id: 'p1', version_number: 1, status: 'SUPERSEDED', summary: '按照片内容分为风景、人物和建筑' }, plan]
    store.viewingPlanVersion = plan
    store.context!.current_plan_version_id = 'p2'
    store.planDiff = { old_plan_version_id: 'p1', new_plan_version_id: 'p2', categories_added: [{ category_id: 'night', name: '夜景' }], categories_removed: [], category_changes: [], file_changes: [], affected_file_ids: ['f0', 'f1', 'f2'], summary_counts: { target_changed: 3, unchanged: 45, total: 48 } } as any
  }
  if (['execution-success', 'post-execution-chat'].includes(scenario.value)) store.executionRounds = [{ id: 'r1', conversation_id: 'ui-review', round_number: 1, plan_version_id: 'p1', execution_plan_id: 'core', status: 'COMPLETED', affected_file_count: 46, created_at: now, summary: { description: '界面样例：46 个文件已整理，2 个保留原位置。' } }] as any
  if (['undo-preview', 'undo-conflict'].includes(scenario.value)) {
    const conflict = scenario.value === 'undo-conflict'
    store.pendingUndoPlan = { id: 'u1', status: conflict ? 'BLOCKED' : 'WAITING_FOR_APPROVAL', summary: { target_round_number: 2, ready: conflict ? 3 : 5, blocked: conflict ? 2 : 0 }, items: Array.from({ length: 5 }, (_, i) => ({ id: `u${i}`, current_source: `D:/Photos/Trip/风景/DSC_${i + 1}.jpg`, restore_target: `D:/Photos/Trip/建筑/DSC_${i + 1}.jpg`, status: conflict && i > 2 ? 'BLOCKED_TARGET_CONFLICT' : 'READY', operation_kind: 'MOVE' })) } as any
  }
  if (scenario.value === 'session-recovery') store.recovery = { reconciliation: { requires_user_action: true, scope_status: 'AVAILABLE', new_files: 5, moved: 2, renamed: 0, modified: 1, missing: 0 }, agent_turns: [] } as any
}
store.viewPlanVersion = async (id: string | null) => { store.viewingPlanVersion = store.planVersions.find(plan => plan.id === id) ?? null }
watch(scenario, apply, { immediate: true })
</script>
<template>
  <div class="review-switch"><label>界面验收样例 · 非实时任务 <select v-model="scenario" aria-label="验收场景"><option v-for="item in scenarios" :key="item">{{ item }}</option></select></label><a href="/">返回应用</a></div>
  <ConversationWorkspacePage :key="scenario" />
</template>
<style scoped>
.review-switch { position: fixed; left: 8px; bottom: 156px; z-index: 50; width: 224px; padding: 8px; background: var(--warning-soft); border: 1px solid var(--border-default); border-radius: 6px; color: var(--warning); font-size: 11px; }
.review-switch select { width: 100%; height: 28px; margin: 8px 0; border: 1px solid var(--border-strong); border-radius: 4px; background: var(--bg-surface); font-size: 12px; }
@media(max-width:1279px){.review-switch{width:180px;bottom:4px;left:80px}}
</style>
