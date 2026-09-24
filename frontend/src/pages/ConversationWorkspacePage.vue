<script setup lang="ts">
import { Bot, Check, FolderOpen, MessageSquare, RefreshCw } from 'lucide-vue-next'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { chooseSource } from '../services/api'
import ConversationHeader from '../features/conversations/components/ConversationHeader.vue'
import ConversationMessage from '../features/conversations/components/ConversationMessage.vue'
import ChatComposer from '../features/conversations/components/ChatComposer.vue'
import FileWorkspace from '../features/conversations/components/FileWorkspace.vue'
import WorkspaceStatusBar from '../features/conversations/components/WorkspaceStatusBar.vue'
import PlanPreviewCard from '../features/conversations/components/PlanPreviewCard.vue'
import ExecutionResultCard from '../features/conversations/components/ExecutionResultCard.vue'
import UndoPreviewCard from '../features/conversations/components/UndoPreviewCard.vue'
import OperationProgress from '../features/conversations/components/OperationProgress.vue'
import { useConversationStore } from '../features/conversations/store'

const route = useRoute()
const router = useRouter()
const store = useConversationStore()
const composer = ref<InstanceType<typeof ChatComposer> | null>(null)
const narrowWindow = window.matchMedia?.('(max-width: 1100px)') ?? { matches: false, addEventListener: undefined, removeEventListener: undefined }
const filePanelCollapsed = ref(narrowWindow.matches)
const fileWorkspace = ref<InstanceType<typeof FileWorkspace> | null>(null)
const messageLimit = ref(80)
const visibleMessages = computed(() => store.messages.slice(-messageLimit.value))
function adaptPanels(event: MediaQueryListEvent) { if (event.matches) filePanelCollapsed.value = true }
onMounted(() => narrowWindow.addEventListener?.('change', adaptPanels))
onUnmounted(() => narrowWindow.removeEventListener?.('change', adaptPanels))
async function showPlan(id: string) {
  filePanelCollapsed.value = false
  await nextTick()
  fileWorkspace.value?.showTab('plans')
  await store.viewPlanVersion(id)
}
async function showFiles(ids?: string[]) {
  if (ids) store.selectReferencedFiles(ids)
  filePanelCollapsed.value = false
  await nextTick()
  fileWorkspace.value?.showTab('files')
}
async function showHistory() {
  filePanelCollapsed.value = false
  await nextTick()
  fileWorkspace.value?.showTab('history')
}
const pendingPrompt = ref('')
const folderBusy = ref(false)
const examples = ['按照文件内容整理，不要分得太细。', '这些是大学资料，按课程整理。', '这些是照片，按照内容和场景整理。']

async function loadForRoute() {
  if (import.meta.env.DEV && route.path === '/__ui-review') return
  const id = typeof route.params.id === 'string' ? route.params.id : ''
  if (id) {
    await store.loadConversation(id)
    return
  }
  await store.loadConversations()
  if (store.conversations.length) await router.replace(`/conversations/${store.conversations[0].id}`)
}
async function chooseFolder() {
  if (folderBusy.value) return
  folderBusy.value = true
  store.clearError()
  try {
    const grant = await chooseSource()
    if (grant.cancelled || !grant.grant_id) return
    const conversation = await store.createConversation(grant.grant_id)
    if (!conversation) return
    await router.replace(`/conversations/${conversation.id}`)
    await nextTick()
    if (pendingPrompt.value) { composer.value?.fill(pendingPrompt.value); pendingPrompt.value = '' }
  } finally { folderBusy.value = false }
}
function useExample(prompt: string) {
  pendingPrompt.value = prompt
  if (store.currentConversation) composer.value?.fill(prompt)
  else store.notice = '选择文件夹后，这条整理要求会填入输入框。'
}
function statusText() {
  if (store.analysisBusy) return '正在扫描文件、分析内容并生成整理预览…'
  if (store.executionBusy) return '正在整理文件…'
  if (store.refinementBusy) return `正在检查${store.affectedScope?.affected_category_ids?.length ? '本轮影响范围' : '当前文件状态'}…`
  if (store.notice) return store.notice
  if (store.loading) return '正在读取会话状态…'
  if (store.currentConversation && !store.messages.length) return '已准备好记录你的整理要求。'
  return '消息、方案和执行记录都会保存在当前会话中。'
}
function statusTone(): 'idle' | 'loading' | 'success' | 'error' {
  if (store.error) return 'error'
  if (store.loading || store.analysisBusy || store.refinementBusy || store.executionBusy) return 'loading'
  if (store.notice) return 'success'
  return 'idle'
}
onMounted(loadForRoute)
watch(() => route.params.id, loadForRoute)
</script>

<template>
  <section class="conversation-workspace-page" :class="{ 'files-collapsed': filePanelCollapsed }">
    <main class="chat-workspace" :class="{ 'file-collapsed': filePanelCollapsed }">
      <ConversationHeader :conversation="store.currentConversation" />
      <div v-if="store.error" class="workspace-error" role="alert"><RefreshCw :size="17" /><span>{{ store.error }}</span><button type="button" @click="loadForRoute">重新加载</button></div>
      <section v-if="store.recovery?.reconciliation?.requires_user_action" class="recovery-banner" role="status">
        <div class="recovery-banner-icon"><RefreshCw :size="17" /></div>
        <div class="recovery-banner-copy">
          <strong v-if="store.recovery.reconciliation.scope_status !== 'AVAILABLE'">当前目录暂时不可用</strong>
          <strong v-else>归序发现了目录变化，需要同步后继续</strong>
          <span v-if="store.recovery.reconciliation.scope_status !== 'AVAILABLE'">历史消息和方案仍可查看；重新授权后才能继续文件操作。</span>
          <span v-else>新增 {{ store.recovery.reconciliation.new_files }} · 移动 {{ store.recovery.reconciliation.moved }} · 重命名 {{ store.recovery.reconciliation.renamed }} · 修改 {{ store.recovery.reconciliation.modified }} · 缺失 {{ store.recovery.reconciliation.missing }}</span>
        </div>
        <button v-if="store.recovery.reconciliation.scope_status === 'AVAILABLE'" type="button" :disabled="store.recoveryBusy" @click="store.reconcileConversation">同步状态</button>
      </section>
      <section v-if="store.recovery?.agent_turns?.some(turn => turn.status === 'INTERRUPTED')" class="recovery-card" role="alert">
        <div>
          <strong>上一次分析在应用关闭时中断</strong>
          <span>已保存的文件内容分析会继续复用，不会自动重放旧模型请求。</span>
        </div>
        <button type="button" :disabled="store.recoveryBusy" @click="store.resumeAnalysis">继续分析</button>
      </section>
      <section v-if="store.recovery?.agent_turns?.some(turn => turn.status === 'INTERRUPTED' && turn.turn_kind === 'EXECUTION')" class="recovery-card recovery-card-danger" role="alert">
        <div><strong>上一次文件整理未完整结束</strong><span>请先检查当前磁盘状态和操作日志，系统不会重复执行全部文件。</span></div>
        <button type="button" @click="store.reconcileConversation">检查当前状态</button>
      </section>
      <div class="message-scroll-area">
        <div v-if="store.loading && !store.currentConversation" class="workspace-loading"><span class="loading-spinner" /><p>正在打开会话…</p></div>
        <template v-else-if="store.currentConversation">
          <div v-if="!store.messages.length" class="conversation-empty-state">
            <div class="empty-state-icon"><Bot :size="22" /></div>
            <h2>告诉归序，你希望怎样整理这个文件夹。</h2>
            <p>描述你的整理要求。文件移动前，你可以先查看并确认方案。</p>
          </div>
          <div v-else class="message-list" aria-live="polite">
            <div class="message-date-label">当前会话</div>
          <button v-if="store.messages.length > messageLimit" class="text-button" type="button" @click="messageLimit += 80">显示更早的消息</button>
          <ConversationMessage v-for="message in visibleMessages" :key="message.id" :message="message" @references="showFiles" />
            <div v-if="store.pendingGlobalMessage" class="global-replan-warning" role="alert">
              <strong>这个修改会重新规划整个整理目录</strong>
              <p>当前范围 {{ store.refinementMetrics?.total_scope_files || store.files.length }} 个文件；已有内容分析会优先复用。是否继续？</p>
              <div><button type="button" :disabled="store.refinementBusy" @click="store.confirmGlobalRefinement">继续重新规划</button><button type="button" @click="store.cancelGlobalRefinement">取消</button></div>
            </div>
            <PlanPreviewCard v-for="plan in store.planVersions" :key="`plan-${plan.id}`" :plan="plan" :current="plan.id === store.currentPlanVersion?.id" :execution-busy="store.executionBusy" @view-history="showPlan" @approve="store.approveAndExecute" />
            <UndoPreviewCard v-if="store.pendingUndoPlan" :plan="store.pendingUndoPlan" :busy="store.undoBusy" @confirm="store.confirmUndo" @cancel="store.cancelUndo" />
            <ExecutionResultCard v-for="round in store.executionRounds" :key="`round-${round.id}`" :round="round" :undo-busy="store.undoBusy" @undo="store.requestUndo" @view-history="showHistory" />
          </div>
        </template>
        <div v-else class="workspace-empty-state">
          <div class="empty-state-icon"><MessageSquare :size="24" /></div>
          <h2>归序</h2>
          <p>选择一个文件夹，告诉归序你希望怎样整理。归序只会处理你授权的目录。</p>
          <button class="primary-action" type="button" :disabled="folderBusy" @click="chooseFolder"><FolderOpen :size="17" />{{ folderBusy ? '正在选择…' : '选择文件夹' }}</button>
          <div class="prompt-suggestions" aria-label="整理要求示例">
            <button v-for="prompt in examples" :key="prompt" type="button" @click="useExample(prompt)"><span>{{ prompt }}</span><Check :size="15" /></button>
          </div>
        </div>
      </div>
      <div class="chat-footer">
        <OperationProgress v-if="store.analysisBusy || store.refinementBusy || store.executionBusy || store.undoBusy" :label="store.analysisBusy ? '正在扫描文件并生成整理预览' : store.undoBusy ? '正在核对并恢复文件' : store.executionBusy ? '正在整理文件' : '正在检查文件内容与整理要求'" />
        <WorkspaceStatusBar :tone="statusTone()" :text="statusText()" />
        <ChatComposer ref="composer" @references="showFiles()" :disabled="!store.currentConversation || !!store.error || store.analysisBusy || store.refinementBusy || store.executionBusy || store.undoBusy" />
      </div>
    </main>
    <FileWorkspace ref="fileWorkspace" :plans="store.planVersions" :executions="store.executionRounds" :current-plan-version="store.currentPlanVersion" :viewing-plan-version="store.viewingPlanVersion" :plan-diff="store.planDiff" :version-loading="store.versionLoading" :collapsed="filePanelCollapsed" @collapse="filePanelCollapsed = true" @expand="filePanelCollapsed = false" @view-history="store.viewPlanVersion" @restore-version="store.restorePlanVersion" @approve-plan="store.approveAndExecute" @undo="store.requestUndo" />
  </section>
</template>
