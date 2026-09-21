<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowRight, FolderSearch, ShieldCheck } from 'lucide-vue-next'
import { api, type Task } from '../services/api'

const tasks = ref<Task[]>([])
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try { tasks.value = (await api.tasks()).items } catch (cause) { error.value = String(cause) } finally { loading.value = false }
})
</script>

<template>
  <section class="page home-page">
    <header class="hero">
      <p class="eyebrow">LOCAL-FIRST FILE ORGANIZER</p>
      <div class="hero-line">
        <div><h1>让 AI 读懂文件，再决定它们应该放在哪里。</h1><p>理解正文与画面，智能规划分类；每一步都可预览、可撤销，由你确认。</p></div>
        <span class="mode-chip"><ShieldCheck :size="16" /> 仅本机 · 只读阶段</span>
      </div>
    </header>
    <RouterLink class="source-cta" to="/tasks/new">
      <span class="folder-icon"><FolderSearch :size="30" /></span>
      <span><strong>选择一个测试文件夹</strong><small>接入 DeepSeek 或本地 Qwen，先只读理解内容并规划整理方式</small></span>
      <span class="primary-button">新建整理任务 <ArrowRight :size="17" /></span>
    </RouterLink>
    <section class="section-block">
      <div class="section-heading"><h2>最近任务</h2><span>{{ tasks.length }} 项</span></div>
      <div v-if="loading" class="state-card">正在读取本地任务记录…</div>
      <div v-else-if="error" class="state-card error-state">读取失败：{{ error }}</div>
      <div v-else-if="tasks.length === 0" class="state-card empty-state">
        <ArchiveBox /><strong>这里还没有整理记录</strong><p>首次扫描完成后，真实任务会显示在这里。</p>
      </div>
      <RouterLink v-for="task in tasks" v-else :key="task.id" class="task-row" :to="`/tasks/${task.id}/analyze`">
        <span><strong>{{ task.name }}</strong><small>{{ task.settings.scan_mode }} · {{ task.settings.operation_mode }}</small></span>
        <span class="task-status">{{ task.status }}</span>
      </RouterLink>
    </section>
  </section>
</template>

<script lang="ts">
import { Archive as ArchiveBox } from 'lucide-vue-next'
</script>
