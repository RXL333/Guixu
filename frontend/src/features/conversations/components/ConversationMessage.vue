<script setup lang="ts">
import { ref } from 'vue'
import { Bot, Check, CircleUserRound, Copy } from 'lucide-vue-next'
import MessageContent from './MessageContent.vue'
import type { ConversationMessage } from '../../../services/api'

defineProps<{ message: ConversationMessage }>()
const emit = defineEmits<{ references: [fileIds: string[]] }>()
const copyState = ref<'idle' | 'copied' | 'failed'>('idle')
async function copyMessage(content: string) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(content)
    } else {
      const input = document.createElement('textarea')
      input.value = content
      input.style.position = 'fixed'
      input.style.opacity = '0'
      document.body.appendChild(input)
      try {
        input.select()
        if (!document.execCommand('copy')) throw new Error('Clipboard unavailable')
      } finally {
        input.remove()
      }
    }
    copyState.value = 'copied'
  } catch {
    copyState.value = 'failed'
  }
  window.setTimeout(() => { copyState.value = 'idle' }, 2000)
}
function time(value: string) { return new Date(value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }
</script>

<template>
  <article class="conversation-message" :class="`message-${message.role.toLowerCase()}`">
    <div class="message-avatar" aria-hidden="true"><CircleUserRound v-if="message.role === 'USER'" :size="17" /><Bot v-else :size="17" /></div>
    <div class="message-body">
      <div class="message-meta"><strong>{{ message.role === 'USER' ? '我' : message.role === 'ASSISTANT' ? '归序' : '系统' }}</strong><time>{{ time(message.created_at) }}</time></div>
      <MessageContent :content="message.content" />
      <button v-if="message.referenced_file_ids?.length" type="button" class="message-reference-badge" @click="emit('references', message.referenced_file_ids)">
        引用 · {{ message.referenced_file_ids.length }} 个文件
        <span v-if="message.file_references?.some(item => item.state === 'MISSING')"> · 含不可见文件</span>
      </button>
      <button type="button" class="message-copy-button" :aria-label="copyState === 'copied' ? '已复制对话' : copyState === 'failed' ? '复制失败，请重试' : '复制对话'" :title="copyState === 'copied' ? '已复制' : copyState === 'failed' ? '复制失败，请重试' : '复制对话'" @click="copyMessage(message.content)">
        <Check v-if="copyState === 'copied'" :size="15" /><Copy v-else :size="15" />
        <span v-if="copyState !== 'idle'">{{ copyState === 'copied' ? '已复制' : '复制失败' }}</span>
      </button>
    </div>
  </article>
</template>
