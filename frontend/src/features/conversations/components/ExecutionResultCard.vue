<script setup lang="ts">
import { ArrowUpRight, CheckCircle2, RotateCcw } from 'lucide-vue-next'
import type { ConversationExecutionRound } from '../../../services/api'

defineProps<{ round: ConversationExecutionRound; undoBusy?: boolean }>()
const emit = defineEmits<{ undo: [round: ConversationExecutionRound]; viewHistory: [] }>()
</script>

<template>
  <article class="business-card execution-result-card">
    <header><span class="business-card-kicker"><CheckCircle2 :size="15" />{{ round.round_kind === 'UNDO' ? `第 ${round.round_number} 次操作 · 撤销` : `第 ${round.round_number} 次整理` }}</span><span class="execution-status">{{ ({ COMPLETED: '已完成', RUNNING: '正在整理', FAILED: '未完成', RECOVERY_REQUIRED: '需要检查', CANCELLED: '已取消' } as Record<string, string>)[round.status] || '等待执行' }}</span></header>
    <h3>{{ round.affected_file_count ? `已处理 ${round.affected_file_count} 个文件` : '整理执行记录' }}</h3>
    <p v-if="round.summary && Object.keys(round.summary).length">{{ round.summary.description || '本轮执行记录已保存。' }}</p>
    <p v-else>执行记录和安全日志已保留。</p>
    <p v-if="round.status === 'COMPLETED'" class="execution-continuation">整理完成，你可以继续告诉归序需要调整的地方。</p>
    <p v-if="round.undo_state === 'FULLY_UNDONE'" class="execution-continuation">这次整理已被撤销。</p>
    <p v-else-if="round.undo_state === 'PARTIALLY_UNDONE'" class="execution-continuation">部分撤销 · {{ round.undone_file_count || 0 }} / {{ round.reversible_file_count || round.affected_file_count }}</p>
    <button v-if="round.round_kind !== 'UNDO' && round.status === 'COMPLETED' && round.undo_state !== 'FULLY_UNDONE'" class="execution-undo-button" type="button" :disabled="undoBusy" @click="emit('undo', round)"><RotateCcw :size="15" />撤销</button>
    <button class="business-card-link" type="button" @click="emit('viewHistory')"><span>查看执行记录</span><ArrowUpRight :size="15" /></button>
  </article>
</template>
