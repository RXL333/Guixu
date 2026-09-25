<script setup lang="ts">
import { Paperclip, Send, Sparkles, X } from 'lucide-vue-next'
import { computed, nextTick, ref, watch } from 'vue'
import { useConversationStore } from '../store'

const props = defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{ sent: []; references: [] }>()
const store = useConversationStore()
const draft = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)
const sending = ref(false)
const selectedPreview = computed(() => store.selectedFileIds.slice(0, 3).map(id => store.files.find(file => file.file_id === id)).filter((file): file is NonNullable<typeof file> => Boolean(file)))
const basename = (path: string) => path.split(/[\\/]/).pop() || path

async function send() {
  if (sending.value || props.disabled || !draft.value.trim()) return
  sending.value = true
  const accepted = await store.appendMessage(draft.value)
  if (accepted) { draft.value = ''; emit('sent'); await nextTick(); textarea.value?.focus() }
  sending.value = false
}
async function organize() {
  if (sending.value || props.disabled || store.chatBusy) return
  sending.value = true
  const accepted = await store.startOrganization(draft.value.trim() || '开始整理')
  if (accepted) { draft.value = ''; emit('sent') }
  sending.value = false
}
function keydown(event: KeyboardEvent) {
  if (event.isComposing) return
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void send() }
}
function fill(value: string) { draft.value = value; textarea.value?.focus() }
watch(draft, async () => {
  await nextTick()
  if (textarea.value) {
    textarea.value.style.height = 'auto'
    textarea.value.style.height = `${Math.min(144, Math.max(48, textarea.value.scrollHeight))}px`
  }
})
defineExpose({ fill })
</script>

<template>
  <section class="composer-shell" aria-label="整理要求输入">
    <div class="composer-reference-row">
      <template v-if="store.selectedFileIds.length">
        <span class="reference-count">已引用 {{ store.selectedFileIds.length }} 个文件</span>
        <button v-for="file in selectedPreview" :key="file.file_id" type="button" class="reference-chip" @click="store.removeFileReference(file.file_id)">{{ basename(file.current_known_path) }} <X :size="12" /></button>
        <span v-if="store.selectedFileIds.length > 3" class="reference-more">+{{ store.selectedFileIds.length - 3 }}</span>
        <button type="button" class="reference-clear" @click="store.clearFileReferences">清空引用</button>
      </template>

    </div>
    <textarea ref="textarea" v-model="draft" rows="2" :disabled="disabled || sending || store.chatBusy" aria-label="整理要求" placeholder="先聊聊你的整理需求；说“开始整理”后生成方案……" @keydown="keydown" />
    <div class="composer-toolbar">
      <button class="composer-icon-button" type="button" aria-label="添加文件引用" :disabled="disabled" @click="emit('references')"><Paperclip :size="18" /></button>
      <span class="composer-hint">Enter 发送，Shift + Enter 换行</span>
      <div class="composer-actions">
        <span class="composer-model"><Sparkles :size="15" />{{ store.activeModel?.name || '未选择模型' }}</span>
        <button class="organize-button" type="button" :disabled="disabled || sending || store.chatBusy || !store.activeModel" @click="organize">{{ store.currentPlanVersion ? '更新整理方案' : '生成整理方案' }}</button>
        <button class="send-button" type="button" :disabled="disabled || sending || store.chatBusy || !draft.trim()" aria-label="发送消息" @click="send"><Send :size="17" /></button>
      </div>
    </div>
  </section>
</template>
