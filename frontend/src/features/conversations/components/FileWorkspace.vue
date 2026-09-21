<script setup lang="ts">
import { computed, ref } from 'vue'
import { FileImage, FileText, Folder, Grid2X2, List, SlidersHorizontal, Video, X } from 'lucide-vue-next'
import type { ConversationExecutionRound, ConversationFile, ConversationPlanDiff, ConversationPlanVersion } from '../../../services/api'
import { useConversationStore } from '../store'
import PlanPreviewCard from './PlanPreviewCard.vue'
import ExecutionResultCard from './ExecutionResultCard.vue'

const props = defineProps<{ plans: ConversationPlanVersion[]; executions: ConversationExecutionRound[]; currentPlanVersion?: ConversationPlanVersion | null; viewingPlanVersion?: ConversationPlanVersion | null; planDiff?: ConversationPlanDiff | null; versionLoading?: boolean; collapsed?: boolean }>()
const emit = defineEmits<{ collapse: []; expand: []; viewHistory: [id: string]; restoreVersion: [id: string]; approvePlan: [plan: ConversationPlanVersion] }>()
const store = useConversationStore()
const tab = ref<'files' | 'plans' | 'history'>('files')
const query = ref('')
const view = ref<'list' | 'grid'>('list')

const filteredFiles = computed(() => store.files.filter(file => {
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

    <section v-if="tab === 'files'" class="file-panel-body">
      <div class="file-panel-heading"><h2>当前目录的文件 <span>({{ store.files.length }})</span></h2><button type="button" class="panel-icon-button" aria-label="收起文件区" @click="emit('collapse')"><X :size="17" /></button></div>
      <div class="file-toolbar"><label class="file-search"><span class="sr-only">搜索文件</span><input v-model="query" type="search" placeholder="搜索文件…" /></label><div class="view-switch" role="group" aria-label="文件显示方式"><button type="button" :class="{ active: view === 'list' }" aria-label="列表视图" @click="view = 'list'"><List :size="17" /></button><button type="button" :class="{ active: view === 'grid' }" aria-label="网格视图" @click="view = 'grid'"><Grid2X2 :size="17" /></button></div></div>
      <div v-if="!filteredFiles.length" class="file-empty"><FileText :size="22" /><strong>{{ store.files.length ? '没有匹配的文件' : '当前目录还没有文件记录' }}</strong><p>绑定目录后，文件会显示在这里。</p></div>
      <div v-else class="file-list" :class="{ 'grid-view': view === 'grid' }">
        <button v-for="file in filteredFiles" :key="file.file_id" type="button" class="file-item" :class="{ selected: store.selectedFileIds.includes(file.file_id) }" @click="store.toggleFile(file.file_id)">
          <span class="file-icon"><component :is="FileIcon(file)" :size="18" /></span>
          <span class="file-copy"><strong>{{ basename(file) }}</strong><small>{{ relativePath(file) }}</small></span>
          <span class="file-meta"><small>{{ new Date(file.current_mtime_ns ? file.current_mtime_ns / 1_000_000 : file.added_at).toLocaleDateString('zh-CN') }}</small><small>{{ size(file) }}</small></span>
          <span v-if="statusLabel(file)" class="file-state" :data-state="file.state">{{ statusLabel(file) }}</span>
          <span v-else class="file-location"><Folder :size="14" />{{ relativePath(file).split(/[\\/]/)[0] || '当前目录' }}</span>
        </button>
      </div>
    </section>

    <section v-else-if="tab === 'plans'" class="file-panel-body alternate-panel">
      <div class="file-panel-heading"><h2>{{ props.viewingPlanVersion && props.viewingPlanVersion.id !== props.currentPlanVersion?.id ? `历史方案预览 · v${props.viewingPlanVersion.version_number}` : `整理预览${props.currentPlanVersion ? ` · v${props.currentPlanVersion.version_number}` : ''}` }}</h2><button type="button" class="panel-icon-button" aria-label="收起文件区" @click="emit('collapse')"><X :size="17" /></button></div>
      <div v-if="props.viewingPlanVersion && props.viewingPlanVersion.id !== props.currentPlanVersion?.id" class="historical-plan-banner">这是历史方案，不代表当前整理状态。</div>
      <div v-if="store.affectedScope" class="affected-scope-panel">
        <strong>本轮影响范围 · {{ store.affectedScope.scope_type }}</strong>
        <span>{{ store.refinementMetrics?.affected_files || store.affectedScope.candidate_file_ids.length }} 个候选文件</span>
        <span v-if="store.refinementMetrics?.delta_plan_count">其中 {{ store.refinementMetrics.delta_plan_count }} 个建议调整</span>
      </div>
      <div v-if="!props.plans.length" class="file-empty"><SlidersHorizontal :size="22" /><strong>还没有整理方案</strong><p>AI 生成整理方案后，会在这里预览新的目录结构。</p></div>
      <template v-else>
        <div v-if="props.currentPlanVersion?.status === 'EXECUTED' && (!props.viewingPlanVersion || props.viewingPlanVersion.id === props.currentPlanVersion.id)" class="historical-plan-banner current-clean">当前没有待执行的调整。</div>
        <div class="version-switcher" aria-label="方案版本历史">
          <button v-for="plan in props.plans" :key="plan.id" type="button" :class="{ active: plan.id === (props.viewingPlanVersion?.id || props.currentPlanVersion?.id) }" @click="emit('viewHistory', plan.id)">v{{ plan.version_number }}<small v-if="plan.id === props.currentPlanVersion?.id">当前</small></button>
        </div>
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
      </template>
    </section>

    <section v-else class="file-panel-body alternate-panel">
      <div class="file-panel-heading"><h2>变更记录</h2><button type="button" class="panel-icon-button" aria-label="收起文件区" @click="emit('collapse')"><X :size="17" /></button></div>
      <div v-if="!props.executions.length" class="file-empty"><List :size="22" /><strong>还没有执行记录</strong><p>执行后的整理记录会显示在这里。</p></div>
      <div v-else class="business-card-stack"><ExecutionResultCard v-for="round in props.executions" :key="round.id" :round="round" /></div>
    </section>

    <footer class="file-panel-footer"><span>已选择 {{ store.selectedFileIds.length }} 个文件</span><button type="button" class="open-folder-button" disabled><Folder :size="15" />打开所在目录</button></footer>
  </aside>
  <button v-else type="button" class="file-panel-expand" aria-label="展开文件区" @click="emit('expand')"><Folder :size="18" /></button>
</template>
