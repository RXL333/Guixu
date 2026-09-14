<script setup lang="ts">
import { Archive, BookOpen, BrainCircuit, History, ListChecks, Settings } from 'lucide-vue-next'
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar" aria-label="主导航">
      <RouterLink class="brand" to="/">
        <span class="brand-mark">序</span>
        <span><strong>归序</strong><small>GUIXU</small></span>
      </RouterLink>
      <nav>
        <RouterLink to="/"><Archive :size="19" /><span>整理工作台</span></RouterLink>
        <RouterLink to="/templates"><BookOpen :size="19" /><span>分类模板</span></RouterLink>
        <RouterLink to="/rules"><ListChecks :size="19" /><span>规则中心</span></RouterLink>
        <RouterLink to="/history"><History :size="19" /><span>任务记录</span></RouterLink>
        <RouterLink to="/models"><BrainCircuit :size="19" /><span>模型连接</span></RouterLink>
        <RouterLink to="/settings"><Settings :size="19" /><span>设置</span></RouterLink>
      </nav>
      <p class="local-badge">● 本地安全会话</p>
    </aside>
    <main class="content"><RouterView /></main>
  </div>
</template>

