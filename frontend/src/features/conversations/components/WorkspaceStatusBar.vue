<script setup lang="ts">
defineProps<{ tone?: 'idle' | 'loading' | 'success' | 'error'; text: string }>()
</script>

<template>
  <div class="workspace-status" :data-tone="tone || 'idle'" role="status">
    <span class="status-dot" aria-hidden="true" />
    <span>{{ text }}</span>
  </div>
</template>
