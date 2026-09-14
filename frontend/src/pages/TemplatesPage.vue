<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Bot, Filter, ShieldCheck } from 'lucide-vue-next'
import { api, type ClassificationTemplate } from '../services/api'

const templates = ref<ClassificationTemplate[]>([])
const filter = ref('all')
const error = ref('')
const visible = computed(() => filter.value === 'all' ? templates.value : templates.value.filter(item => item.modalities.includes(filter.value)))
onMounted(async () => { try { templates.value = (await api.templates()).items } catch (cause) { error.value = String(cause) } })
</script>

<template>
  <section class="page">
    <header class="page-heading"><div><p class="eyebrow">VERSIONED TAXONOMY</p><h1>分类模板</h1><p class="lead">24 套内置定义从本地数据库读取；内置版本只读，复制后才可编辑。</p></div><span class="mode-chip"><ShieldCheck :size="16" /> 受限类别 ID</span></header>
    <div class="template-toolbar"><Filter :size="16" /><button v-for="item in ['all','image','text','document','audio','video']" :key="item" :class="{active: filter === item}" @click="filter = item">{{ item === 'all' ? '全部' : item }}</button></div>
    <div v-if="error" class="state-card error-state">{{ error }}</div>
    <div v-else class="template-grid">
      <article v-for="item in visible" :key="item.template_id" class="template-card"><div class="template-card-top"><code>{{ item.template_id }} · v{{ item.version }}</code><Bot v-if="item.requires_ai" :size="16" /></div><h2>{{ item.name }}</h2><p>{{ item.description }}</p><footer><span>{{ item.nodes.filter(node => node.selectable).length }} 个可选类别</span><span>{{ item.requires_ai ? '需要模型' : '纯规则可用' }}</span></footer></article>
    </div>
  </section>
</template>
