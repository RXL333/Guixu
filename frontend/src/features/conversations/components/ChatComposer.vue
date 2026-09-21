<script setup lang="ts">
import { Paperclip, Send, Sparkles } from 'lucide-vue-next'
import { nextTick, ref } from 'vue'
import { useConversationStore } from '../store'

const props = defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{ sent: [] }>()
const store = useConversationStore()
const draft = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)
const sending = ref(false)

async function send() {
  if (sending.value || props.disabled || !draft.value.trim()) return
  sending.value = true
  const accepted = await store.appendMessage(draft.value)
  if (accepted) { draft.value = ''; emit('sent'); await nextTick(); textarea.value?.focus() }
  sending.value = false
}
function keydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void send() }
}
function fill(value: string) { draft.value = value; textarea.value?.focus() }
defineExpose({ fill })
</script>

<template>
  <section class="composer-shell" aria-label="整理要求输入">
    <div class="composer-reference-row">
      <span v-if="store.selectedFileIds.length" class="reference-chip">已选择 {{ store.selectedFileIds.length }} 个文件</span>
      <span v-else class="reference-placeholder">可在右侧选择文件，作为未来引用入口</span>
    </div>
    <textarea ref="textarea" v-model="draft" rows="3" :disabled="disabled || sending" aria-label="整理要求" placeholder="告诉归序你希望怎样整理这些文件……" @keydown="keydown" />
    <div class="composer-toolbar">
      <button class="composer-icon-button" type="button" aria-label="添加文件引用" disabled><Paperclip :size="18" /></button>
      <span class="composer-hint">Enter 发送，Shift + Enter 换行</span>
      <div class="composer-actions">
        <span class="composer-model"><Sparkles :size="15" />{{ store.activeModel?.name || '未选择模型' }}</span>
        <button class="send-button" type="button" :disabled="disabled || sending || !draft.trim()" aria-label="发送消息" @click="send"><Send :size="17" /></button>
      </div>
    </div>
  </section>
</template>
