<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { CheckCircle2, FileQuestion, Microscope, ShieldCheck, X } from 'lucide-vue-next'
import { api, type FileDetail, type FileItem, type Task, type TaskEvent, type Taxonomy } from '../services/api'

const route = useRoute()
const task = ref<Task | null>(null)
const files = ref<FileItem[]>([])
const error = ref('')
const loading = ref(true)
const analyzing = ref('')
const detail = ref<FileDetail | null>(null)
const taxonomies = ref<Taxonomy[]>([])
const approving = ref('')
const events = ref<TaskEvent[]>([])
const reviewCategory = ref('')
const eligible = computed(() => files.value.filter((file) => file.scan_status === 'eligible').length)

onMounted(async () => {
  try {
    const id = String(route.params.id)
    task.value = await api.task(id)
    files.value = (await api.files(id)).items
    taxonomies.value = await api.taxonomies(id)
    events.value = (await api.events(id)).items
  } catch (cause) { error.value = String(cause) } finally { loading.value = false }
})

function formatSize(bytes: number) { return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB` }

async function inspect(file: FileItem) {
  if (!task.value) return
  error.value = ''
  try {
    detail.value = await api.file(task.value.id, file.id)
    if (!detail.value.profile && file.scan_status === 'eligible') {
      analyzing.value = file.id
      await api.reanalyze(task.value.id, task.value.revision, file.id)
      detail.value = await api.file(task.value.id, file.id)
    }
    reviewCategory.value = detail.value.latest_review?.category_id ?? detail.value.suggestion?.category_id ?? ''
  } catch (cause) { error.value = String(cause) } finally { analyzing.value = '' }
}

const aiProgress = computed(() => {
  const labels: Record<string,string> = {
    scan_completed:'只读扫描完成', AI_PLANNER_STARTED:'AI 正在理解代表性文件并规划分类树',
    AI_PLANNER_COMPLETED:'AI 分类树规划完成，等待确认', AI_PLANNER_FAILED:'AI 分类树规划失败',
    AI_CLASSIFY_BATCH_STARTED:'AI 正在分析文件批次', AI_CLASSIFY_BATCH_COMPLETED:'AI 已完成一个文件批次',
    AI_CLASSIFY_BATCH_FAILED:'AI 文件分类失败', AI_CLASSIFICATION_COMPLETED:'AI 文件分类完成，等待审阅',
  }
  return events.value.slice(-6).map(item => ({ ...item, label: labels[item.event_type] || item.event_type }))
})

async function approve(taxonomy: Taxonomy) {
  if (!task.value) return
  approving.value = taxonomy.taxonomy_id; error.value = ''
  try {
    await api.approveTaxonomy(task.value.id, taxonomy.taxonomy_id, task.value.revision, taxonomy.tree_hash)
    task.value = await api.task(task.value.id)
    taxonomies.value = await api.taxonomies(task.value.id)
  } catch (cause) { error.value = String(cause) } finally { approving.value = '' }
}

function taxonomyForDetail() { return taxonomies.value.find(item => item.scope_id === detail.value?.file.scope_id && item.status === 'approved') }

async function saveReview() {
  if (!task.value || !detail.value || !reviewCategory.value) return
  const taxonomy = taxonomyForDetail(); if (!taxonomy) return
  try {
    const result = await api.review(task.value.id, task.value.revision, { file_id: detail.value.file.id, taxonomy_id: taxonomy.taxonomy_id, category_id: reviewCategory.value, decision: detail.value.suggestion?.category_id === reviewCategory.value ? 'accept' : 'change', note: '' })
    task.value = { ...task.value, revision: result.new_revision }
    detail.value = await api.file(task.value.id, detail.value.file.id)
  } catch (cause) { error.value = String(cause) }
}

function locatorText(locator: Record<string, unknown>) {
  const entries = Object.entries(locator)
  return entries.length ? entries.map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join('–') : value}`).join(' · ') : '文件级'
}
</script>

<template>
  <section class="page scan-page">
    <div class="task-stepper"><span class="done">设置</span><span class="done">分析</span><span>分类树</span><span>审阅</span><span>执行</span><span>结果</span></div>
    <header class="page-heading"><div><p class="eyebrow">READ-ONLY SCAN</p><h1>{{ task?.name ?? '扫描结果' }}</h1></div><span class="mode-chip"><ShieldCheck :size="16" /> 原文件未改变</span></header>
    <div v-if="loading" class="state-card">正在读取扫描结果…</div>
    <div v-else-if="error" class="state-card error-state">扫描失败：{{ error }}</div>
    <template v-else>
      <div class="summary-strip"><span><strong>{{ files.length }}</strong> 已扫描</span><span><strong>{{ eligible }}</strong> 等待/完成 AI 理解</span><span><strong>{{ files.length - eligible }}</strong> 已排除</span><span><strong>{{ task?.phase }}</strong> 当前阶段</span></div>
      <section v-if="aiProgress.length" class="state-card"><h2>AI 实际进度</h2><div v-for="item in aiProgress" :key="item.seq" class="operation-row"><b>#{{item.seq}}</b><span>{{item.label}}</span><small v-if="item.payload.batch_index">第 {{item.payload.batch_index}} / {{item.payload.batch_count}} 批 · {{item.payload.file_count}} 个文件</small></div></section>
      <section v-for="taxonomy in taxonomies.filter(item => item.status === 'draft')" :key="taxonomy.taxonomy_id" class="taxonomy-approval"><div><strong>分类树 v{{ taxonomy.version }} 等待批准</strong><small>{{ taxonomy.nodes.length }} 个节点；批准后哈希冻结，AI 只能选择现有类别。</small></div><button class="primary-button" :disabled="!!approving" @click="approve(taxonomy)">{{ approving === taxonomy.taxonomy_id ? 'AI 正在理解并分类…' : '核对并批准分类树' }}</button></section>
      <div v-if="files.length === 0" class="state-card empty-state"><FileQuestion /><strong>这个范围内没有文件</strong><p>请返回并选择其他测试目录或扫描方式。</p></div>
      <div v-else class="file-table" role="table" aria-label="真实扫描文件">
        <div class="file-row table-head" role="row"><span>文件</span><span>整理区域</span><span>类型建议</span><span>大小</span><span>状态</span></div>
        <button v-for="file in files" :key="file.id" class="file-row file-row-button" role="row" :disabled="analyzing === file.id" @click="inspect(file)">
          <span class="file-name"><strong>{{ file.basename }}</strong><small>{{ file.relative_path }}</small></span>
          <span>{{ file.scope_name }}</span><span>{{ file.modality }}<small>{{ file.metadata.type_evidence }}</small></span><span>{{ formatSize(file.size_bytes) }}</span>
          <span :class="file.scan_status === 'eligible' ? 'ok-text' : 'warning-text'"><Microscope v-if="analyzing === file.id" :size="15" /><CheckCircle2 v-else-if="file.scan_status === 'eligible'" :size="15" />{{ analyzing === file.id ? '本地解析中…' : file.scan_status === 'eligible' ? '查看证据' : file.exclusion_code }}</span>
        </button>
      </div>
      <aside v-if="detail" class="evidence-panel" aria-label="文件解析证据">
        <header><div><p class="eyebrow">LOCAL FILE PROFILE</p><h2>{{ detail.file.basename }}</h2></div><button class="icon-button" aria-label="关闭详情" @click="detail = null"><X :size="18" /></button></header>
        <div v-if="!detail.profile" class="state-card">此文件未生成解析档案。</div>
        <template v-else>
          <div class="profile-facts"><span><strong>{{ detail.profile.coverage.mode }}</strong>覆盖方式</span><span><strong>{{ detail.profile.evidence.length }}</strong>证据片段</span><span><strong>{{ detail.profile.parser_version }}</strong>解析版本</span></div>
          <p v-if="detail.profile.coverage.truncated || detail.profile.coverage.sampled_pages.length" class="sampling-note">采样提示：页 {{ detail.profile.coverage.sampled_pages.join('、') || '按策略分层' }}；{{ detail.profile.coverage.truncated ? '未覆盖全部内容' : '已覆盖全部页' }}。</p>
          <div v-if="detail.profile.warnings.length" class="warning-list"><span v-for="warning in detail.profile.warnings" :key="warning">{{ warning }}</span></div>
          <div v-if="detail.suggestion" class="suggestion-card"><span :class="`band-${detail.suggestion.review_band}`">{{ detail.suggestion.review_band }}</span><div><strong>{{ detail.suggestion.category_id ?? '待确认' }}</strong><p>{{ detail.suggestion.reason }}</p></div></div>
          <div v-if="taxonomyForDetail()" class="review-controls"><label>人工审阅类别<select v-model="reviewCategory"><option disabled value="">请选择</option><option v-for="node in taxonomyForDetail()!.nodes.filter(item => item.selectable)" :key="node.category_id" :value="node.category_id">{{ node.name }} · {{ node.category_id }}</option></select></label><button class="primary-button" :disabled="!reviewCategory" @click="saveReview">{{ detail.latest_review ? '更新人工决定' : '保存人工决定' }}</button><small>人工决定只作用于此文件，不会生成或训练本地分类规则。</small></div>
          <article v-for="evidence in detail.profile.evidence" :key="evidence.id" class="evidence-card"><div><strong>{{ evidence.kind }}</strong><small>{{ locatorText(evidence.locator) }} · {{ evidence.origin }} · {{ evidence.quality }}</small></div><p>{{ evidence.text }}</p></article>
        </template>
      </aside>
      <footer class="action-bar"><span>已发现 {{files.length}} 项 · 已执行 0 项</span><RouterLink class="primary-button" :to="`/tasks/${task?.id}/taxonomy`">查看分类结构并继续</RouterLink></footer>
    </template>
  </section>
</template>
