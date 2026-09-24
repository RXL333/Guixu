import { cleanup, fireEvent, render, waitFor } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ConversationMessage from '../src/features/conversations/components/ConversationMessage.vue'
import ChatComposer from '../src/features/conversations/components/ChatComposer.vue'
import FileWorkspace from '../src/features/conversations/components/FileWorkspace.vue'
import ConversationWorkspacePage from '../src/pages/ConversationWorkspacePage.vue'
import PlanPreviewCard from '../src/features/conversations/components/PlanPreviewCard.vue'
import ExecutionResultCard from '../src/features/conversations/components/ExecutionResultCard.vue'
import UndoPreviewCard from '../src/features/conversations/components/UndoPreviewCard.vue'
import { api } from '../src/services/api'
import { useConversationStore } from '../src/features/conversations/store'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const message = (role: 'USER'|'ASSISTANT'|'SYSTEM_EVENT', content: string, sequence_number: number) => ({
  id: `m-${sequence_number}`, conversation_id: 'c1', role, content, sequence_number,
  message_type: role === 'SYSTEM_EVENT' ? 'SYSTEM_EVENT' : 'TEXT', status: 'ACTIVE', created_at: '2026-09-20T08:32:00Z',
}) as any

describe('phase E Conversation Workspace', () => {
  it('renders ordered user, assistant and system-event messages', () => {
    const view = render(ConversationMessage, { props: { message: message('USER', '整理这些照片', 1) } })
    expect(view.getByText('我')).toBeTruthy()
    expect(view.getByText('整理这些照片')).toBeTruthy()
    const assistant = render(ConversationMessage, { props: { message: message('ASSISTANT', '已保存你的消息。', 2) } })
    expect(assistant.getByText('归序')).toBeTruthy()
    const system = render(ConversationMessage, { props: { message: message('SYSTEM_EVENT', '系统状态', 3) } })
    expect(system.getByText('系统')).toBeTruthy()
  })

  it('persists composer input through Message API without fabricating assistant output', async () => {
    const pinia = createPinia()
    const store = useConversationStore(pinia)
    store.currentConversation = { id: 'c1', title: '摄影照片整理', status: 'ACTIVE', revision: 1, created_at: 'now', updated_at: 'now' }
    vi.spyOn(api, 'appendConversationMessage').mockResolvedValue(message('USER', '按照内容整理', 1))
    const view = render(ChatComposer, { global: { plugins: [pinia] } })
    await fireEvent.update(view.getByRole('textbox', { name: '整理要求' }), '按照内容整理')
    await fireEvent.keyDown(view.getByRole('textbox', { name: '整理要求' }), { key: 'Enter' })
    await waitFor(() => expect(api.appendConversationMessage).toHaveBeenCalledWith('c1', {
      role: 'USER', content: '按照内容整理', selected_file_ids: [], focused_file_id: null,
      active_category_id: null, expected_context_revision: undefined,
    }))
    expect(view.queryByText('好的，我来帮你整理。')).toBeNull()
  })

  it('switches file workspace tabs and supports selected file ids', async () => {
    const pinia = createPinia()
    const store = useConversationStore(pinia)
    store.files = [{ id: 'cf1', conversation_id: 'c1', file_id: 'f1', first_seen_path: 'D:/Photos/DSC_001.jpg', current_known_path: 'D:/Photos/DSC_001.jpg', added_at: '2026-09-20T08:00:00Z', state: 'ACTIVE' }] as any
    store.currentConversation = { id: 'c1', title: '摄影照片整理', status: 'ACTIVE', revision: 1, created_at: 'now', updated_at: 'now', scopes: [{ id: 's1', scope_kind: 'folder', source_root: 'D:/Photos', display_name: 'Photos', created_at: 'now' }] }
    const view = render(FileWorkspace, { props: { plans: [], executions: [] }, global: { plugins: [pinia] } })
    expect(view.getAllByText('DSC_001.jpg').length).toBeGreaterThan(0)
    await fireEvent.click(view.getAllByText('DSC_001.jpg')[0])
    expect(store.selectedFileIds).toEqual(['f1'])
    await fireEvent.click(view.getByRole('tab', { name: /整理预览/ }))
    expect(view.getByText('还没有整理方案')).toBeTruthy()
    await fireEvent.click(view.getByRole('tab', { name: /变更记录/ }))
    expect(view.getByText('还没有执行记录')).toBeTruthy()
  })

  it('keeps the root empty state explicit and does not render fake AI', async () => {
    const pinia = createPinia()
    const testRouter = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: ConversationWorkspacePage }] })
    await testRouter.push('/')
    await testRouter.isReady()
    vi.spyOn(api, 'conversations').mockResolvedValue([])
    const view = render(ConversationWorkspacePage, { global: { plugins: [pinia, testRouter] } })
    await waitFor(() => expect(view.getByText(/归序只会处理你授权的目录/)).toBeTruthy())
    expect(view.getByRole('button', { name: '选择文件夹' })).toBeTruthy()
    expect(view.queryByText('好的，我来帮你整理。')).toBeNull()
  })

  it('browses immutable plan history and exposes safe restore action', async () => {
    const pinia = createPinia()
    const store = useConversationStore(pinia)
    store.currentConversation = { id: 'c1', title: '摄影照片整理', status: 'ACTIVE', revision: 1, created_at: 'now', updated_at: 'now', scopes: [{ id: 's1', scope_kind: 'folder', source_root: 'D:/Photos', display_name: 'Photos', created_at: 'now' }] }
    const v1 = { id: 'p1', conversation_id: 'c1', version_number: 1, basis_context_revision: 1, source: 'USER_REQUEST', status: 'SUPERSEDED', summary: '旧方案', affected_file_count: 2, created_at: 'now' } as any
    const v2 = { id: 'p2', conversation_id: 'c1', version_number: 2, basis_context_revision: 2, source: 'USER_REQUEST', status: 'PROPOSED', summary: '当前方案', affected_file_count: 3, created_at: 'now' } as any
    const view = render(FileWorkspace, {
      props: {
        plans: [v1, v2],
        executions: [],
        currentPlanVersion: v2,
        viewingPlanVersion: v1,
        planDiff: { old_plan_version_id: 'p1', new_plan_version_id: 'p2', categories_added: [], categories_removed: [], category_changes: [], file_changes: [], affected_file_ids: [], summary_counts: { total: 0, unchanged: 0, target_changed: 0 } },
      },
      global: { plugins: [pinia] },
    })
    await fireEvent.click(view.getByRole('tab', { name: /整理预览/ }))
    expect(view.getByText('历史方案预览 · v1')).toBeTruthy()
    expect(view.getByText('这是历史方案，不代表当前整理状态。')).toBeTruthy()
    await fireEvent.click(view.getByRole('button', { name: '恢复为新方案' }))
    expect(view.emitted('restoreVersion')?.[0]).toEqual(['p1'])
  })

  it('keeps the composer active after execution and prepares a local delta refinement', async () => {
    const pinia = createPinia()
    const store = useConversationStore(pinia)
    store.currentConversation = { id: 'c1', title: '摄影照片整理', status: 'ACTIVE', revision: 1, created_at: 'now', updated_at: 'now' }
    store.context = { id: 'ctx', conversation_id: 'c1', context_revision: 5, max_directory_depth: 2, file_state_revision: 2, created_at: 'now', updated_at: 'now' } as any
    store.executionRounds = [{ id: 'r1', conversation_id: 'c1', round_number: 1, plan_version_id: 'p1', execution_plan_id: 'core1', status: 'COMPLETED', affected_file_count: 48, created_at: 'now' }] as any
    const delta = { id: 'p2', conversation_id: 'c1', version_number: 2, parent_plan_version_id: 'p1', baseline_execution_round_id: 'r1', basis_context_revision: 6, source: 'USER_REQUEST', plan_kind: 'DELTA', status: 'PROPOSED', plan_hash: 'a'.repeat(64), summary: '局部调整 · 3 个文件', affected_file_count: 3, kept_file_count: 45, created_at: 'now' } as any
    vi.spyOn(api, 'appendConversationMessage').mockResolvedValue(message('USER', '建筑里的夜景放到风景，其他不要动。', 2))
    vi.spyOn(api, 'prepareConversationRefinement').mockResolvedValue({
      status: 'WAITING_FOR_APPROVAL', intent: 'POST_EXECUTION_REFINEMENT',
      affected_scope: { scope_type: 'LOCAL', affected_category_ids: ['building'], candidate_file_ids: Array.from({ length: 12 }, (_, i) => `f${i}`), target_category_id: 'landscape', requires_global_replan: false, preserve_unaffected: true, reason: 'validated' },
      metrics: { total_scope_files: 48, affected_files: 12, evidence_reused: 10, evidence_refreshed: 2, invalid_evidence: 0, delta_plan_count: 3, ai_calls: 1 },
      plan_version: delta, assistant_message: message('ASSISTANT', '本轮只调整 3 个文件，其他保持不变。', 3),
    })
    vi.spyOn(api, 'conversationContext').mockResolvedValue({ ...store.context, context_revision: 7, current_plan_version_id: 'p2' } as any)
    expect(await store.appendMessage('建筑里的夜景放到风景，其他不要动。')).toBe(true)
    expect(api.prepareConversationRefinement).toHaveBeenCalledWith('c1', {
      user_message: '建筑里的夜景放到风景，其他不要动。', confirmed_global: false,
      referenced_file_ids: [], trigger_message_id: 'm-2',
    })
    expect(store.affectedScope?.scope_type).toBe('LOCAL')
    expect(store.refinementMetrics?.delta_plan_count).toBe(3)
    expect(store.planVersions.at(-1)?.plan_kind).toBe('DELTA')
    expect(store.messages.at(-1)?.role).toBe('ASSISTANT')
  })

  it('renders delta approval and the post-execution continuation cue', async () => {
    const delta = { id: 'p2', conversation_id: 'c1', version_number: 2, baseline_execution_round_id: 'r1', basis_context_revision: 6, source: 'USER_REQUEST', plan_kind: 'DELTA', status: 'PROPOSED', plan_hash: 'a'.repeat(64), summary: '局部调整', affected_file_count: 3, kept_file_count: 45, created_at: 'now', change_summary: { metrics: { affected_files: 12, evidence_reused: 10 }, scope: { scope_type: 'LOCAL' } } } as any
    const view = render(PlanPreviewCard, { props: { plan: delta, current: true } })
    expect(view.getByText('局部调整 · v2')).toBeTruthy()
    expect(view.getByText(/其他 45 个保持不变/)).toBeTruthy()
    await fireEvent.click(view.getByRole('button', { name: /确认执行/ }))
    expect(view.emitted('approve')?.[0]).toEqual([delta])
    const execution = render(ExecutionResultCard, { props: { round: { id: 'r2', conversation_id: 'c1', round_number: 2, plan_version_id: 'p2', execution_plan_id: 'core2', status: 'COMPLETED', affected_file_count: 3, created_at: 'now', summary: { description: '本轮调整完成。' } } as any } })
    expect(execution.getByText('整理完成，你可以继续告诉归序需要调整的地方。')).toBeTruthy()
  })

  it('requires global confirmation and refreshes files after execution round two', async () => {
    const pinia = createPinia()
    const store = useConversationStore(pinia)
    const conversation = { id: 'c1', title: '摄影照片整理', status: 'ACTIVE', revision: 1, created_at: 'now', updated_at: 'now' } as any
    const context = { id: 'ctx', conversation_id: 'c1', context_revision: 8, current_plan_version_id: 'p2', max_directory_depth: 2, file_state_revision: 2, created_at: 'now', updated_at: 'now' } as any
    const plan = { id: 'p2', conversation_id: 'c1', version_number: 2, baseline_execution_round_id: 'r1', basis_context_revision: 7, source: 'USER_REQUEST', plan_kind: 'DELTA', status: 'PROPOSED', plan_hash: 'a'.repeat(64), summary: '局部调整', affected_file_count: 1, created_at: 'now' } as any
    store.currentConversation = conversation
    store.context = context
    store.planVersions = [plan]
    store.models = [{ id: 'm1', name: 'Model' } as any]
    vi.spyOn(api, 'prepareConversationRefinement').mockResolvedValue({ status: 'GLOBAL_REPLAN_CONFIRMATION_REQUIRED', intent: 'POST_EXECUTION_REFINEMENT', affected_scope: { scope_type: 'GLOBAL', affected_category_ids: [], candidate_file_ids: ['f1'], requires_global_replan: true, preserve_unaffected: false, reason: 'global' }, metrics: { total_scope_files: 48, affected_files: 48, evidence_reused: 45, evidence_refreshed: 3, invalid_evidence: 0, delta_plan_count: 0, ai_calls: 1 } })
    expect(await store.prepareRefinement('全部重新规划')).toBe(true)
    expect(store.pendingGlobalMessage).toBe('全部重新规划')
    expect(store.refinementMetrics?.evidence_reused).toBe(45)

    vi.spyOn(api, 'approveConversationPlanVersion').mockResolvedValue({ id: 'approval' })
    vi.spyOn(api, 'executeConversationRefinement').mockResolvedValue({ execution_round: { id: 'r2', conversation_id: 'c1', round_number: 2, plan_version_id: 'p2', execution_plan_id: 'core2', status: 'COMPLETED', affected_file_count: 1, created_at: 'now' }, workspace: {} as any })
    vi.spyOn(api, 'conversation').mockResolvedValue(conversation)
    vi.spyOn(api, 'conversationMessages').mockResolvedValue([])
    vi.spyOn(api, 'conversationContext').mockResolvedValue({ ...context, context_revision: 9 } as any)
    vi.spyOn(api, 'conversationFiles').mockResolvedValue([{ id: 'cf1', conversation_id: 'c1', file_id: 'f1', first_seen_path: 'D:/Photos/a.jpg', current_known_path: 'D:/Photos/风景/a.jpg', added_at: 'now', state: 'ACTIVE' }] as any)
    vi.spyOn(api, 'conversationPlans').mockResolvedValue([{ ...plan, status: 'EXECUTED' }] as any)
    vi.spyOn(api, 'conversationExecutions').mockResolvedValue([{ id: 'r1', conversation_id: 'c1', round_number: 1, plan_version_id: 'p1', execution_plan_id: 'core1', status: 'COMPLETED', affected_file_count: 48, created_at: 'now' }, { id: 'r2', conversation_id: 'c1', round_number: 2, plan_version_id: 'p2', execution_plan_id: 'core2', status: 'COMPLETED', affected_file_count: 1, created_at: 'now' }] as any)
    expect(await store.approveAndExecute(plan)).toBe(true)
    expect(store.files[0].current_known_path).toContain('/风景/')
    expect(store.executionRounds.at(-1)?.round_number).toBe(2)
  })

  it('renders removable reference chips, batches selection into one message, then clears it', async () => {
    const pinia = createPinia()
    const store = useConversationStore(pinia)
    store.currentConversation = { id: 'c1', title: '引用测试', status: 'ACTIVE', revision: 1, created_at: 'now', updated_at: 'now' } as any
    store.context = { id: 'ctx', conversation_id: 'c1', context_revision: 4, max_directory_depth: 2, file_state_revision: 1, created_at: 'now', updated_at: 'now' } as any
    store.files = Array.from({ length: 500 }, (_, index) => ({ id: `cf${index}`, conversation_id: 'c1', file_id: `f${index}`, first_seen_path: `D:/Photos/${index}.jpg`, current_known_path: `D:/Photos/${index}.jpg`, state: 'ACTIVE', added_at: 'now' })) as any
    store.selectedFileIds = Array.from({ length: 500 }, (_, index) => `f${index}`)
    vi.spyOn(api, 'appendConversationMessage').mockResolvedValue({ ...message('USER', '这些放到旅行', 1), referenced_file_ids: Array.from({ length: 499 }, (_, index) => `f${index + 1}`), reference_source: 'UI_SELECTION' } as any)
    const view = render(ChatComposer, { global: { plugins: [pinia] } })
    expect(view.getByText('已引用 500 个文件')).toBeTruthy()
    expect(view.getByText('+497')).toBeTruthy()
    await fireEvent.click(view.getByRole('button', { name: /0.jpg/ }))
    expect(store.selectedFileIds).toHaveLength(499)
    await fireEvent.update(view.getByRole('textbox', { name: '整理要求' }), '这些放到旅行')
    await fireEvent.click(view.getByRole('button', { name: '发送消息' }))
    await waitFor(() => expect(api.appendConversationMessage).toHaveBeenCalledWith('c1', expect.objectContaining({ selected_file_ids: expect.arrayContaining(['f1', 'f499']), expected_context_revision: 4 })))
    expect(store.selectedFileIds).toEqual([])
  })

  it('shows immutable message reference badges and emits ids for FileWorkspace highlighting', async () => {
    const referenced = { ...message('ASSISTANT', '我找到 3 个文件', 2), referenced_file_ids: ['f1', 'f2', 'f3'], file_references: [{ file_id: 'f1', reference_source: 'RECENT_MESSAGE_REFERENCE', reference_role: 'RESULT', state: 'MISSING', basename: 'a.jpg' }] } as any
    const view = render(ConversationMessage, { props: { message: referenced } })
    const badge = view.getByRole('button', { name: /引用 · 3 个文件/ })
    expect(view.getByText(/含不可见文件/)).toBeTruthy()
    await fireEvent.click(badge)
    expect(view.emitted('references')?.[0]).toEqual([['f1', 'f2', 'f3']])
  })

  it('clears ephemeral selection when switching conversations', async () => {
    const pinia = createPinia()
    const store = useConversationStore(pinia)
    store.selectedFileIds = ['a1', 'a2']
    const conversation = { id: 'b', title: 'B', status: 'ACTIVE', revision: 1, created_at: 'now', updated_at: 'now' } as any
    vi.spyOn(api, 'conversation').mockResolvedValue(conversation)
    vi.spyOn(api, 'conversationMessages').mockResolvedValue([])
    vi.spyOn(api, 'conversationContext').mockResolvedValue({ id: 'ctx-b', conversation_id: 'b', context_revision: 1, max_directory_depth: 2, file_state_revision: 1, created_at: 'now', updated_at: 'now' } as any)
    vi.spyOn(api, 'conversationFiles').mockResolvedValue([])
    vi.spyOn(api, 'conversationPlans').mockResolvedValue([])
    vi.spyOn(api, 'conversationExecutions').mockResolvedValue([])
    vi.spyOn(api, 'models').mockResolvedValue([])
    await store.loadConversation('b')
    expect(store.selectedFileIds).toEqual([])
    expect(store.focusedFileId).toBeNull()
  })

  it('renders UndoPreviewCard and requires explicit confirmation', async () => {
    const plan = {
      id: 'u1', conversation_id: 'c1', target_execution_round_id: 'r2', status: 'WAITING_FOR_APPROVAL',
      basis_file_state_revision: 4, plan_hash: 'a'.repeat(64), requested_file_ids: [], approval: {}, created_at: 'now',
      summary: { target_round_number: 2, total: 2, ready: 2, blocked: 0, partial: false },
      items: [
        { id: 'ui1', file_id: 'f1', original_operation_id: 'o1', operation_kind: 'MOVE', ordinal: 0, current_source: 'D:/Photos/风景/a.jpg', restore_target: 'D:/Photos/建筑/a.jpg', expected_fingerprint: 'a'.repeat(64), status: 'READY' },
        { id: 'ui2', file_id: 'f2', original_operation_id: 'o2', operation_kind: 'MOVE', ordinal: 1, current_source: 'D:/Photos/风景/b.jpg', restore_target: 'D:/Photos/建筑/b.jpg', expected_fingerprint: 'b'.repeat(64), status: 'READY' },
      ],
    } as any
    const view = render(UndoPreviewCard, { props: { plan } })
    expect(view.getByText('撤销第 2 次整理')).toBeTruthy()
    expect(view.getByText('2', { selector: 'strong' })).toBeTruthy()
    await fireEvent.click(view.getByRole('button', { name: '确认撤销' }))
    expect(view.emitted('confirm')).toHaveLength(1)
    await fireEvent.click(view.getByRole('button', { name: '取消' }))
    expect(view.emitted('cancel')).toHaveLength(1)
  })

  it('routes conversational undo to preview without refinement or direct execution', async () => {
    const pinia = createPinia()
    const store = useConversationStore(pinia)
    store.currentConversation = { id: 'c1', title: '撤销测试', status: 'ACTIVE', revision: 1, created_at: 'now', updated_at: 'now' } as any
    store.context = { id: 'ctx', conversation_id: 'c1', context_revision: 5, max_directory_depth: 2, file_state_revision: 4, created_at: 'now', updated_at: 'now' } as any
    store.executionRounds = [{ id: 'r2', conversation_id: 'c1', round_number: 2, plan_version_id: 'p2', execution_plan_id: 'core2', status: 'COMPLETED', affected_file_count: 1, created_at: 'now', round_kind: 'FORWARD' }] as any
    vi.spyOn(api, 'appendConversationMessage').mockResolvedValue({ ...message('USER', '撤销刚才那次调整。', 3), referenced_file_ids: [] } as any)
    vi.spyOn(api, 'requestConversationUndo').mockResolvedValue({
      target: { execution_round_id: 'r2' },
      undo_plan: { id: 'u1', conversation_id: 'c1', target_execution_round_id: 'r2', status: 'WAITING_FOR_APPROVAL', basis_file_state_revision: 4, plan_hash: 'a'.repeat(64), requested_file_ids: [], approval: {}, created_at: 'now', summary: { target_round_number: 2, total: 1, ready: 1, blocked: 0 }, items: [] } as any,
    })
    const refinement = vi.spyOn(api, 'prepareConversationRefinement')
    const execute = vi.spyOn(api, 'executeConversationUndo')
    expect(await store.appendMessage('撤销刚才那次调整。')).toBe(true)
    expect(api.requestConversationUndo).toHaveBeenCalledWith('c1', { user_message: '撤销刚才那次调整。', referenced_file_ids: [] })
    expect(store.pendingUndoPlan?.id).toBe('u1')
    expect(refinement).not.toHaveBeenCalled()
    expect(execute).not.toHaveBeenCalled()
  })

  it('shows partial undo history and emits the shared quick-undo action', async () => {
    const round = { id: 'r2', conversation_id: 'c1', round_number: 2, plan_version_id: 'p2', execution_plan_id: 'core2', status: 'COMPLETED', affected_file_count: 10, created_at: 'now', round_kind: 'FORWARD', undo_state: 'PARTIALLY_UNDONE', undone_file_count: 3, reversible_file_count: 10 } as any
    const view = render(ExecutionResultCard, { props: { round } })
    expect(view.getByText('部分撤销 · 3 / 10')).toBeTruthy()
    await fireEvent.click(view.getByRole('button', { name: '撤销' }))
    expect(view.emitted('undo')?.[0]).toEqual([round])
  })
})
