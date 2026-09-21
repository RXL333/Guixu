<script setup lang="ts">
import { ArrowUpRight, Check, ClipboardList } from 'lucide-vue-next'
import { computed } from 'vue'
import type { ConversationPlanVersion } from '../../../services/api'

const props = defineProps<{ plan: ConversationPlanVersion; current?: boolean; viewing?: boolean; executionBusy?: boolean }>()
const emit = defineEmits<{ viewHistory: [id: string]; approve: [plan: ConversationPlanVersion] }>()
const metrics = computed(() => (props.plan.change_summary?.metrics || {}) as Record<string, number>)
const scope = computed(() => (props.plan.change_summary?.scope || {}) as Record<string, unknown>)
function lifecycleLabel() {
  if (props.current) return '当前'
  if (props.plan.status === 'APPROVED') return '已批准'
  if (props.plan.status === 'EXECUTED' || props.plan.executed_at) return '已执行'
  if (props.plan.status === 'SUPERSEDED') return '已被替代'
  return props.plan.status
}
</script>

<template>
  <article class="business-card plan-preview-card" :class="{ 'is-viewing': viewing }">
    <header><span class="business-card-kicker"><ClipboardList :size="15" />{{ plan.plan_kind === 'DELTA' ? '局部调整' : '整理方案' }} · v{{ plan.version_number }}</span><span class="plan-status">{{ lifecycleLabel() }}</span></header>
    <h3>{{ plan.summary || '未命名整理方案' }}</h3>
    <p v-if="plan.affected_file_count">影响 {{ plan.affected_file_count }} 个文件<span v-if="plan.kept_file_count">，其他 {{ plan.kept_file_count }} 个保持不变</span></p>
    <p v-else>方案已保存，等待后续接入预览详情。</p>
    <div v-if="plan.plan_kind === 'DELTA' && metrics.affected_files" class="plan-scope-summary">
      <span>候选范围 {{ metrics.affected_files }} 个</span><span>证据复用 {{ metrics.evidence_reused || 0 }}</span><span v-if="scope.scope_type">{{ scope.scope_type }}</span>
    </div>
    <button v-if="current && plan.status === 'PROPOSED' && plan.baseline_execution_round_id" class="plan-approve-button" type="button" :disabled="executionBusy" @click="emit('approve', plan)"><Check :size="16" />{{ executionBusy ? '正在执行…' : '确认执行' }}</button>
    <button class="business-card-link" type="button" @click="emit('viewHistory', plan.id)"><span>查看版本历史</span><ArrowUpRight :size="15" /></button>
  </article>
</template>
