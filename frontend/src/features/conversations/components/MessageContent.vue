<script setup lang="ts">
import { computed } from 'vue'
import { parseMarkdown } from '../markdown'
import MessageInline from './MessageInline.vue'

const props = defineProps<{ content: string }>()
const blocks = computed(() => parseMarkdown(props.content ?? ''))
</script>

<template>
  <div class="message-content">
    <template v-for="(block, index) in blocks" :key="index">
      <pre v-if="block.kind === 'code'" class="message-block-code"><code>{{ block.text }}</code></pre>
      <ol v-else-if="block.kind === 'list' && block.ordered" class="message-list">
        <li v-for="(item, itemIndex) in block.items" :key="itemIndex"><MessageInline :nodes="item" /></li>
      </ol>
      <ul v-else-if="block.kind === 'list'" class="message-list">
        <li v-for="(item, itemIndex) in block.items" :key="itemIndex"><MessageInline :nodes="item" /></li>
      </ul>
      <p v-else class="message-paragraph"><MessageInline :nodes="block.children" /></p>
    </template>
  </div>
</template>

<style scoped>
.message-content :deep(p) { margin: 0; }
.message-content :deep(p) + :deep(p),
.message-content :deep(p) + :deep(.message-list),
.message-content :deep(.message-list) + :deep(p),
.message-content :deep(.message-list) + :deep(.message-list),
.message-content :deep(.message-block-code) + :deep(*) { margin-top: 0.55em; }
.message-content :deep(.message-list) { margin: 0; padding-left: 1.35em; }
.message-content :deep(.message-list) li { margin: 0.2em 0; }
.message-content :deep(.message-inline-code) {
  padding: 0.1em 0.35em; border-radius: 4px; background: rgba(15, 23, 42, 0.08);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 0.92em;
}
.message-content :deep(.message-block-code) {
  margin: 0; padding: 0.6em 0.8em; border-radius: 8px; overflow-x: auto;
  background: rgba(15, 23, 42, 0.06);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 0.88em;
}
.message-content :deep(.message-link) { color: inherit; text-decoration: underline; }
</style>
