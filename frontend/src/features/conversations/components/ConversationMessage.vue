<script setup lang="ts">
import { Bot, CircleUserRound } from 'lucide-vue-next'
import type { ConversationMessage } from '../../../services/api'

defineProps<{ message: ConversationMessage }>()
function time(value: string) { return new Date(value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }
</script>

<template>
  <article class="conversation-message" :class="`message-${message.role.toLowerCase()}`">
    <div class="message-avatar" aria-hidden="true"><CircleUserRound v-if="message.role === 'USER'" :size="17" /><Bot v-else :size="17" /></div>
    <div class="message-body">
      <div class="message-meta"><strong>{{ message.role === 'USER' ? '我' : message.role === 'ASSISTANT' ? '归序' : '系统' }}</strong><time>{{ time(message.created_at) }}</time></div>
      <p>{{ message.content }}</p>
    </div>
  </article>
</template>
