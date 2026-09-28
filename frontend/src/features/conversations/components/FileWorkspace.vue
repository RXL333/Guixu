<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Check, FileImage, FileText, Folder, Grid2X2, List, SlidersHorizontal, Video, X } from 'lucide-vue-next'
import { api, type ConversationExecutionRound, type ConversationFile, type ConversationPlanDiff, type ConversationPlanPreview, type ConversationPlanVersion } from '../../../services/api'
import { useConversationStore } from '../store'
import PlanPreviewCard from './PlanPreviewCard.vue'
import ExecutionResultCard from './ExecutionResultCard.vue'

const props = defineProps<{ plans: ConversationPlanVersion[]; executions: ConversationExecutionRound[]; currentPlanVersion?: ConversationPlanVersion | null; viewingPlanVersion?: ConversationPlanVersion | null; planDiff?: ConversationPlanDiff | null; versionLoading?: boolean; collapsed?: boolean }>()
const emit = defineEmits<{ collapse: []; expand: []; viewHistory: [id: string]; restoreVersion: [id: string]; approvePlan: [plan: ConversationPlanVersion]; undo: [round: ConversationExecutionRound] }>()
const store = useConversationStore()
const tab = ref<'files' | 'plans' | 'history'>('files')
const planPreview = ref<ConversationPlanPreview | null>(null)
const planPreviewBusy = ref(false)
const planPreviewError = ref('')
const suggestionSelection = ref<string[]>([])
const suggestionBusy = ref(false)
const confirmableSuggestions = computed(() => (planPreview.value?.operations || []).filter(item =>
  ['skip', 'noop'].includes(item.action) && Boolean(item.suggested_category_id) && !item.abstain,
))
const previewUrl = ref('')
const previewName = ref('')
const previewError = ref('')
const previewBusy = ref(false)
const previewCloseButton = ref<HTMLButtonElement | null>(null)
let previewReturnFocus: HTMLElement | null = null
const planQuery = ref('')
const planPage = ref(1)
const planPageSize = 50
const activePlan = computed(() => props.viewingPlanVersion || props.currentPlanVersion || props.plans.at(-1) || null)
const visibleOperations = computed(() => (planPreview.value?.operations || []).filter(item =>
  `${item.source_path} ${item.target_path || ''}`.toLowerCase().includes(planQuery.value.trim().toLowerCase()),
))
const planPageCount = computed(() => Math.max(1, Math.ceil(visibleOperations.value.length / planPageSize)))
const pagedOperations = computed(() => visibleOperations.value.slice((planPage.value - 1) * planPageSize, planPage.value * planPageSize))
watch([planQuery, () => activePlan.value?.id], () => { planPage.value = 1 })
watch([tab, () => activePlan.value?.id, () => store.currentConversation?.id], async () => {
  if (tab.value !== 'plans' || !activePlan.value || !store.currentConversation) return
  const planId = activePlan.value.id
  planPreview.value = null
  suggestionSelection.value = []
  planPreviewError.value = ''
  planPreviewBusy.value = true
  try { planPreview.value = await api.conversationPlanPreview(store.currentConversation.id, planId) }
  catch (cause) { planPreviewError.value = cause instanceof Error ? cause.message : String(cause) }
  finally { planPreviewBusy.value = false }
})
async function confirmSuggestions() {
  const conversationId = store.currentConversation?.id
  const planId = activePlan.value?.id
  const revision = store.context?.context_revision
  if (!conversationId || !planId || !revision || !suggestionSelection.value.length || suggestionBusy.value) return
  suggestionBusy.value = true
  planPreviewError.value = ''
  try {
    await api.confirmConversationSuggestions(conversationId, planId, {
      expected_context_revision: revision, file_ids: suggestionSelection.value,
    })
    await store.loadConversation(conversationId)
    store.notice = '已生成新的整理方案；请再次核对逐文件去向。'
  } catch (cause) { planPreviewError.value = cause instanceof Error ? cause.message : String(cause) }
  finally { suggestionBusy.value = false }
}
async function previewFile(file: ConversationFile, useSourcePath = false) {
  const conversationId = store.currentConversation?.id
  if (!conversationId || previewBusy.value) return
  previewBusy.value = true
  previewError.value = ''
  previewUrl.value = ''
  previewName.value = basename(file)
  previewReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  await nextTick()
  previewCloseButton.value?.focus()
  try {
    const ticket = await api.conversationPreviewTicket(conversationId,
      inventoryOnly.value || useSourcePath ? { source_path: file.current_known_path } : { file_id: file.file_id })
    previewUrl.value = ticket.url
  } catch (cause) { previewError.value = cause instanceof Error ? cause.message : String(cause) }
  finally { previewBusy.value = false }
}
function closePreview() {
  previewUrl.value = ''; previewError.value = ''; previewName.value = ''
  nextTick(() => { if (previewReturnFocus?.isConnected) previewReturnFocus.focus(); previewReturnFocus = null })
}
async function openCurrentDirectory() {
  const conversationId = store.currentConversation?.id
  if (!conversationId) return
  if (!window.pywebview?.api) { store.error = '请在归序桌面版中打开当前目录。'; return }
  try { await window.pywebview.api.open_conversation_directory(conversationId) }
  catch (cause) { store.error = cause instanceof Error ? cause.message : String(cause) }
}
function showTab(value: 'files' | 'plans' | 'history') { tab.value = value }
defineExpose({ showTab })
const query = ref('')
const sourceLoading = ref(false)
let sourceRequest = 0
watch([query, () => store.currentConversation?.id], ([term, id], previous, onCleanup) => {
  sourceRequest++
  sourceLoading.value = false
  if (!id || !inventoryOnly.value || (!term.trim() && !previous?.[0]?.trim())) return
  store.sourceInventoryRevision++
  const request = sourceRequest
  const timer = window.setTimeout(async () => {
    sourceLoading.value = true
    try {
      const inventory = await api.sourceFiles(id, { q: term.trim() })
      if (request !== sourceRequest || store.currentConversation?.id !== id) return
      store.sourceFiles = inventory.files
      store.sourceFilesTruncated = inventory.truncated
    } catch (cause) {
      if (request === sourceRequest) store.error = cause instanceof Error ? cause.message : String(cause)
    } finally { if (request === sourceRequest) sourceLoading.value = false }
  }, 250)
  onCleanup(() => window.clearTimeout(timer))
})
async function loadMoreSourceFiles() {
  const id = store.currentConversation?.id
  if (!id || sourceLoading.value || !store.sourceFilesTruncated) return
  const request = ++sourceRequest
  store.sourceInventoryRevision++
  sourceLoading.value = true
  try {
    const inventory = await api.sourceFiles(id, { offset: store.sourceFiles.length, q: query.value.trim() })
    if (request !== sourceRequest || store.currentConversation?.id !== id) return
    store.sourceFiles = [...store.sourceFiles, ...inventory.files]
    store.sourceFilesTruncated = inventory.truncated
  } catch (cause) { if (request === sourceRequest) store.error = cause instanceof Error ? cause.message : String(cause) }
  finally { if (request === sourceRequest) sourceLoading.value = false }
}
const view = ref<'list' | 'grid'>('list')
const panel = ref<HTMLElement | null>(null)
const scrollOffset = ref(0)
const columns = computed(() => view.value === 'grid' ? 2 : 1)
const rowHeight = computed(() => view.value === 'grid' ? 96 : 56)
const windowStart = computed(() => Math.max(0, Math.floor((scrollOffset.value - 160) / rowHeight.value) - 4) * columns.value)
const windowFiles = computed(() => filteredFiles.value.slice(windowStart.value, windowStart.value + 48))
const beforeHeight = computed(() => Math.floor(windowStart.value / columns.value) * rowHeight.value)
const afterHeight = computed(() => Math.ceil(Math.max(0, filteredFiles.value.length - windowStart.value - windowFiles.value.length) / columns.value) * rowHeight.value)
watch([query, view, () => store.currentConversation?.id], () => {
  scrollOffset.value = 0
  if (panel.value) panel.value.scrollTop = 0
})
const selectedIds = computed(() => new Set(store.selectedFileIds))
const inventoryOnly = computed(() => store.files.length === 0)
const displayFiles = computed<ConversationFile[]>(() => inventoryOnly.value ? store.sourceFiles.map(item => ({
  id: item.path, conversation_id: store.currentConversation?.id || '', file_id: item.path,
  first_seen_path: item.path, current_known_path: item.path,
  current_size_bytes: item.size_bytes, current_mtime_ns: item.mtime_ns,
  added_at: new Date(item.mtime_ns / 1_000_000).toISOString(), state: 'ACTIVE' as const,
})) : store.files)
function onPanelScroll(event: Event) { scrollOffset.value = (event.target as HTMLElement).scrollTop }

const filteredFiles = computed(() => displayFiles.value.filter(file => {
  const haystack = `${file.current_known_path} ${file.core_current_path || ''} ${file.file_id}`.toLowerCase()
  return haystack.includes(query.value.trim().toLowerCase())
}))
function basename(file: ConversationFile) { return (file.current_known_path || file.core_current_path || file.file_id).split(/[\\/]/).pop() || file.file_id }
function relativePath(file: ConversationFile) {
  const root = store.activeScope?.source_root
  const path = file.current_known_path || file.core_current_path || ''
  return root && path.toLowerCase().startsWith(root.toLowerCase()) ? path.slice(root.length).replace(/^[/\\]+/, '') || '当前目录' : path
}
function extension(file: ConversationFile) { return basename(file).split('.').pop()?.toLowerCase() || '' }
function isPreviewable(file: ConversationFile) { return ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'].includes(extension(file)) }
function previewPlanFile(fileId: string, sourcePath: string) {
  const file = store.files.find(item => item.file_id === fileId)
  if (file) return previewFile(file)
  return previewFile({ file_id: sourcePath, current_known_path: sourcePath } as ConversationFile, true)
}
function FileIcon(file: ConversationFile) {
  const ext = extension(file)
  if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic'].includes(ext)) return FileImage
  if (['mp4', 'mov', 'avi', 'mkv'].includes(ext)) return Video
  return FileText
}
function size(file: ConversationFile) {
  const bytes = file.current_size_bytes ?? file.core_size_bytes ?? 0
  if (bytes === 0) return '—'
  if (bytes > 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  if (bytes > 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}
function statusLabel(file: ConversationFile) { return file.state === 'FILE_CHANGED' ? '内容已变化' : file.state === 'MISSING' ? '文件不可见' : '' }
function fileChangeLabel(type: string) {
  return ({ ADDED: '新增', REMOVED: '移除', TARGET_CHANGED: '目标变化', KEEP_CHANGED: '保留状态变化', CONFLICT_CHANGED: '冲突变化' } as Record<string, string>)[type] || type
}
</script>

<template>
  <aside v-if="!collapsed" class="file-workspace" aria-label="文件工作区">
    <div class="file-tabs" role="tablist" aria-label="文件工作区视图">
      <button type="button" role="tab" :aria-selected="tab === 'files'" :class="{ active: tab === 'files' }" @click="tab = 'files'"><List :size="16" />当前文件</button>
      <button type="button" role="tab" :aria-selected="tab === 'plans'" :class="{ active: tab === 'plans' }" @click="tab = 'plans'"><SlidersHorizontal :size="16" />整理预览</button>
      <button type="button" role="tab" :aria-selected="tab === 'history'" :class="{ active: tab === 'history' }" @click="tab = 'history'"><List :size="16" />变更记录</button>
    </div>

    <section v-if="tab === 'files'" ref="panel" class="file-panel-body" @scroll="onPanelScroll">
      <div class="file-panel-heading"><h2>当前目录的文件 <span>({{ displayFiles.length }}{{ store.sourceFilesTruncated && inventoryOnly ? '+' : '' }})</span></h2><button type="button" class="panel-icon-button" aria-label="收起文件区" @click="emit('collapse')"><X :size="17" /></button></div>
      <div v-if="inventoryOnly && displayFiles.length" class="historical-plan-banner">可选择最多 3 张图片先和 AI 讨论内容；生成方案前不会移动文件。</div>
      <div class="file-toolbar"><label class="file-search"><span class="sr-only">搜索文件</span><input v-model="query" type="search" placeholder="搜索文件…" /></label><div class="view-switch" role="group" aria-label="文件显示方式"><button type="button" :class="{ active: view === 'list' }" aria-label="列表视图" @click="view = 'list'"><List :size="17" /></button><button type="button" :class="{ active: view === 'grid' }" aria-label="网格视图" @click="view = 'grid'"><Grid2X2 :size="17" /></button></div></div>
      <div v-if="!filteredFiles.length" class="file-empty"><FileText :size="22" /><strong>{{ sourceLoading ? '正在搜索文件…' : displayFiles.length ? '没有匹配的文件' : '当前目录没有可显示的文件' }}</strong><p>检查所选目录，或生成整理方案后重试。</p></div>
      <div v-else class="file-list" :class="{ 'grid-view': view === 'grid' }">
        <div v-if="beforeHeight" aria-hidden="true" class="file-spacer" :style="{ height: `${beforeHeight}px` }" />
        <div v-for="file in windowFiles" :key="file.file_id" class="file-item-wrap">
        <button type="button" class="file-item" :class="{ selected: selectedIds.has(file.file_id) }" :aria-pressed="selectedIds.has(file.file_id)" :title="file.current_known_path" :disabled="inventoryOnly && !isPreviewable(file)" @click="store.toggleFile(file.file_id)">
          <span class="file-icon"><Check v-if="selectedIds.has(file.file_id)" :size="18" /><component v-else :is="FileIcon(file)" :size="18" /></span>
          <span class="file-copy"><strong>{{ basename(file) }}</strong><small>{{ relativePath(file) }}</small></span>
          <span class="file-meta"><small>{{ new Date(file.current_mtime_ns ? file.current_mtime_ns / 1_000_000 : file.added_at).toLocaleDateString('zh-CN') }}</small><small>{{ size(file) }}</small></span>
          <span v-if="statusLabel(file)" class="file-state" :data-state="file.state">{{ statusLabel(file) }}</span>
          <span v-else class="file-location"><Folder :size="14" />{{ relativePath(file).split(/[\\/]/)[0] || '当前目录' }}</span>
        </button>
        <button v-if="isPreviewable(file)" type="button" class="file-preview-shortcut" aria-label="预览图片" :title="`预览 ${basename(file)}`" @click="previewFile(file)">预览</button>
        </div>
        <div v-if="afterHeight" aria-hidden="true" class="file-spacer" :style="{ height: `${afterHeight}px` }" />
      </div>
      <button v-if="inventoryOnly && store.sourceFilesTruncated" type="button" class="source-load-more" :disabled="sourceLoading" @click="loadMoreSourceFiles">{{ sourceLoading ? '正在加载…' : '加载更多文件' }}</button>
    </section>

    <section v-else-if="tab === 'plans'" class="file-panel-body alternate-panel">
      <div class="file-panel-heading"><h2>{{ props.viewingPlanVersion && props.viewingPlanVersion.id !== props.currentPlanVersion?.id ? `历史方案预览 · v${props.viewingPlanVersion.version_number}` : `整理预览${props.currentPlanVersion ? ` · v${props.currentPlanVersion.version_number}` : ''}` }}</h2><button type="button" class="panel-icon-button" aria-label="收起文件区" @click="emit('collapse')"><X :size="17" /></button></div>
      <div v-if="props.viewingPlanVersion && props.viewingPlanVersion.id !== props.currentPlanVersion?.id" class="historical-plan-banner">这是历史方案，不代表当前整理状态。</div>
      <div v-if="store.affectedScope" class="affected-scope-panel">
        <strong>本轮影响范围 · {{ ({ LOCAL: '局部调整', PARTIAL: '选中文件', GLOBAL: '整个目录' } as Record<string, string>)[store.affectedScope.scope_type] || '选定范围' }}</strong>
        <span>{{ store.refinementMetrics?.affected_files || store.affectedScope.candidate_file_ids.length }} 个候选文件</span>
        <span v-if="store.refinementMetrics?.delta_plan_count">其中 {{ store.refinementMetrics.delta_plan_count }} 个建议调整</span>
      </div>
      <div v-if="!props.plans.length" class="file-empty"><SlidersHorizontal :size="22" /><strong>还没有整理方案</strong><p>AI 生成整理方案后，会在这里预览新的目录结构。</p></div>
      <template v-else>
        <div v-if="props.currentPlanVersion?.status === 'EXECUTED' && (!props.viewingPlanVersion || props.viewingPlanVersion.id === props.currentPlanVersion.id)" class="historical-plan-banner current-clean">当前没有待执行的调整。</div>
        <details class="version-history"><summary>方案版本历史 · {{ props.plans.length }} 个版本</summary><div class="version-switcher" aria-label="方案版本历史">
          <button v-for="plan in props.plans" :key="plan.id" type="button" :class="{ active: plan.id === (props.viewingPlanVersion?.id || props.currentPlanVersion?.id) }" @click="emit('viewHistory', plan.id)">v{{ plan.version_number }}<small v-if="plan.id === props.currentPlanVersion?.id">当前</small></button>
        </div></details>
        <div v-if="props.viewingPlanVersion" class="business-card-stack">
          <PlanPreviewCard :plan="props.viewingPlanVersion" :current="props.viewingPlanVersion.id === props.currentPlanVersion?.id" :viewing="true" :execution-busy="store.executionBusy" @view-history="emit('viewHistory', $event)" @approve="emit('approvePlan', $event)" />
          <div v-if="props.planDiff" class="plan-diff-panel">
            <h3>这一轮改了什么</h3>
            <p>{{ props.planDiff.summary_counts.target_changed || 0 }} 个文件调整目标，{{ props.planDiff.summary_counts.unchanged || 0 }} 个文件保持不变。</p>
            <div v-if="props.planDiff.categories_added.length" class="diff-line"><strong>新增分类</strong><span v-for="category in props.planDiff.categories_added" :key="String(category.category_id || category.id)">+ {{ category.name || category.label }}</span></div>
            <div v-if="props.planDiff.categories_removed.length" class="diff-line"><strong>删除分类</strong><span v-for="category in props.planDiff.categories_removed" :key="String(category.category_id || category.id)">− {{ category.name || category.label }}</span></div>
            <div v-if="props.planDiff.file_changes.some(change => change.change_type !== 'UNCHANGED')" class="diff-line"><strong>文件调整</strong><span>{{ props.planDiff.affected_file_ids.length }} 个文件 · {{ props.planDiff.file_changes.filter(change => change.change_type !== 'UNCHANGED').slice(0, 4).map(change => `${change.file_id.slice(0, 8)} ${fileChangeLabel(change.change_type)}`).join('、') }}</span></div>
          </div>
          <button v-if="props.viewingPlanVersion.id !== props.currentPlanVersion?.id" class="restore-version-button" type="button" :disabled="props.versionLoading" @click="emit('restoreVersion', props.viewingPlanVersion.id)">{{ props.versionLoading ? '正在验证…' : '恢复为新方案' }}</button>
        </div>
        <div v-else class="business-card-stack"><PlanPreviewCard v-for="plan in props.plans" :key="plan.id" :plan="plan" :current="plan.id === props.currentPlanVersion?.id" :execution-busy="store.executionBusy" @view-history="emit('viewHistory', $event)" @approve="emit('approvePlan', $event)" /></div>
        <section v-if="activePlan" class="plan-file-mappings" aria-label="逐文件整理方案">
          <h3>逐文件去向 <span v-if="planPreview">({{ planPreview.operations.length }})</span></h3>
          <p>核对每个文件的原位置和目标位置，再决定是否执行。</p>
          <input v-model="planQuery" type="search" aria-label="搜索方案文件" placeholder="搜索文件名或目标文件夹…" />
          <p v-if="planPreviewBusy">正在读取逐文件方案…</p>
          <p v-else-if="planPreviewError" role="alert">{{ planPreviewError }}</p>
          <p v-else-if="planPreview && !planPreview.operations.length">此方案没有文件操作。</p>
          <p v-else-if="!visibleOperations.length">没有匹配的文件。</p>
          <div v-else class="plan-file-list">
          <div v-if="confirmableSuggestions.length && activePlan.id === props.currentPlanVersion?.id && activePlan.status === 'PROPOSED'" class="affected-scope-panel">
            <strong>{{ confirmableSuggestions.length }} 个文件有待确认的 AI 分类建议</strong>
            <span>请预览图片并逐项核对。勾选只表示接受分类建议；仍需核对新方案并单独确认执行。</span>
            <button type="button" :disabled="!suggestionSelection.length || suggestionBusy" @click="confirmSuggestions">{{ suggestionBusy ? '正在生成方案…' : `确认选中的 ${suggestionSelection.length} 项并生成新方案` }}</button>
          </div>
            <div v-if="planPageCount > 1" class="plan-pagination" role="group" aria-label="方案文件分页">
              <button type="button" :disabled="planPage === 1" @click="planPage--">上一页</button>
              <span>第 {{ planPage }} / {{ planPageCount }} 页 · 匹配 {{ visibleOperations.length }} 项</span>
              <button type="button" :disabled="planPage === planPageCount" @click="planPage++">下一页</button>
            </div>
            <article v-for="operation in pagedOperations" :key="operation.file_id" class="plan-file-row">
              <div class="plan-file-row-heading"><strong>{{ operation.source_path.split(/[\\/]/).pop() }}</strong><button v-if="['jpg','jpeg','png','gif','webp','bmp'].includes(operation.source_path.split('.').pop()?.toLowerCase() || '')" type="button" @click="previewPlanFile(operation.file_id, operation.source_path)">预览图片</button></div>
              <small>原位置：{{ operation.source_path }}</small>
              <small v-if="operation.target_path && ['move', 'copy'].includes(operation.action)">{{ operation.action === 'copy' ? '复制到' : operation.source_path.replace(/[\\/][^\\/]+$/, '') === operation.target_path.replace(/[\\/][^\\/]+$/, '') ? '重命名为' : '移动到' }}：{{ operation.target_path }}</small>
              <small v-else>保持原位{{ operation.reason ? ` · ${operation.reason}` : '' }}</small>
              <small v-if="operation.suggested_category_path?.length">AI 建议：{{ operation.suggested_category_path.join(' / ') }} · {{ ({ high: '较高', medium: '中等', low: '较低' } as Record<string,string>)[operation.review_band || ''] || '待核对' }}置信度</small>
              <small v-if="operation.classification_reason">依据：{{ operation.classification_reason }}</small>
              <label v-if="['skip', 'noop'].includes(operation.action) && operation.suggested_category_id && !operation.abstain && activePlan.id === props.currentPlanVersion?.id && activePlan.status === 'PROPOSED'">
                <input v-model="suggestionSelection" type="checkbox" :value="operation.file_id" /> 我已核对图片，同意此分类建议
              </label>
            </article>
          </div>
        </section>
      </template>
    </section>

    <section v-else class="file-panel-body alternate-panel">
      <div class="file-panel-heading"><h2>变更记录</h2><button type="button" class="panel-icon-button" aria-label="收起文件区" @click="emit('collapse')"><X :size="17" /></button></div>
      <div v-if="!props.executions.length" class="file-empty"><List :size="22" /><strong>还没有执行记录</strong><p>执行后的整理记录会显示在这里。</p></div>
      <div v-else class="business-card-stack"><ExecutionResultCard v-for="round in props.executions" :key="round.id" :round="round" :undo-busy="store.undoBusy" @undo="emit('undo', $event)" /></div>
    </section>

    <footer class="file-panel-footer"><span>已选择 {{ store.selectedFileIds.length }} 个文件</span><button type="button" class="open-folder-button" :disabled="!store.activeScope" @click="openCurrentDirectory"><Folder :size="15" />打开当前目录</button></footer>
  </aside>
  <button v-else type="button" class="file-panel-expand" aria-label="展开文件区" @click="emit('expand')"><Folder :size="18" /></button>
  <div v-if="previewName" class="image-preview-backdrop" role="presentation" @click.self="closePreview">
    <section class="image-preview-dialog" role="dialog" aria-modal="true" :aria-label="`预览 ${previewName}`" @keydown.esc.stop.prevent="closePreview">
      <header><strong>{{ previewName }}</strong><button ref="previewCloseButton" type="button" aria-label="关闭图片预览" @click="closePreview"><X :size="20" /></button></header>
      <p v-if="previewBusy">正在加载图片…</p>
      <p v-else-if="previewError" role="alert">{{ previewError }}</p>
      <img v-else-if="previewUrl" :src="previewUrl" :alt="previewName" @error="previewError = '图片解码失败或票据已过期，请重新打开预览。'" />
    </section>
  </div>
</template>
