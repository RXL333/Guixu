<script setup lang="ts">
import { confirmAction } from '../components/dialogState'
import { onMounted, ref } from 'vue'
import { api, type CacheStatus, type TaskSettings } from '../services/api'
const settings = ref<TaskSettings | null>(null)
const components = ref<Array<Record<string, unknown>>>([])
const cache = ref<CacheStatus | null>(null)
const cacheBusy = ref(false)
const error = ref('')
onMounted(async () => { try { settings.value = (await api.settings()).values; components.value = await api.components(); cache.value = await api.cacheStatus() } catch (e) { error.value = String(e) } })
async function clearCache() {
  if (!await confirmAction('清除文件内容分析缓存？不会删除原文件、任务或操作历史。')) return
  cacheBusy.value = true
  try { await api.clearCache(); cache.value = await api.cacheStatus() } catch (e) { error.value = String(e) } finally { cacheBusy.value = false }
}
const sections = [{ id: 'behavior', label: '整理偏好' }, { id: 'privacy', label: '隐私与预算' }, { id: 'cache', label: '内容分析缓存' }, { id: 'about', label: '关于归序' }]
function settingLabel(value: string | undefined) {
  return ({ preserve_top_level: '保留一级目录', recursive: '包含子文件夹', current_only: '仅当前文件夹', standard: '标准', quick: '快速', fast: '快速', deep: '深入', keep_in_place: '保留原位置', review: '等待确认' } as Record<string, string>)[value || ''] || '使用默认设置'
}
</script>
<template>
  <section class="page settings-page">
    <nav class="page-nav" aria-label="设置页面"><RouterLink to="/models">模型连接</RouterLink><RouterLink to="/settings">通用设置</RouterLink></nav>
    <h1>通用设置</h1><p class="lead">整理偏好、隐私与本地资源。</p>
    <p v-if="error" class="notice danger-notice" role="alert">{{ error }}</p>
    <div class="settings-layout">
      <nav class="settings-nav" aria-label="设置分区"><a v-for="section in sections" :key="section.id" :href="`#${section.id}`">{{ section.label }}</a></nav>
      <div>
        <section id="behavior" class="settings-section"><h2>整理偏好</h2>
          <div class="settings-row"><div>扫描范围<p>新建整理时使用的默认目录范围。</p></div><span>{{ settingLabel(settings?.scan_mode) }}</span></div>
          <div class="settings-row"><div>分析强度<p>平衡内容理解的深度和耗时。</p></div><span>{{ settingLabel(settings?.analysis_preset) }}</span></div>
          <div class="settings-row"><div>无法确定分类的文件</div><span>{{ settingLabel(settings?.uncertain_action) }}</span></div>
        </section>
        <section id="privacy" class="settings-section"><h2>隐私与预算</h2>
          <div class="settings-row"><div>向模型发送文件名</div><span>{{ settings?.privacy.allow_basename ? '允许' : '默认不允许' }}</span></div>
          <div class="settings-row"><div>向模型发送精确位置</div><span>{{ settings?.privacy.allow_precise_location ? '允许' : '默认不允许' }}</span></div>
          <div class="settings-row"><div>每次整理的模型调用上限</div><span>{{ settings?.task_budget.max_calls ?? '—' }} 次</span></div>
        </section>
        <section id="cache" class="settings-section"><h2>内容分析缓存</h2>
          <div class="settings-row"><div>已保存的内容理解<p>{{ cache?.valid_count ?? 0 }} 条 · {{ ((cache?.estimated_bytes ?? 0) / 1024 / 1024).toFixed(1) }} MB</p><p>清除后会重新分析文件，不会删除原文件或操作历史。</p></div><button class="secondary-button" :disabled="cacheBusy" @click="clearCache">{{ cacheBusy ? '正在清除…' : '清除缓存' }}</button></div>
        </section>
        <section id="about" class="settings-section"><h2>关于归序</h2><p>归序 Guixu · 0.1.0 dev</p><p class="lead">对话、整理方案与操作历史保存在本机。</p>
          <details><summary>诊断与资源组件</summary><p v-if="!components.length" class="lead">尚未检测到可选资源组件。</p><div v-for="item in components" :key="String(item.component_type)" class="settings-row"><span>{{ item.component_type }}</span><span>{{ item.status }} · {{ item.version }}</span></div></details>
        </section>
      </div>
    </div>
  </section>
</template>
