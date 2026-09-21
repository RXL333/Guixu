import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api, type AffectedScope, type Conversation, type ConversationContext, type ConversationExecutionRound, type ConversationFile, type ConversationMessage, type ConversationPlanDiff, type ConversationPlanVersion, type ModelProfile, type RefinementMetrics } from '../../services/api'

export const useConversationStore = defineStore('conversations', () => {
  const conversations = ref<Conversation[]>([])
  const currentConversation = ref<Conversation | null>(null)
  const messages = ref<ConversationMessage[]>([])
  const context = ref<ConversationContext | null>(null)
  const files = ref<ConversationFile[]>([])
  const planVersions = ref<ConversationPlanVersion[]>([])
  const viewingPlanVersion = ref<ConversationPlanVersion | null>(null)
  const planDiff = ref<ConversationPlanDiff | null>(null)
  const versionLoading = ref(false)
  const refinementBusy = ref(false)
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
    try { models.value = await api.models() } catch { models.value = [] }
  }

  async function loadConversation(id: string) {
    loading.value = true
    error.value = ''
    notice.value = ''
    try {
      const [conversation, nextMessages, nextContext, nextFiles, nextPlans, nextExecutions] = await Promise.all([
        api.conversation(id),
        api.conversationMessages(id),
        api.conversationContext(id),
        api.conversationFiles(id),
        api.conversationPlans(id),
        api.conversationExecutions(id),
      ])
      currentConversation.value = conversation
      messages.value = nextMessages
      context.value = nextContext
      files.value = nextFiles
      planVersions.value = nextPlans
      viewingPlanVersion.value = null
      planDiff.value = null
      executionRounds.value = nextExecutions
      affectedScope.value = null
      refinementMetrics.value = null
      pendingGlobalMessage.value = ''
      selectedFileIds.value = []
      if (!models.value.length) await loadModels()
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : String(cause)
      currentConversation.value = null
      messages.value = []
      context.value = null
      files.value = []
      planVersions.value = []
      executionRounds.value = []
    } finally {
      loading.value = false
    }
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
    if (!conversationId || !content.trim()) return false
    try {
      const message = await api.appendConversationMessage(conversationId, { role: 'USER', content: content.trim() })
      messages.value = [...messages.value, message]
      if (executionRounds.value.some(round => round.status === 'COMPLETED')) {
        await prepareRefinement(content.trim())
      } else {
        notice.value = '消息已保存。首次整理分析能力尚未接入当前工作区。'
      }
      currentConversation.value = { ...currentConversation.value!, last_message_at: message.created_at, updated_at: message.created_at }
      conversations.value = conversations.value.map(item => item.id === conversationId ? { ...item, last_message_at: message.created_at, updated_at: message.created_at } : item)
      return true
    } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); return false }
  }

  async function prepareRefinement(content: string, confirmedGlobal = false) {
    const conversationId = currentConversation.value?.id
    if (!conversationId || refinementBusy.value) return false
    refinementBusy.value = true
    error.value = ''
    notice.value = '正在核对当前文件状态和本轮影响范围…'
    try {
      const result = await api.prepareConversationRefinement(conversationId, { user_message: content, confirmed_global: confirmedGlobal })
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
    selectedFileIds.value = selectedFileIds.value.includes(fileId)
      ? selectedFileIds.value.filter(id => id !== fileId)
      : [...selectedFileIds.value, fileId]
  }

  return {
    conversations, currentConversation, messages, context, files, planVersions, currentPlanVersion, viewingPlanVersion, planDiff, versionLoading, executionRounds, models,
    refinementBusy, executionBusy, affectedScope, refinementMetrics, pendingGlobalMessage,
    loading, loadingConversations, error, notice, selectedFileIds, activeScope, activeModel,
    clearError, clearNotice, loadConversations, loadConversation, loadModels, createConversation,
    renameConversation, deleteConversation, appendMessage, prepareRefinement, confirmGlobalRefinement, cancelGlobalRefinement,
    approveAndExecute, viewPlanVersion, restorePlanVersion, toggleFile,
  }
})
