<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type TaskSettings } from '../services/api'
const settings = ref<TaskSettings | null>(null)
const components = ref<Array<Record<string, unknown>>>([])
const error = ref('')
onMounted(async () => { try { settings.value = (await api.settings()).values; components.value = await api.components() } catch (e) { error.value = String(e) } })
</script>
<template><section class="page"><p class="eyebrow">LOCAL SETTINGS</p><h1>设置与资源</h1><p class="lead">此页显示后端真实默认值和已验证组件，不会后台下载资源。</p><p v-if="error" class="notice danger-notice">{{error}}</p><div class="settings-grid"><section class="state-card"><h2>默认行为</h2><p>扫描：{{settings?.scan_mode}}</p><p>分析：{{settings?.analysis_preset}}</p><p>不确定项：{{settings?.uncertain_action}}</p></section><section class="state-card"><h2>隐私与预算</h2><p>文件名默认外发：{{settings?.privacy.allow_basename?'允许':'不允许'}}</p><p>精确位置：{{settings?.privacy.allow_precise_location?'允许':'不允许'}}</p><p>调用上限：{{settings?.task_budget.max_calls}}</p><p>费用：{{settings?.task_budget.max_cost_micros==null?'未知（不显示 0 元）':settings.task_budget.max_cost_micros}}</p></section><section class="state-card components-card"><h2>资源组件</h2><div v-for="item in components" :key="String(item.component_type)"><b>{{item.component_type}}</b><span>{{item.status}} · {{item.version}}</span></div></section><section class="state-card"><h2>诊断与关于</h2><p>Guixu 0.1.0 dev · SQLite 本地数据 · Windows 用户级凭据。</p><p>缓存、历史与操作日志分层保存；清理缓存不会删除操作日志。诊断方法见用户手册。</p></section></div></section></template>
