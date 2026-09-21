<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Plus, Save, Trash2 } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import TaskStepper from '../components/TaskStepper.vue'
import TaxonomyTree from '../components/TaxonomyTree.vue'
import { api, type Task, type Taxonomy } from '../services/api'

const route = useRoute(), router = useRouter()
const task = ref<Task | null>(null), trees = ref<Taxonomy[]>([]), selected = ref(''), error = ref(''), busy = ref(false)
const current = computed(() => trees.value.find(item => item.status === 'draft') || trees.value.find(item => item.status === 'approved'))
const rationale = computed(() => String(current.value?.policy?.planner_rationale || 'AI 根据代表性文件的内容证据和当前整理要求生成此结构。'))

async function load() {
  const id = String(route.params.id)
  task.value = await api.task(id); trees.value = await api.taxonomies(id)
}
onMounted(() => load().catch(cause => { error.value = String(cause) }))

function rename(categoryId: string, name: string) {
  if (!current.value || current.value.status !== 'draft') return
  const node = current.value.nodes.find(item => item.category_id === categoryId); if (node) node.name = name
}
function reparent(categoryId: string, parentId: string) {
  if (!current.value || current.value.status !== 'draft') return
  const node = current.value.nodes.find(item => item.category_id === categoryId); if (node) node.parent_id = parentId || null
}
function remove(categoryId: string) {
  if (!current.value || current.value.status !== 'draft') return
  current.value.nodes = current.value.nodes.filter(item => item.category_id !== categoryId)
  current.value.nodes.forEach(item => { if (item.parent_id === categoryId) item.parent_id = null })
}
function add() {
  if (!current.value || current.value.status !== 'draft') return
  const id = `user.category_${Date.now().toString(36)}`
  current.value.nodes.push({ category_id:id, parent_id:null, name:'新类别', selectable:true,
    definition:{ description:'用户新增类别', selection_criteria:'由 AI 按内容判断是否属于此类别' }, is_fallback:false })
}
async function save() {
  if (!task.value || !current.value || current.value.status !== 'draft') return
  busy.value = true; error.value = ''
  try { await api.updateTaxonomy(task.value.id, current.value, task.value.revision); await load() }
  catch (cause) { error.value = String(cause) } finally { busy.value = false }
}
async function approve() {
  if (!task.value || !current.value) return
  busy.value = true; error.value = ''
  try {
    if (current.value.status === 'draft') await api.approveTaxonomy(task.value.id, current.value.taxonomy_id, task.value.revision, current.value.tree_hash)
    else if (task.value.status !== 'AWAITING_EXECUTION_APPROVAL') await api.retryClassification(task.value.id, current.value.taxonomy_id)
    await router.push(`/tasks/${task.value.id}/review`)
  } catch (cause) { error.value = String(cause) } finally { busy.value = false }
}
</script>

<template>
  <section class="page"><TaskStepper :current="2"/>
    <header class="page-heading"><div><p class="eyebrow">AI TAXONOMY REVIEW</p><h1>确认分类结构</h1><p class="lead">先调整 AI 规划的逻辑类别；批准后才会逐文件进行 AI 内容分类，此时仍不会移动文件。</p></div></header>
    <p v-if="error" class="notice danger-notice">{{error}}</p>
    <div v-if="current" class="taxonomy-layout">
      <section class="state-card"><p><b>{{current.nodes.length}}</b> 个节点 · v{{current.version}} · {{current.status}}</p><TaxonomyTree :taxonomy="current" :selected="selected" @select="selected=$event"/></section>
      <aside class="state-card"><h2>AI 规划说明</h2><p>{{rationale}}</p><p>最多 {{task?.settings.max_depth}} 级，同级最多 {{task?.settings.max_siblings}} 个目录。</p><code>{{current.tree_hash}}</code></aside>
    </div>
    <section v-if="current?.status==='draft'" class="state-card taxonomy-editor"><header><h2>编辑分类树</h2><button class="secondary-button" @click="add"><Plus :size="16"/>新增类别</button></header>
      <div v-for="node in current.nodes" :key="node.category_id" class="taxonomy-edit-row"><input :value="node.name" aria-label="类别名称" @input="rename(node.category_id,($event.target as HTMLInputElement).value)"/><select :value="node.parent_id||''" aria-label="父类别" @change="reparent(node.category_id,($event.target as HTMLSelectElement).value)"><option value="">顶级类别</option><option v-for="candidate in current.nodes.filter(item=>item.category_id!==node.category_id)" :key="candidate.category_id" :value="candidate.category_id">{{candidate.name}}</option></select><code>{{node.category_id}}</code><button class="icon-button" aria-label="删除类别" :disabled="current.nodes.length<=1" @click="remove(node.category_id)"><Trash2 :size="16"/></button></div>
      <button class="secondary-button" :disabled="busy" @click="save"><Save :size="16"/>保存分类树修改</button>
    </section>
    <div v-if="!current" class="state-card">尚无分类树；请返回分析页查看 AI 规划错误并重试。</div>
    <footer class="action-bar"><span>批准会冻结 tree hash 并开始 AI 文件分类；原文件不变</span><button class="primary-button" :disabled="!current||busy" @click="approve">{{busy?'AI 正在分类…':current?.status==='approved'?'重试 AI 分类':'批准分类树并开始 AI 分类'}}</button></footer>
  </section>
</template>
