import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api, ApiError, type AffectedScope, type Conversation, type ConversationContext, type ConversationExecutionRound, type ConversationFile, type ConversationMessage, type ConversationPlanDiff, type ConversationPlanVersion, type ConversationRecoveryStatus, type ConversationUndoPlan, type ModelProfile, type RefinementMetrics, type SourceFile } from '../../services/api'
import { isNamingRequest } from './intent'

export const useConversationStore = defineStore('conversations', () => {
  const conversations = ref<Conversation[]>([])
  const currentConversation = ref<Conversation | null>(null)
  const messages = ref<ConversationMessage[]>([])
  const context = ref<ConversationContext | null>(null)
  const files = ref<ConversationFile[]>([])
  const sourceFiles = ref<SourceFile[]>([])
  const sourceFilesTruncated = ref(false)
  const sourceInventoryRevision = ref(0)
  const planVersions = ref<ConversationPlanVersion[]>([])
  const viewingPlanVersion = ref<ConversationPlanVersion | null>(null)
  const planDiff = ref<ConversationPlanDiff | null>(null)
  const versionLoading = ref(false)
  const refinementBusy = ref(false)
  const analysisBusy = ref(false)
  const chatBusy = ref(false)
  const executionBusy = ref(false)
  const affectedScope = ref<AffectedScope | null>(null)
  const refinementMetrics = ref<RefinementMetrics | null>(null)
  const pendingGlobalMessage = ref('')
  const executionRounds = ref<ConversationExecutionRound[]>([])
  const models = ref<ModelProfile[]>([])
  const loading = ref(false)
  const loadingConversations = ref(false)
  const error = ref('')
  const notice = ref('')
  const selectedFileIds = ref<string[]>([])
  const focusedFileId = ref<string | null>(null)
  const activeCategoryId = ref<string | null>(null)
  const recovery = ref<ConversationRecoveryStatus | null>(null)
  const recoveryBusy = ref(false)
  const undoPlans = ref<ConversationUndoPlan[]>([])
  const pendingUndoPlan = ref<ConversationUndoPlan | null>(null)
  const undoBusy = ref(false)
  let conversationLoadGeneration = 0
  let modelLoadGeneration = 0

  const activeScope = computed(() => currentConversation.value?.scopes?.[0] ?? null)
  const activeModel = computed(() => {
    const id = currentConversation.value?.model_profile_id || context.value?.model_profile_id
    return models.value.find(model => model.id === id) ?? null
  })
  const currentPlanVersion = computed(() => {
    const id = context.value?.current_plan_version_id
    return planVersions.value.find(plan => plan.id === id) ?? planVersions.value.at(-1) ?? null
  })

  function clearError() { error.value = '' }
  function clearNotice() { notice.value = '' }

  async function loadConversations(view: 'active'|'deleted'|'all' = 'active') {
    loadingConversations.value = true
    error.value = ''
    try {
      conversations.value = await api.conversations(view)
      if (view === 'active' && currentConversation.value && !conversations.value.some(item => item.id === currentConversation.value?.id)) {
        currentConversation.value = null
      }
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : String(cause)
    } finally {
      loadingConversations.value = false
    }
  }

  async function loadModels() {
    const generation = ++modelLoadGeneration
    try {
      const latestModels = await api.models()
      if (generation === modelLoadGeneration) models.value = latestModels
    } catch {
      // Keep the last known choices if a background refresh fails.
    }
  }

  async function loadConversation(id: string) {
    const generation = ++conversationLoadGeneration
    loading.value = true
    error.value = ''
    notice.value = ''
    try {
      // Recovery status is an optional enhancement for older embedded shells
      // that may not expose a session token until after the first view loads.
      // Keep the core Conversation workspace load independent from it.
      const sessionReady = typeof window !== 'undefined' && Boolean(
        window.__GUIXU_SESSION__ || import.meta.env.VITE_GUIXU_SESSION,
      )
      const [conversation, nextMessages, nextContext, nextFiles, nextPlans, nextExecutions, nextUndoPlans] = await Promise.all([
        api.conversation(id),
        api.conversationMessages(id),
        api.conversationContext(id),
        api.conversationFiles(id),
        api.conversationPlans(id),
        api.conversationExecutions(id),
        sessionReady ? api.conversationUndoPlans(id) : Promise.resolve([]),
      ])
      if (generation !== conversationLoadGeneration) return
      currentConversation.value = conversation
      messages.value = nextMessages
      context.value = nextContext
      files.value = nextFiles
      sourceFiles.value = []
      sourceFilesTruncated.value = false
      sourceInventoryRevision.value++
      planVersions.value = nextPlans
      viewingPlanVersion.value = null
      planDiff.value = null
      executionRounds.value = nextExecutions
      recovery.value = null
      undoPlans.value = nextUndoPlans
      pendingUndoPlan.value = nextUndoPlans.find(item => ['WAITING_FOR_APPROVAL', 'APPROVED', 'BLOCKED', 'RECOVERY_REQUIRED'].includes(item.status)) ?? null
      affectedScope.value = null
      refinementMetrics.value = null
      pendingGlobalMessage.value = ''
      selectedFileIds.value = []
      focusedFileId.value = null
      activeCategoryId.value = null
      // Directory reconciliation hashes files. Keep it off the critical path for opening a chat.
      // Execution still performs its own backend validation before touching files.
      void (async () => {
        void loadModels()
        if (!nextFiles.length) {
          const inventoryRevision = sourceInventoryRevision.value
          void api.sourceFiles(id).then(inventory => {
            if (generation !== conversationLoadGeneration || currentConversation.value?.id !== id || inventoryRevision !== sourceInventoryRevision.value) return
            sourceFiles.value = inventory.files
            sourceFilesTruncated.value = inventory.truncated
          }).catch(() => { /* The file panel can still show the saved conversation state. */ })
        }
        if (!sessionReady) return
        try {
          const nextRecovery = await api.conversationRecoveryStatus(id, true)
          if (generation !== conversationLoadGeneration || currentConversation.value?.id !== id) return
          recovery.value = nextRecovery
          if (nextRecovery?.reconciliation?.workspace_changed) {
            const [latestFiles, latestContext] = await Promise.all([api.conversationFiles(id), api.conversationContext(id)])
            if (generation === conversationLoadGeneration && currentConversation.value?.id === id) {
              files.value = latestFiles
              context.value = latestContext
            }
          }
        } catch { /* Recovery status is optional while viewing saved messages. */ }
      })()
    } catch (cause) {
      if (generation !== conversationLoadGeneration) return
      error.value = cause instanceof Error ? cause.message : String(cause)
      currentConversation.value = null
      messages.value = []
      context.value = null
      files.value = []
      sourceFiles.value = []
      sourceFilesTruncated.value = false
      planVersions.value = []
      executionRounds.value = []
      recovery.value = null
      undoPlans.value = []
      pendingUndoPlan.value = null
    } finally {
      if (generation === conversationLoadGeneration) loading.value = false
    }
  }

  async function reconcileConversation() {
    const conversationId = currentConversation.value?.id
    if (!conversationId || recoveryBusy.value) return null
    recoveryBusy.value = true
    try {
      const summary = await api.reconcileConversation(conversationId)
      recovery.value = { ...(recovery.value || { conversation_id: conversationId, conversation_status: currentConversation.value?.status ?? 'ACTIVE', agent_turns: [], model_available: true, requires_user_action: false }), reconciliation: summary, requires_user_action: summary.requires_user_action }
      context.value = await api.conversationContext(conversationId)
      const inventory = await api.sourceFiles(conversationId)
      sourceFiles.value = inventory.files
      sourceFilesTruncated.value = inventory.truncated
      return summary
    } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); return null }
    finally { recoveryBusy.value = false }
  }

  async function resumeAnalysis() {
    const conversationId = currentConversation.value?.id
    if (!conversationId) return false
    try {
      const turn = await api.resumeConversationAnalysis(conversationId)
      recovery.value = { ...(recovery.value || { conversation_id: conversationId, conversation_status: currentConversation.value?.status ?? 'ACTIVE', reconciliation: null, model_available: true, requires_user_action: false }), agent_turns: [turn, ...(recovery.value?.agent_turns || [])] }
      notice.value = '已创建新的分析任务；不会自动重放上一次模型请求。'
      return true
    } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); return false }
  }

  async function retryAgentTurn(turnId: string) {
    const conversationId = currentConversation.value?.id
    if (!conversationId) return false
    try {
      const turn = await api.retryConversationAgentTurn(conversationId, turnId)
      recovery.value = { ...(recovery.value || { conversation_id: conversationId, conversation_status: currentConversation.value?.status ?? 'ACTIVE', reconciliation: null, model_available: true, requires_user_action: false }), agent_turns: [turn, ...(recovery.value?.agent_turns || [])] }
      notice.value = '已创建新的分析尝试。'
      return true
    } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); return false }
  }

  async function createConversation(scopeGrant: string, title = '未命名整理', modelProfileId?: string | null) {
    loading.value = true
    error.value = ''
    try {
      const conversation = await api.createConversation({ title, model_profile_id: modelProfileId ?? null, scope_grant: scopeGrant })
      conversations.value = [conversation, ...conversations.value.filter(item => item.id !== conversation.id)]
      await loadConversation(conversation.id)
      return conversation
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : String(cause)
      return null
    } finally {
      loading.value = false
    }
  }

  async function renameConversation(id: string, title: string) {
    try {
      const updated = await api.renameConversation(id, title)
      currentConversation.value = currentConversation.value?.id === id ? { ...currentConversation.value, ...updated } : currentConversation.value
      conversations.value = conversations.value.map(item => item.id === id ? { ...item, ...updated } : item)
    } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause) }
  }

  async function setConversationModel(modelProfileId: string) {
    const conversationId = currentConversation.value?.id
    if (!conversationId || !modelProfileId) return false
    try {
      const updated = await api.updateConversationModel(conversationId, modelProfileId)
      currentConversation.value = { ...currentConversation.value!, ...updated }
      conversations.value = conversations.value.map(item => item.id === conversationId ? { ...item, ...updated } : item)
      context.value = updated.context ?? await api.conversationContext(conversationId)
      notice.value = `已切换到 ${models.value.find(model => model.id === modelProfileId)?.name || '所选模型'}。`
      return true
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : String(cause)
      return false
    }
  }

  async function deleteConversation(id: string) {
    try {
      await api.deleteConversation(id)
      conversations.value = conversations.value.filter(item => item.id !== id)
      if (currentConversation.value?.id === id) {
        currentConversation.value = null
        messages.value = []
        context.value = null
        files.value = []
        planVersions.value = []
        executionRounds.value = []
      }
      notice.value = '会话记录已删除，磁盘文件未被修改。'
    } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause) }
  }

  async function appendMessage(content: string) {
    const conversationId = currentConversation.value?.id
    const message = content.trim()
    if (!conversationId || !message || chatBusy.value || analysisBusy.value) return false
    if (isNamingRequest(message)) {
      return prepareNaming(message)
    }
    if (/^(请)?(现在)?(开始|进行|重新进行|继续)(整理|分类|分析)(吧|一下|这些文件|这个文件夹)?[。.!！]?$|^(请)?(生成|更新|重新生成)(整理|分类)?方案|^(请)?帮我(开始)?(整理|分类)(一下|这些文件|这个文件夹|这些照片)?[。.!！]?$/.test(message)) {
      return startOrganization(message)
    }
    if (/^(请)?(撤销|恢复原位|放回去)/.test(message)) {
      try {
        const userMessage = await api.appendConversationMessage(conversationId, { role: 'USER', content: message,
          selected_file_ids: [...selectedFileIds.value], expected_context_revision: context.value?.context_revision })
        messages.value = [...messages.value, userMessage]
        const result = await api.requestConversationUndo(conversationId, {
          user_message: message, referenced_file_ids: userMessage.referenced_file_ids || [],
        })
        if (result.undo_plan) {
          pendingUndoPlan.value = result.undo_plan
          undoPlans.value = [result.undo_plan, ...undoPlans.value.filter(item => item.id !== result.undo_plan!.id)]
        }
        notice.value = result.undo_plan ? '撤销预览已生成，确认前磁盘不会变化。' : (result.query?.message || '没有可撤销的文件操作。')
        selectedFileIds.value = []
        return true
      } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); return false }
    }
    if (!activeModel.value) {
      error.value = '请先在右上角选择并测试模型，然后再聊天。'
      return false
    }
    chatBusy.value = true
    error.value = ''
    notice.value = 'AI 正在回复…'
    try {
      const inventoryOnly = files.value.length === 0
      const sourcePaths = inventoryOnly ? [...selectedFileIds.value] : []
      if (sourcePaths.length && !window.confirm(`将把选中的 ${sourcePaths.length} 张图片缩小后发送给“${activeModel.value.name}”分析，仅用于这次对话。是否继续？`)) {
        notice.value = ''
        return false
      }
      const result = await api.chatConversation(conversationId, message,
        inventoryOnly ? [] : [...selectedFileIds.value], sourcePaths, sourcePaths.length > 0)
      messages.value = [...messages.value, result.user_message, result.assistant_message]
      selectedFileIds.value = []
      focusedFileId.value = null
      notice.value = '已回复。准备好后可生成整理方案或命名方案。'
      currentConversation.value = { ...currentConversation.value!, last_message_at: result.assistant_message.created_at, updated_at: result.assistant_message.created_at }
      conversations.value = conversations.value.map(item => item.id === conversationId ? { ...item, last_message_at: result.assistant_message.created_at, updated_at: result.assistant_message.created_at } : item)
      return true
    } catch (cause) {
      notice.value = ''
      error.value = cause instanceof Error ? cause.message : String(cause)
      return false
    } finally { chatBusy.value = false }
  }

  async function startOrganization(command = '开始整理') {
    const conversationId = currentConversation.value?.id
    if (!conversationId || analysisBusy.value || refinementBusy.value) return false
    if (!activeModel.value) { error.value = '请先选择并测试模型。'; return false }
    const firstAnalysis = !planVersions.value.length && !executionRounds.value.length && !context.value?.current_plan_version_id
    const boundary = firstAnalysis ? '' : (currentPlanVersion.value?.created_at || '')
    const discussed = messages.value.filter(item => item.role === 'USER' && item.message_type === 'TEXT' && (!boundary || item.created_at > boundary))
      .slice(-30).map(item => item.content.trim())
      .filter(item => item && !item.startsWith('请按下面的用户讨论记录提取明确的整理要求'))
    if (!firstAnalysis && !discussed.length && command === '开始整理') {
      notice.value = currentPlanVersion.value?.status === 'PROPOSED'
        ? '当前方案已准备好，请先检查预览并确认执行。'
        : '请先说明这轮要调整哪些分类规则。'
      return false
    }
    const afterExecution = executionRounds.value.some(round => round.status === 'COMPLETED')
    const globalRequest = afterExecution && (/(重新|全部|整个)/.test(command) || discussed.some(text => /文件夹名|目录名|命名规则|全部|整个/.test(text)))
      ? '\n全部重新规划' : ''
    const instructions = [...new Set([...discussed, command])].join('\n') + globalRequest
    const request = `请按下面的用户讨论记录提取明确的整理要求；寒暄和提问不应当作分类指令。\n${instructions}`.slice(-12000)
    if (!firstAnalysis) return prepareRefinement(request)
    const acknowledged = typeof window !== 'undefined' && typeof window.confirm === 'function'
      ? window.confirm(`将按本次对话中的要求分析授权目录，并把允许的内容证据发送给“${activeModel.value.name}”。只生成预览，是否继续？`)
      : true
    if (!acknowledged) return false
    analysisBusy.value = true
    error.value = ''
    notice.value = '正在扫描授权目录并生成整理预览…'
    try {
      const result = await api.firstConversationTurn(conversationId, {
        content: command, requirements_context: request, acknowledge_privacy: true,
      })
      messages.value = [...messages.value, result.user_message, result.assistant_message]
      files.value = result.files
      context.value = result.context
      planVersions.value = [...planVersions.value.filter(item => item.id !== result.plan_version.id), result.plan_version]
      notice.value = `已生成方案 v${result.plan_version.version_number}，请检查并确认后执行。`
      return true
    } catch (cause) {
      if (cause instanceof ApiError && ['PLANNER_SCHEMA_INVALID', 'MODEL_OUTPUT_INVALID', 'CLASSIFICATION_SCHEMA_INVALID'].includes(cause.code)) {
        error.value = `AI 整理结果未通过安全校验（${cause.code}）。文件未移动。`
      } else error.value = cause instanceof Error ? cause.message : String(cause)
      notice.value = ''
      return false
    } finally { analysisBusy.value = false }
  }

  async function prepareNaming(command = '开始命名') {
    const conversationId = currentConversation.value?.id
    if (!conversationId || analysisBusy.value || refinementBusy.value) return false
    if (!activeModel.value) { error.value = '请先选择并测试模型。'; return false }
    if (!currentPlanVersion.value) {
      const analyzed = await startOrganization('分析文件内容，为命名生成预览')
      if (!analyzed) return false
    }
    const boundary = currentPlanVersion.value?.created_at || ''
    const discussed = messages.value.filter(item => item.role === 'USER' && item.message_type === 'TEXT' && item.created_at > boundary)
      .slice(-20).map(item => item.content.trim()).filter(Boolean)
    const instruction = [...discussed, command].join('\n').slice(-4000)
    const validIds = new Set(files.value.map(file => file.file_id))
    const selected = selectedFileIds.value.filter(id => validIds.has(id))
    refinementBusy.value = true
    error.value = ''
    notice.value = '正在根据文件内容生成命名预览…'
    try {
      const userMessage = await api.appendConversationMessage(conversationId, {
        role: 'USER', content: command, selected_file_ids: selected,
      })
      messages.value = [...messages.value, userMessage]
      const result = await api.prepareConversationNaming(conversationId, instruction, selected)
      planVersions.value = [...planVersions.value.filter(item => item.id !== result.plan_version.id), result.plan_version]
      viewingPlanVersion.value = result.plan_version
      messages.value = [...messages.value, result.assistant_message]
      context.value = await api.conversationContext(conversationId)
      selectedFileIds.value = []
      notice.value = `已为 ${result.metrics.affected_files} 个文件生成命名预览，请逐项核对后确认。`
      return true
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : String(cause)
      notice.value = ''
      return false
    } finally { refinementBusy.value = false }
  }

  async function prepareRefinement(content: string, confirmedGlobal = false, referencedFileIds: string[] = [], triggerMessageId?: string) {
    const conversationId = currentConversation.value?.id
    if (!conversationId || refinementBusy.value) return false
    refinementBusy.value = true
    error.value = ''
    notice.value = '正在核对当前文件状态和本轮影响范围…'
    try {
      const result = await api.prepareConversationRefinement(conversationId, {
        user_message: content, confirmed_global: confirmedGlobal,
        referenced_file_ids: referencedFileIds, trigger_message_id: triggerMessageId,
      })
      affectedScope.value = result.affected_scope
      refinementMetrics.value = result.metrics
      if (result.status === 'GLOBAL_REPLAN_CONFIRMATION_REQUIRED') {
        pendingGlobalMessage.value = content
        notice.value = '这项修改会重新规划整个整理目录，需要再次确认。'
        return true
      }
      pendingGlobalMessage.value = ''
      if (result.plan_version) {
        planVersions.value = [...planVersions.value.filter(item => item.id !== result.plan_version!.id), result.plan_version]
        viewingPlanVersion.value = result.plan_version
      }
      if (result.assistant_message && !messages.value.some(item => item.id === result.assistant_message!.id)) {
        messages.value = [...messages.value, result.assistant_message]
      }
      context.value = await api.conversationContext(conversationId)
      notice.value = '本轮调整方案已准备好，确认前不会移动文件。'
      return true
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : String(cause)
      notice.value = ''
      return false
    } finally { refinementBusy.value = false }
  }

  async function confirmGlobalRefinement() {
    if (!pendingGlobalMessage.value) return false
    return prepareRefinement(pendingGlobalMessage.value, true)
  }

  function cancelGlobalRefinement() {
    pendingGlobalMessage.value = ''
    affectedScope.value = null
    refinementMetrics.value = null
    notice.value = '已取消全局重新规划，磁盘文件没有变化。'
  }

  async function approveAndExecute(plan: ConversationPlanVersion) {
    const conversationId = currentConversation.value?.id
    if (!conversationId || !context.value || executionBusy.value || !plan.plan_hash) return false
    executionBusy.value = true
    error.value = ''
    const revision = context.value.context_revision
    try {
      await api.approveConversationPlanVersion(conversationId, plan.id, {
        expected_context_revision: revision, plan_hash: plan.plan_hash,
        authorization: { kind: 'interactive', surface: 'conversation_workspace' },
      })
      notice.value = '已批准方案，正在通过安全执行引擎处理…'
      await api.executeConversationRefinement(conversationId, plan.id, {
        expected_context_revision: revision, plan_hash: plan.plan_hash,
      })
      await loadConversation(conversationId)
      notice.value = '本轮调整完成。你可以继续告诉归序需要调整的地方。'
      return true
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : String(cause)
      return false
    } finally { executionBusy.value = false }
  }

  async function requestUndo(round?: ConversationExecutionRound) {
    const conversationId = currentConversation.value?.id
    if (!conversationId || undoBusy.value) return false
    undoBusy.value = true; error.value = ''
    try {
      const result = await api.requestConversationUndo(conversationId, {
        execution_round_id: round?.id, referenced_file_ids: selectedFileIds.value,
      })
      if (!result.undo_plan) { notice.value = result.query?.message || '没有可撤销的文件操作。'; return true }
      pendingUndoPlan.value = result.undo_plan
      undoPlans.value = [result.undo_plan, ...undoPlans.value.filter(item => item.id !== result.undo_plan!.id)]
      notice.value = result.undo_plan.status === 'BLOCKED' ? '撤销预览包含冲突，请先查看详情。' : '撤销预览已生成，确认前磁盘不会变化。'
      return true
    } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); return false }
    finally { undoBusy.value = false }
  }

  async function confirmUndo() {
    const conversationId = currentConversation.value?.id
    const plan = pendingUndoPlan.value
    if (!conversationId || !plan || undoBusy.value) return false
    undoBusy.value = true; error.value = ''
    try {
      await api.approveConversationUndo(conversationId, plan.id, plan.plan_hash)
      pendingUndoPlan.value = await api.executeConversationUndo(conversationId, plan.id, plan.plan_hash)
      await loadConversation(conversationId)
      notice.value = '撤销完成。会话和原执行记录仍然保留。'
      return true
    } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); return false }
    finally { undoBusy.value = false }
  }

  async function cancelUndo() {
    const conversationId = currentConversation.value?.id
    const plan = pendingUndoPlan.value
    if (!conversationId || !plan || undoBusy.value) return false
    undoBusy.value = true
    try {
      const cancelled = await api.cancelConversationUndo(conversationId, plan.id)
      undoPlans.value = undoPlans.value.map(item => item.id === cancelled.id ? cancelled : item)
      pendingUndoPlan.value = null; notice.value = '已取消撤销，磁盘文件没有变化。'; return true
    } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); return false }
    finally { undoBusy.value = false }
  }

  async function viewPlanVersion(id: string | null) {
    if (!id) {
      viewingPlanVersion.value = null
      planDiff.value = null
      return
    }
    versionLoading.value = true
    try {
      const version = planVersions.value.find(item => item.id === id) ?? await api.conversationPlanVersion(currentConversation.value!.id, id)
      viewingPlanVersion.value = version
      planDiff.value = version.parent_plan_version_id
        ? await api.conversationPlanDiff(currentConversation.value!.id, version.id, version.parent_plan_version_id)
        : null
    } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause) }
    finally { versionLoading.value = false }
  }

  async function restorePlanVersion(id: string) {
    if (!currentConversation.value || !context.value) return false
    versionLoading.value = true
    try {
      await api.restoreConversationPlanVersion(currentConversation.value.id, id, {
        expected_context_revision: context.value.context_revision,
        expected_current_plan_version_id: currentPlanVersion.value?.id,
      })
      await loadConversation(currentConversation.value.id)
      notice.value = '已基于历史方案创建新的方案版本。'
      return true
    } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); return false }
    finally { versionLoading.value = false }
  }

  function toggleFile(fileId: string) {
    if (!files.value.length && !selectedFileIds.value.includes(fileId) && selectedFileIds.value.length >= 3) {
      notice.value = '每次最多选择 3 张图片进行对话分析。'
      return
    }
    focusedFileId.value = fileId
    selectedFileIds.value = selectedFileIds.value.includes(fileId)
      ? selectedFileIds.value.filter(id => id !== fileId)
      : [...selectedFileIds.value, fileId]
  }

  function removeFileReference(fileId: string) { selectedFileIds.value = selectedFileIds.value.filter(id => id !== fileId) }
  function clearFileReferences() { selectedFileIds.value = []; focusedFileId.value = null }
  function selectReferencedFiles(fileIds: string[]) {
    const available = new Set(files.value.map(file => file.file_id))
    selectedFileIds.value = fileIds.filter(id => available.has(id))
    focusedFileId.value = selectedFileIds.value.length === 1 ? selectedFileIds.value[0] : null
  }

  return {
    conversations, currentConversation, messages, context, files, sourceFiles, sourceFilesTruncated, sourceInventoryRevision, planVersions, currentPlanVersion, viewingPlanVersion, planDiff, versionLoading, executionRounds, models,
    refinementBusy, executionBusy, affectedScope, refinementMetrics, pendingGlobalMessage,
    loading, loadingConversations, error, notice, selectedFileIds, focusedFileId, activeCategoryId, activeScope, activeModel, analysisBusy, chatBusy, recovery, recoveryBusy,
    undoPlans, pendingUndoPlan, undoBusy,
    clearError, clearNotice, loadConversations, loadConversation, loadModels, createConversation,
    renameConversation, setConversationModel, deleteConversation, appendMessage, startOrganization, prepareNaming, prepareRefinement, confirmGlobalRefinement, cancelGlobalRefinement, reconcileConversation, resumeAnalysis, retryAgentTurn,
    approveAndExecute, requestUndo, confirmUndo, cancelUndo, viewPlanVersion, restorePlanVersion, toggleFile, removeFileReference, clearFileReferences, selectReferencedFiles,
  }
})
