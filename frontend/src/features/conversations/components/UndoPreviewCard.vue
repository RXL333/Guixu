<script setup lang="ts">
import { AlertTriangle, RotateCcw, ShieldCheck } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import type { ConversationUndoPlan } from '../../../services/api'

const props = defineProps<{ plan: ConversationUndoPlan; busy?: boolean }>()
const emit = defineEmits<{ confirm: []; cancel: [] }>()
const expanded = ref(false)
const visibleItems = computed(() => expanded.value ? props.plan.items : props.plan.items.slice(0, 4))
function name(path: string) { return path.split(/[\\/]/).pop() || path }
function itemLabel(status: string) {
  return ({
    READY: '可以恢复', COMPLETED: '已恢复', ALREADY_REVERSED: '已经在原位置',
    BLOCKED_MISSING: '文件不可见', BLOCKED_MODIFIED: '文件内容已变化',
    BLOCKED_EXTERNAL_MOVE: '文件后来被手动移动', BLOCKED_TARGET_CONFLICT: '原位置已被占用',
    BLOCKED_DEPENDENCY: '这个文件后来又被调整过', BLOCKED_SCOPE: '超出当前授权目录', FAILED: '恢复未完成',
  } as Record<string, string>)[status] || status
}
</script>

<template>
  <article class="undo-preview-card" :class="{ blocked: plan.status === 'BLOCKED' }">
    <header>
      <span class="undo-preview-icon"><AlertTriangle v-if="plan.status === 'BLOCKED'" :size="18" /><RotateCcw v-else :size="18" /></span>
      <div><strong>撤销第 {{ plan.summary.target_round_number }} 次整理</strong><small>{{ plan.summary.partial ? '仅恢复选中的文件' : '恢复这次整理实际移动的文件' }}</small></div>
      <span class="undo-preview-state">{{ plan.status === 'BLOCKED' ? '需要处理冲突' : '等待确认' }}</span>
    </header>
    <div class="undo-preview-metrics">
      <span><strong>{{ plan.summary.ready || 0 }}</strong> 可以恢复</span>
      <span><strong>{{ plan.summary.blocked || 0 }}</strong> 存在冲突</span>
      <span v-if="plan.summary.already_reversed"><strong>{{ plan.summary.already_reversed }}</strong> 已在原位</span>
    </div>
    <div class="undo-file-list">
      <div v-for="item in visibleItems" :key="item.id" class="undo-file-row" :data-state="item.status">
        <div><strong>{{ name(item.current_source) }}</strong><small>{{ item.operation_kind === 'COPY' ? '移入系统回收站' : `${item.current_source} → ${item.restore_target}` }}</small></div>
        <span>{{ itemLabel(item.status) }}</span>
      </div>
      <button v-if="plan.items.length > 4" type="button" class="undo-show-all" @click="expanded = !expanded">{{ expanded ? '收起' : `查看全部 ${plan.items.length} 个文件` }}</button>
    </div>
    <p class="undo-safety-note"><ShieldCheck :size="15" />确认后仍会再次检查文件内容、原位置和授权范围，不会覆盖已有文件。</p>
    <footer>
      <button type="button" class="undo-cancel" :disabled="busy" @click="emit('cancel')">取消</button>
      <button type="button" class="undo-confirm" :disabled="busy || plan.status !== 'WAITING_FOR_APPROVAL'" @click="emit('confirm')">{{ busy ? '正在核对…' : '确认撤销' }}</button>
    </footer>
  </article>
</template>
