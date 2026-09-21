<script setup lang="ts">
import ConversationSidebar from './features/conversations/components/ConversationSidebar.vue'
</script>

<template>
  <div class="app-shell conversation-app-shell" aria-label="归序工作台、整理记录、最近删除">
    <ConversationSidebar />
    <main class="content conversation-content"><RouterView /></main>
  </div>
</template>
