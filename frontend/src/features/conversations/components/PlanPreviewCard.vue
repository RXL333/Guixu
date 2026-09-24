<script setup lang="ts">
import { ArrowUpRight, Check, ClipboardList } from 'lucide-vue-next'
import { computed } from 'vue'
import type { ConversationPlanVersion } from '../../../services/api'

const props = defineProps<{ plan: ConversationPlanVersion; current?: boolean; viewing?: boolean; executionBusy?: boolean }>()
const emit = defineEmits<{ viewHistory: [id: string]; approve: [plan: ConversationPlanVersion] }>()
const metrics = computed(() => (props.plan.change_summary?.metrics || {}) as Record<string, number>)
function lifecycleLabel() {
  if (props.current) return '当前'
  if (props.plan.status === 'APPROVED') return '已批准'
  if (props.plan.status === 'EXECUTED' || props.plan.executed_at) return '已执行'
  if (props.plan.status === 'SUPERSEDED') return '已被替代'
  return ({ DRAFT: '草稿', PROPOSED: '待确认', CANCELLED: '已取消' } as Record<string, string>)[props.plan.status] || '已保存'
}
</script>

<template>
  <article class="business-card plan-preview-card" :class="{ 'is-viewing': viewing }">
    <header><span class="business-card-kicker"><ClipboardList :size="15" />{{ plan.plan_kind === 'DELTA' ? '局部调整' : '整理方案' }} · v{{ plan.version_number }}</span><span class="plan-status">{{ lifecycleLabel() }}</span></header>
    <h3>{{ plan.summary || '未命名整理方案' }}</h3>
    <p v-if="plan.affected_file_count">影响 {{ plan.affected_file_count }} 个文件<span v-if="plan.kept_file_count">，其他 {{ plan.kept_file_count }} 个保持不变</span></p>
    <p v-else>没有需要调整的文件。</p>
    <div v-if="plan.plan_kind === 'DELTA' && metrics.affected_files" class="plan-scope-summary">
      <span>候选范围 {{ metrics.affected_files }} 个</span><span>沿用内容分析 {{ metrics.evidence_reused || 0 }} 个</span>
    </div>
    <button v-if="current && plan.status === 'PROPOSED' && plan.plan_hash" class="plan-approve-button" type="button" :disabled="executionBusy" @click="emit('approve', plan)"><Check :size="16" />{{ executionBusy ? '正在整理…' : (plan.plan_kind === 'FULL' && !plan.baseline_execution_round_id ? '确认并开始整理' : '确认执行') }}</button>
    <button class="business-card-link" type="button" @click="emit('viewHistory', plan.id)"><span>查看版本历史</span><ArrowUpRight :size="15" /></button>
  </article>
</template>
