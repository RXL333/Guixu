<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { FolderOpen, LockKeyhole } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { api, chooseDirectory, type ModelProfile, type TaskSettings } from '../services/api'

const router = useRouter()
const settings = ref<TaskSettings | null>(null)
const name = ref('AI 整理')
const typedPath = ref('')
const grant = reactive({ id:'', path:'' })
const output = reactive({ id:'', path:'', typed:'' })
const models = ref<ModelProfile[]>([])
const instructions = ref('')
const acknowledgeAI = ref(false)
const modelId = ref('')
const busy = ref(false)
const error = ref('')
const selectedModel = computed(() => models.value.find(item => item.id === modelId.value))
const canSubmit = computed(() => Boolean(settings.value && grant.id && name.value.trim() && modelId.value && acknowledgeAI.value && !busy.value && (settings.value.operation_mode !== 'copy' || output.id)))

onMounted(async () => {
  try {
    settings.value = (await api.settings()).values
    settings.value.classification_source = 'auto_plan'
    settings.value.max_depth = 2
    settings.value.analysis_preset = 'standard'
    settings.value.operation_mode = 'preview_move'
    models.value = await api.models()
  } catch (cause) { error.value = String(cause) }
})

function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(',')}]`
  if (value && typeof value === 'object') return `{${Object.keys(value as Record<string, unknown>).sort().map(key => `${JSON.stringify(key)}:${stable((value as Record<string, unknown>)[key])}`).join(',')}}`
  return JSON.stringify(value)
}
async function sha256(value: string) {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))
  return Array.from(new Uint8Array(bytes)).map(item => item.toString(16).padStart(2, '0')).join('')
}
async function selectDirectory(useTyped=false) {
  error.value = ''
  try {
    const result = await chooseDirectory('source', useTyped ? typedPath.value : undefined)
    if (!result.cancelled && result.grant_id && result.display_path) {
      grant.id=result.grant_id; grant.path=result.display_path; typedPath.value=result.display_path
    }
  } catch (cause) { error.value=`目录授权失败：${String(cause)}` }
}
async function selectOutput() {
  try {
    const result=await chooseDirectory('output',output.typed)
    if(!result.cancelled&&result.grant_id&&result.display_path){output.id=result.grant_id;output.path=result.display_path;output.typed=result.display_path}
  } catch(cause){error.value=`输出目录授权失败：${String(cause)}`}
}
async function submit() {
  if (!settings.value || !canSubmit.value) return
  busy.value=true; error.value=''
  try {
    settings.value.classification_source='auto_plan'
    let task=await api.createTask({name:name.value.trim(),source_grant:grant.id,output_grant:output.id||null,settings:settings.value,model_profile_id:modelId.value,user_instructions:instructions.value})
    const privacy=settings.value.privacy
    const dataTypes=[privacy.allow_extracted_text&&'extracted_text',privacy.allow_derivative_images&&'derivative_images',privacy.allow_video_frames&&'video_frames',privacy.allow_asr_text&&'asr_text'].filter(Boolean) as string[]
    const budget=settings.value.task_budget
    const scope_hash=await sha256(stable({provider_profile_id:modelId.value,data_types:[...dataTypes].sort(),budget}))
    await api.grantConsent(task.id,{expected_revision:task.revision,provider_profile_id:modelId.value,scope_hash,data_types:dataTypes,budget,acknowledge_content_disclosure:true})
    task=await api.task(task.id)
    await api.startTask(task.id,task.revision)
    await router.push(`/tasks/${task.id}/analyze`)
  } catch(cause){error.value=String(cause)} finally {busy.value=false}
}
</script>

<template>
  <section class="page narrow-page">
    <p class="eyebrow">AI ORGANIZATION</p><h1>开始一次 AI 整理</h1>
    <p class="lead">选择文件夹并告诉 AI 整理要求。AI 会先分析内容和生成方案，最终确认前不会改变文件。</p>
    <p v-if="error" class="notice danger-notice">{{error}}</p>
    <section class="form-section"><span class="section-index">01</span><div class="form-content"><h2>选择文件夹</h2>
      <label>任务名称<input v-model="name" maxlength="80"/></label>
      <label>源目录<div class="path-picker"><input v-model="typedPath" placeholder="通过原生选择器授权目录"/><button class="secondary-button" type="button" @click="selectDirectory(false)"><FolderOpen :size="17"/>选择目录</button></div></label>
      <button v-if="typedPath&&!grant.id" class="text-button" type="button" @click="selectDirectory(true)">授权输入的目录</button>
      <p v-if="grant.id" class="grant-ok"><LockKeyhole :size="15"/>已授权：<code>{{grant.path}}</code></p>
    </div></section>
    <section class="form-section"><span class="section-index">02</span><div class="form-content"><h2>整理要求</h2>
      <label>告诉 AI 你希望怎样整理这些文件<textarea v-model="instructions" rows="6" placeholder="例如：这些是大学资料，按照课程分类，每门课再分课件、作业和实验。留空时由 AI 自主规划。"/></label>
    </div></section>
    <section v-if="settings" class="form-section"><span class="section-index">03</span><div class="form-content"><h2>分析设置</h2>
      <label>AI 模型<select v-model="modelId"><option value="" disabled>请选择可用 AI 模型</option><option v-for="model in models.filter(item=>item.enabled)" :key="model.id" :value="model.id">{{model.name}} · {{model.provider}}</option></select></label>
      <p v-if="selectedModel" class="model-capabilities">连接可用 · text：{{selectedModel.capabilities.text?.status||'unknown'}} · vision：{{selectedModel.capabilities.vision?.status||'unknown'}}</p>
      <label>最大目录深度<select v-model.number="settings.max_depth"><option :value="1">1</option><option :value="2">2（推荐）</option><option :value="3">3</option></select></label>
      <label>分析强度<select v-model="settings.analysis_preset"><option value="fast">快速</option><option value="standard">标准（推荐）</option><option value="deep">深入</option></select></label>
    </div></section>
    <section v-if="settings" class="form-section"><span class="section-index">04</span><div class="form-content"><h2>执行方式</h2><div class="choice-grid">
      <label v-for="item in [{v:'preview_move',t:'预览确认后移动',d:'推荐；核对完整方案后再移动'},{v:'copy',t:'复制',d:'源文件始终保留'},{v:'report_only',t:'只生成报告',d:'不改变磁盘'}]" :key="item.v" class="choice-card" :class="{selected:settings.operation_mode===item.v}"><input v-model="settings.operation_mode" type="radio" :value="item.v"/><strong>{{item.t}}</strong><small>{{item.d}}</small></label>
    </div><label v-if="settings.operation_mode==='copy'">输出目录<div class="path-picker"><input v-model="output.typed"/><button class="secondary-button" type="button" @click="selectOutput">授权输出目录</button></div></label></div></section>
    <section v-if="settings" class="form-section muted-section"><span class="section-index">05</span><div class="form-content"><h2>内容授权</h2>
      <label class="ack"><input v-model="acknowledgeAI" type="checkbox"/>我同意本任务把已启用的文本摘要、OCR/转写与受控图片衍生图发送给所选 {{selectedModel?.trust_scope==='cloud'?'云端':'本地'}} 模型；不会发送 API Key、原始路径或未经授权的原图。</label>
      <p>模型能力不足时会明确停止，不会退回按扩展名或本地规则分类。</p>
    </div></section>
    <footer class="action-bar"><span>{{grant.path||'尚未选择目录'}} · {{modelId?'AI 模型已选择':'需要选择 AI 模型'}} · 最多 {{settings?.max_depth}} 级</span><button class="primary-button" :disabled="!canSubmit" @click="submit">{{busy?'正在启动…':'开始 AI 分析'}}</button></footer>
  </section>
</template>
