<script setup lang="ts">
import { ArrowUpRight, CheckCircle2 } from 'lucide-vue-next'
import type { ConversationExecutionRound } from '../../../services/api'

defineProps<{ round: ConversationExecutionRound }>()
</script>

<template>
  <article class="business-card execution-result-card">
    <header><span class="business-card-kicker"><CheckCircle2 :size="15" />第 {{ round.round_number }} 次整理</span><span class="execution-status">{{ round.status }}</span></header>
    <h3>{{ round.affected_file_count ? `已处理 ${round.affected_file_count} 个文件` : '整理执行记录' }}</h3>
    <p v-if="round.summary && Object.keys(round.summary).length">{{ round.summary.description || '本轮执行记录已保存。' }}</p>
    <p v-else>执行记录和安全日志已保留。</p>
    <p v-if="round.status === 'COMPLETED'" class="execution-continuation">整理完成，你可以继续告诉归序需要调整的地方。</p>
    <button class="business-card-link" type="button"><span>查看执行记录</span><ArrowUpRight :size="15" /></button>
  </article>
</template>
