<script setup lang="ts">
import { Bot, Check, FolderOpen, MessageSquare, RefreshCw } from 'lucide-vue-next'
import { nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { chooseSource } from '../services/api'
import ConversationHeader from '../features/conversations/components/ConversationHeader.vue'
import ConversationMessage from '../features/conversations/components/ConversationMessage.vue'
import ChatComposer from '../features/conversations/components/ChatComposer.vue'
import FileWorkspace from '../features/conversations/components/FileWorkspace.vue'
import WorkspaceStatusBar from '../features/conversations/components/WorkspaceStatusBar.vue'
import PlanPreviewCard from '../features/conversations/components/PlanPreviewCard.vue'
import ExecutionResultCard from '../features/conversations/components/ExecutionResultCard.vue'
import { useConversationStore } from '../features/conversations/store'

const route = useRoute()
const router = useRouter()
const store = useConversationStore()
const composer = ref<InstanceType<typeof ChatComposer> | null>(null)
const filePanelCollapsed = ref(false)
const pendingPrompt = ref('')
const folderBusy = ref(false)
const examples = ['按照文件内容整理，不要分得太细。', '这些是大学资料，按课程整理。', '这些是照片，按照内容和场景整理。']

async function loadForRoute() {
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
  if (store.executionBusy) return '正在通过安全执行引擎处理本轮调整…'
  if (store.refinementBusy) return `正在检查${store.affectedScope?.affected_category_ids?.length ? '本轮影响范围' : '当前文件状态'}…`
  if (store.notice) return store.notice
  if (store.loading) return '正在读取会话状态…'
  if (store.currentConversation && !store.messages.length) return '已准备好记录你的整理要求。'
  return '消息、方案和执行记录都会保存在当前会话中。'
}
function statusTone(): 'idle' | 'loading' | 'success' | 'error' {
  if (store.error) return 'error'
  if (store.loading || store.refinementBusy || store.executionBusy) return 'loading'
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
      <div class="message-scroll-area">
        <div v-if="store.loading && !store.currentConversation" class="workspace-loading"><span class="loading-spinner" /><p>正在打开会话…</p></div>
        <template v-else-if="store.currentConversation">
          <div v-if="!store.messages.length" class="conversation-empty-state">
            <div class="empty-state-icon"><Bot :size="22" /></div>
            <h2>对话式 AI 整理能力将在下一阶段接入</h2>
            <p>你的消息会先安全保存。下一阶段将接入文件内容分析、整理方案生成、执行预览和确认。</p>
          </div>
          <div v-else class="message-list" aria-live="polite">
            <div class="message-date-label">当前会话</div>
            <ConversationMessage v-for="message in store.messages" :key="message.id" :message="message" />
            <div v-if="store.pendingGlobalMessage" class="global-replan-warning" role="alert">
              <strong>这个修改会重新规划整个整理目录</strong>
              <p>当前范围 {{ store.refinementMetrics?.total_scope_files || store.files.length }} 个文件；已有内容分析会优先复用。是否继续？</p>
              <div><button type="button" :disabled="store.refinementBusy" @click="store.confirmGlobalRefinement">继续重新规划</button><button type="button" @click="store.cancelGlobalRefinement">取消</button></div>
            </div>
            <PlanPreviewCard v-for="plan in store.planVersions" :key="`plan-${plan.id}`" :plan="plan" :current="plan.id === store.currentPlanVersion?.id" :execution-busy="store.executionBusy" @view-history="store.viewPlanVersion" @approve="store.approveAndExecute" />
            <ExecutionResultCard v-for="round in store.executionRounds" :key="`round-${round.id}`" :round="round" />
          </div>
        </template>
        <div v-else class="workspace-empty-state">
          <div class="empty-state-icon"><MessageSquare :size="24" /></div>
          <h2>选择一个文件夹，然后告诉我你想怎么整理。</h2>
          <p>先建立一个长期整理会话；消息会被持久化，真正的 AI 整理能力将在下一阶段接入。</p>
          <button class="primary-action" type="button" :disabled="folderBusy" @click="chooseFolder"><FolderOpen :size="17" />{{ folderBusy ? '正在选择…' : '选择文件夹' }}</button>
          <div class="prompt-suggestions" aria-label="整理要求示例">
            <button v-for="prompt in examples" :key="prompt" type="button" @click="useExample(prompt)"><span>{{ prompt }}</span><Check :size="15" /></button>
          </div>
        </div>
      </div>
      <div class="chat-footer">
        <WorkspaceStatusBar :tone="statusTone()" :text="statusText()" />
        <ChatComposer ref="composer" :disabled="!store.currentConversation || !!store.error || store.refinementBusy || store.executionBusy" />
      </div>
    </main>
    <FileWorkspace :plans="store.planVersions" :executions="store.executionRounds" :current-plan-version="store.currentPlanVersion" :viewing-plan-version="store.viewingPlanVersion" :plan-diff="store.planDiff" :version-loading="store.versionLoading" :collapsed="filePanelCollapsed" @collapse="filePanelCollapsed = true" @expand="filePanelCollapsed = false" @view-history="store.viewPlanVersion" @restore-version="store.restorePlanVersion" @approve-plan="store.approveAndExecute" />
  </section>
</template>
