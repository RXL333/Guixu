<script setup lang="ts">
import { LoaderCircle } from 'lucide-vue-next'
defineProps<{ label: string }>()
</script>
<template>
  <div class="operation-progress" role="status" aria-live="polite">
    <LoaderCircle :size="16" class="loading-spinner" /><span>{{ label }}</span>
    <div class="operation-progress-track" role="progressbar" :aria-label="label" aria-valuetext="处理中" />
  </div>
</template>
