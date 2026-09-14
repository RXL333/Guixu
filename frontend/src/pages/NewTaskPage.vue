<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { FolderOpen, LockKeyhole } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { api, chooseDirectory, type ModelProfile, type ScanMode, type TaskSettings } from '../services/api'

const router = useRouter()
const settings = ref<TaskSettings | null>(null)
const name = ref('只读整理报告')
const typedPath = ref('')
const grant = reactive<{ id: string; path: string }>({ id: '', path: '' })
const output = reactive<{ id: string; path: string; typed: string }>({ id: '', path: '', typed: '' })
const models = ref<ModelProfile[]>([])
const modelId = ref('')
const busy = ref(false)
const error = ref('')
const canSubmit = computed(() => Boolean(settings.value && grant.id && name.value.trim() && !busy.value && (settings.value.operation_mode !== 'copy' || output.id)))

const modes: { value: ScanMode; title: string; text: string }[] = [
  { value: 'preserve_top_level', title: '保留一级目录', text: '每个直接子目录都是受保护区域，文件不会跨区。' },
  { value: 'current_only', title: '仅当前目录', text: '只查看根目录直接文件，不读取子目录。' },
  { value: 'recursive', title: '递归扫描', text: '把全部后代文件作为一个整理区域。' },
]

onMounted(async () => {
  try {
    settings.value = (await api.settings()).values
    settings.value.classification_source = 'template'
    models.value = await api.models()
  } catch (cause) { error.value = String(cause) }
})

async function selectDirectory(useTyped = false) {
  error.value = ''
  try {
    const result = await chooseDirectory('source', useTyped ? typedPath.value : undefined)
    if (!result.cancelled && result.grant_id && result.display_path) {
      grant.id = result.grant_id
      grant.path = result.display_path
      typedPath.value = result.display_path
    }
  } catch (cause) { error.value = `目录授权失败：${String(cause)}` }
}

async function selectOutput(useTyped=false) {
  try { const result=await chooseDirectory('output',useTyped?output.typed:undefined); if(!result.cancelled&&result.grant_id&&result.display_path){output.id=result.grant_id;output.path=result.display_path;output.typed=result.display_path} } catch(cause){error.value=`输出目录授权失败：${String(cause)}`}
}

async function submit() {
  if (!settings.value || !canSubmit.value) return
  busy.value = true
  error.value = ''
  try {
    const task = await api.createTask({ name: name.value.trim(), source_grant: grant.id, output_grant: output.id||null, settings: settings.value, model_profile_id:modelId.value||null, template_key:'universal.types' })
    await api.startTask(task.id, task.revision)
    await router.push(`/tasks/${task.id}/analyze`)
  } catch (cause) { error.value = String(cause) } finally { busy.value = false }
}
</script>

<template>
  <section class="page narrow-page">
    <p class="eyebrow">NEW ARCHIVE TASK</p>
    <h1>新建整理任务</h1>
    <p class="lead">先扫描与审阅；只有最终计划 hash 经确认后才可能改变文件。</p>
    <div v-if="error" class="notice danger-notice">{{ error }}</div>
    <section class="form-section">
      <span class="section-index">01</span><div class="form-content"><h2>整理哪里</h2>
        <label>任务名称<input v-model="name" maxlength="80" /></label>
        <label>源目录<div class="path-picker"><input v-model="typedPath" placeholder="通过原生选择器授权目录" /><button class="secondary-button" type="button" @click="selectDirectory(false)"><FolderOpen :size="17" /> 选择目录</button></div></label>
        <button v-if="typedPath && !grant.id" class="text-button" type="button" @click="selectDirectory(true)">授权输入的目录</button>
        <p v-if="grant.id" class="grant-ok"><LockKeyhole :size="15" /> 已授权：<code>{{ grant.path }}</code></p>
      </div>
    </section>
    <section v-if="settings" class="form-section">
      <span class="section-index">02</span><div class="form-content"><h2>整理成什么样</h2><div class="choice-grid">
        <label v-for="mode in modes" :key="mode.value" class="choice-card" :class="{ selected: settings.scan_mode === mode.value }">
          <input v-model="settings.scan_mode" type="radio" :value="mode.value" /><strong>{{ mode.title }}</strong><small>{{ mode.text }}</small>
        </label>
      </div><label>组织策略<select v-model="settings.organization_strategy"><option value="hybrid">智能混合</option><option value="topic_first">主题优先</option><option value="modality_first">模态优先</option></select></label><label>最多层级<select v-model.number="settings.max_depth"><option :value="1">1 级</option><option :value="2">2 级</option><option :value="3">3 级</option></select></label></div>
    </section>
    <section v-if="settings" class="form-section"><span class="section-index">03</span><div class="form-content"><h2>怎么处理</h2><div class="choice-grid"><label v-for="item in [{v:'preview_move',t:'预览后移动',d:'最终再批准计划'},{v:'copy',t:'复制',d:'源文件始终保留'},{v:'report_only',t:'仅报告',d:'不改变磁盘'}]" :key="item.v" class="choice-card" :class="{selected:settings.operation_mode===item.v}"><input v-model="settings.operation_mode" type="radio" :value="item.v"/><strong>{{item.t}}</strong><small>{{item.d}}</small></label></div><label v-if="settings.operation_mode==='copy'">输出目录<div class="path-picker"><input v-model="output.typed"/><button class="secondary-button" @click="selectOutput(true)">授权输出目录</button></div></label></div></section>
    <section v-if="settings" class="form-section muted-section"><span class="section-index">04</span><div class="form-content"><h2>模型与隐私</h2><label>模型连接<select v-model="modelId"><option value="">不使用模型（纯类型模板）</option><option v-for="model in models" :key="model.id" :value="model.id">{{model.name}} · {{model.trust_scope}}</option></select></label><p>默认不发送文件名、绝对路径、精确 GPS、原音频或原视频。选择云模型后仍需为具体任务另行确认出站范围与预算。</p></div></section>
    <footer class="action-bar"><span>{{ grant.path || '尚未选择目录' }} · {{ settings?.scan_mode ?? '读取设置中' }} · 最多 {{settings?.max_depth}} 级</span><button class="primary-button" :disabled="!canSubmit" @click="submit">{{ busy ? '正在扫描…' : '扫描并生成方案' }}</button></footer>
  </section>
</template>
