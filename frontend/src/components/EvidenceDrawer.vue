<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import type { FileDetail } from '../services/api'
defineProps<{ detail: FileDetail | null }>()
const emit = defineEmits<{ close: [] }>()

function handleEscape(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
}

onMounted(() => window.addEventListener('keydown', handleEscape))
onBeforeUnmount(() => window.removeEventListener('keydown', handleEscape))
</script>
<template><aside v-if="detail" class="archive-drawer" aria-label="文件档案"><button class="drawer-close" aria-label="关闭档案" @click="emit('close')">×</button><p class="eyebrow">FILE ARCHIVE</p><h2>{{ detail.file.basename }}</h2><p v-if="detail.suggestion"><b>建议</b> {{ detail.suggestion.category_id||'待确认' }}</p><p>{{ detail.suggestion?.reason||'尚无分类建议' }}</p><p v-if="detail.profile" class="sampling-note">覆盖：{{ detail.profile.coverage.mode }}；证据 {{ detail.profile.evidence.length }} 条。高可信表示建议等级，不是准确率。</p><article v-for="e in detail.profile?.evidence||[]" :key="e.id" class="evidence-card"><strong>{{ e.kind }}</strong><small>{{ JSON.stringify(e.locator) }}</small><p>{{ e.text }}</p></article></aside></template>
