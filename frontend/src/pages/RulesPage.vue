<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Plus, ShieldAlert } from 'lucide-vue-next'
import { api, type RuleItem } from '../services/api'

const rules = ref<RuleItem[]>([]); const name = ref('排除临时文件'); const suffix = ref('.tmp'); const error = ref(''); const saving = ref(false)
async function load() { rules.value = (await api.rules()).items }
async function create() {
  saving.value = true; error.value = ''
  try {
    await api.createRule({ name: name.value, priority: 100, enabled: true, scope: {}, condition: { field: 'extension', op: 'eq', value: suffix.value }, action: { type: 'exclude', category_id: null, template_key: null } })
    await load()
  } catch (cause) { error.value = String(cause) } finally { saving.value = false }
}
onMounted(() => load().catch(cause => { error.value = String(cause) }))
</script>

<template>
  <section class="page narrow-page"><header class="page-heading"><div><p class="eyebrow">SAFE RULE AST</p><h1>规则中心</h1><p class="lead">规则是可审阅的字段、比较符和动作，不执行正则脚本或代码。</p></div><span class="mode-chip"><ShieldAlert :size="16" /> 排除优先</span></header>
    <div class="rule-editor"><h2>新增排除规则</h2><label>名称<input v-model="name" maxlength="80" /></label><label>扩展名<input v-model="suffix" placeholder=".tmp" /></label><button class="primary-button" :disabled="saving || !name || !suffix" @click="create"><Plus :size="16" />{{ saving ? '保存中…' : '明确保存为规则' }}</button><p v-if="error" class="error-state notice">{{ error }}</p></div>
    <div class="section-block"><div class="section-heading"><h2>已保存规则</h2><span>{{ rules.length }} 条</span></div><div v-if="!rules.length" class="state-card">尚未保存规则。一次人工改类不会自动出现在这里。</div><article v-for="rule in rules" :key="rule.id" class="rule-row"><div><strong>{{ rule.name }}</strong><small>优先级 {{ rule.priority }} · revision {{ rule.revision }}</small></div><code>{{ rule.condition }}</code><span>{{ rule.action.type }}</span></article></div>
  </section>
</template>
