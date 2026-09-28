<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RefreshCw, Trash2 } from 'lucide-vue-next'
import { api, type ModelProfile } from '../services/api'

const items = ref<ModelProfile[]>([])
const error = ref('')
const busy = ref('')
const pendingDelete = ref('')
const secret = ref('')
const form = reactive({ provider: 'qwen_local', runtime: 'openai_compatible', name: '本地千问', base_url: 'http://127.0.0.1:8000/v1', model_id: 'Qwen/Qwen3.8-27B', trust_scope: 'loopback' })
const privacyLabel = computed(() => form.trust_scope === 'loopback' ? '数据只发送到本机回环服务' : form.trust_scope === 'trusted_lan' ? '数据会发送到你明确信任的局域网服务' : '数据会发送到 DeepSeek 云服务')

async function load() { try { items.value = await api.models() } catch (e) { error.value = String(e) } }
function preset() {
  if (form.provider === 'deepseek') Object.assign(form, { runtime:'deepseek', name:'DeepSeek 云端', base_url:'https://api.deepseek.com', model_id:'deepseek-flash', trust_scope:'cloud' })
  else Object.assign(form, { runtime:'openai_compatible', name:'本地千问', base_url:'http://127.0.0.1:8000/v1', model_id:'Qwen/Qwen3.8-27B', trust_scope:'loopback' })
}
async function create() {
  error.value=''; busy.value='create'
  try {
    const model=await api.createModel({ ...form, options:{ thinking_mode:form.provider==='deepseek'?'disabled':'server_default', timeout_seconds:60, max_concurrency:1 }, enabled:true })
    if (secret.value) { await api.saveModelSecret(model.id, model.revision, secret.value); secret.value='' }
    await load()
  } catch(e) { error.value=String(e) } finally { busy.value='' }
}
async function probe(item: ModelProfile) { busy.value=item.id; error.value=''; try { await api.probeModel(item.id); await load() } catch(e) { error.value=String(e) } finally { busy.value='' } }
async function remove(item: ModelProfile) {
  if (busy.value) return
  busy.value=`delete:${item.id}`; error.value=''
  try { await api.deleteModel(item.id,item.revision); pendingDelete.value=''; await load() }
  catch(e) { error.value=String(e) }
  finally { busy.value='' }
}
function verificationLabel(item: ModelProfile, key: 'text' | 'vision') {
  return item.capabilities[key]?.status === 'supported' ? '已验证' : '失败'
}
function verificationError(item: ModelProfile, key: 'text' | 'vision') {
  const capability = item.capabilities[key]
  if (!capability || capability.status === 'supported') return ''
  return capability.probe_error || capability.message || '尚未探测'
}
onMounted(load)
</script>

<template>
  <section class="page">
    <nav class="page-nav" aria-label="设置页面"><RouterLink to="/models">模型连接</RouterLink><RouterLink to="/settings">通用设置</RouterLink></nav><h1>模型连接</h1>
    <p class="lede">连接云端或本地模型。连接测试不会使用你的文件。</p>
    <div class="state-card model-form">
      <div class="segmented"><button :class="{ active: form.provider==='qwen_local' }" @click="form.provider='qwen_local';preset()">本地 Qwen</button><button :class="{ active: form.provider==='deepseek' }" @click="form.provider='deepseek';preset()">DeepSeek</button></div>
      <label>连接名称<input v-model="form.name" /></label><label>服务地址<input v-model="form.base_url" /></label><label>模型 ID<input v-model="form.model_id" /></label>
      <label v-if="form.provider==='qwen_local'">信任范围<select v-model="form.trust_scope"><option value="loopback">仅本机</option><option value="trusted_lan">可信局域网</option></select></label>
      <label>API Key（可选，保存后不回显）<input v-model="secret" type="password" autocomplete="new-password" /></label>
      <p class="privacy-note">{{ privacyLabel }}</p><button class="primary" :disabled="!!busy" @click="create">保存连接</button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
    <div v-if="!items.length" class="state-card"><strong>尚无连接</strong><p>添加模型连接后，即可开始 AI 内容分析。已保存的消息和历史仍可查看。</p></div>
    <article v-for="item in items" :key="item.id" class="state-card model-card">
      <header><div><strong>{{ item.name }}</strong><p>{{ item.model_id }} · {{ item.base_url }}</p></div><span>{{ item.has_secret ? '凭据已保存' : '无凭据' }}</span></header>
      <p class="privacy-note">{{ item.trust_scope === 'loopback' ? '仅本机回环' : item.trust_scope === 'trusted_lan' ? '可信局域网' : '云端服务' }}</p>
      <div class="verification-summary">
        <p :data-state="item.capabilities.text?.status"><b>文本：</b>{{ verificationLabel(item, 'text') }}</p>
        <p :data-state="item.capabilities.vision?.status"><b>视觉：</b>{{ verificationLabel(item, 'vision') }}</p>
        <p v-if="verificationError(item, 'text')" class="probe-error"><b>文本失败原因：</b>{{ verificationError(item, 'text') }}</p>
        <p v-if="verificationError(item, 'vision')" class="probe-error"><b>视觉失败原因：</b>{{ verificationError(item, 'vision') }}</p>
      </div>
      <details><summary>连接诊断详情</summary><div class="cap-grid"><span v-for="(cap,key) in item.capabilities" :key="key" :data-state="cap.status"><b>{{ key }}</b>{{ cap.status }}<small>{{ cap.message }}</small></span></div></details>
      <div class="model-actions">
        <button class="model-action-button" :disabled="!!busy" @click="probe(item)"><RefreshCw :size="16" aria-hidden="true" />测试连接与能力</button>
        <button class="model-action-button danger-button" :disabled="!!busy" @click="pendingDelete=item.id"><Trash2 :size="16" aria-hidden="true" />删除连接</button>
      </div>
      <div v-if="pendingDelete===item.id" class="delete-confirm" role="alert">
        <p>删除后此连接不再出现在可用模型中；既有任务的审计引用仍会保留。</p>
        <div class="model-actions"><button class="danger-button" :disabled="!!busy" @click="remove(item)">{{busy===`delete:${item.id}`?'正在删除…':'确认删除'}}</button><button :disabled="!!busy" @click="pendingDelete=''">取消</button></div>
      </div>
    </article>
  </section>
</template>

<style scoped>
.model-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.model-form label{display:grid;gap:7px;font-size:13px}.model-form input,.model-form select{min-height:42px;padding:0 12px;border:1px solid var(--border-strong);border-radius:8px;background:#fff;color:var(--text-primary)}.segmented,.privacy-note,.model-form button{grid-column:1/-1}.segmented button{min-height:36px;margin-right:8px;padding:0 14px;border:1px solid var(--border-strong);border-radius:7px;background:var(--bg-subtle);color:var(--text-primary)}.segmented .active{background:var(--primary);color:white;border-color:var(--primary)}.model-form .primary{min-height:42px;border:0;border-radius:8px;background:var(--primary);color:white;font-weight:600}.model-card{margin-top:16px;border:0;border-bottom:1px solid var(--border-default);border-radius:0;padding:20px 0}.model-form{background:var(--bg-subtle);margin:24px 0}.model-form .primary{justify-self:start;padding:0 20px}.model-card header{display:flex;justify-content:space-between;gap:20px}.model-card p{margin:4px 0}.verification-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:14px 0;padding:12px;border-radius:8px;background:var(--bg-subtle)}.verification-summary p{padding:4px 0}.verification-summary p[data-state="supported"]{color:var(--primary)}.verification-summary p[data-state="unsupported"],.verification-summary p[data-state="error"],.probe-error{color:var(--danger)}.verification-summary .probe-error{grid-column:1/-1;overflow-wrap:anywhere}.cap-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:16px 0}.cap-grid span{display:grid;padding:10px;border:1px solid var(--border-default);border-radius:8px;font-size:12px}.cap-grid span[data-state="supported"]{border-color:#4f8b6d}.cap-grid small{color:var(--text-secondary);margin-top:4px}.privacy-note{color:var(--text-secondary)}.model-actions{display:flex;gap:10px;flex-wrap:wrap}.danger-button{border-color:#b34d45!important;color:var(--danger)!important;background:var(--danger-soft)!important}.delete-confirm{margin-top:12px;padding:12px;border:1px solid #d79a93;border-radius:8px;background:var(--danger-soft)}.error{color:#a33}@media(max-width:900px){.model-form,.cap-grid,.verification-summary{grid-template-columns:1fr}.verification-summary .probe-error{grid-column:1}}
.model-action-button{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:36px;padding:0 13px;border:1px solid var(--border-strong);border-radius:8px;color:var(--accent-primary);background:var(--bg-surface);font-size:13px;font-weight:600}
.model-action-button:hover:not(:disabled){border-color:var(--accent-primary);background:var(--accent-soft)}
.model-action-button.danger-button{border-color:#e3c7c7!important;color:var(--danger)!important;background:var(--bg-surface)!important}
.model-action-button.danger-button:hover:not(:disabled){background:var(--danger-soft)!important}
</style>
