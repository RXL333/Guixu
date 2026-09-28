<script setup lang="ts">
import { confirmAction, promptAction } from '../../../components/dialogState'
import { ChevronDown, Folder, MoreHorizontal, Pencil, Sparkles } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { Conversation } from '../../../services/api'
import { useConversationStore } from '../store'

const props = defineProps<{ conversation: Conversation | null }>()
const router = useRouter()
const store = useConversationStore()
const menuOpen = ref(false)
const modelOpen = ref(false)
const title = computed(() => props.conversation?.title || '新的整理会话')
const scopeName = computed(() => props.conversation?.scopes?.[0]?.display_name || '尚未绑定文件夹')
const modelBusy = ref(false)

async function toggleModelMenu() {
  modelOpen.value = !modelOpen.value
  if (modelOpen.value) await store.loadModels()
}

async function rename() {
  menuOpen.value = false
  const next = (await promptAction('重命名对话', title.value))?.trim()
  if (next && props.conversation) await store.renameConversation(props.conversation.id, next)
}
async function remove() {
  menuOpen.value = false
  if (!props.conversation) return
  if (!await confirmAction('只删除归序中的会话记录，不会删除或移动磁盘上的文件。是否继续？')) return
  await store.deleteConversation(props.conversation.id)
  await router.push('/')
}
async function selectModel(modelId: string) {
  if (modelBusy.value) return
  modelBusy.value = true
  try {
    if (await store.setConversationModel(modelId)) modelOpen.value = false
  } finally { modelBusy.value = false }
}
</script>

<template>
  <header class="conversation-header" @keydown.esc="menuOpen = false; modelOpen = false">
    <div class="conversation-heading">
      <div class="conversation-title-row">
        <h1>{{ title }}</h1>
        <button class="header-icon-button" type="button" aria-label="重命名对话" @click="rename"><Pencil :size="15" /></button>
      </div>
      <p class="conversation-scope"><Folder :size="15" /><span :title="conversation?.scopes?.[0]?.source_root || ''">{{ scopeName }}</span></p>
    </div>
    <div class="conversation-header-actions">
      <div class="model-selector" :class="{ open: modelOpen }">
        <button class="model-selector-trigger" type="button" :aria-expanded="modelOpen" @click="toggleModelMenu">
          <Sparkles :size="16" /><span>{{ store.activeModel?.name || '选择模型' }}</span><ChevronDown :size="15" />
        </button>
        <div v-if="modelOpen" class="model-selector-menu">
          <p v-if="!store.models.length">暂无已配置模型</p>
          <button v-for="model in store.models" :key="model.id" type="button" :class="{ selected: model.id === store.activeModel?.id }" :disabled="modelBusy" @click="selectModel(model.id)">
            <span>{{ model.name }}</span><small>{{ model.provider === 'qwen_local' ? '本地' : '云端' }} · {{ model.model_id }}</small>
          </button>
          <RouterLink to="/models">管理模型连接</RouterLink>
        </div>
      </div>
      <div class="header-menu-wrap">
        <button class="header-icon-button more-button" type="button" aria-label="会话更多操作" :aria-expanded="menuOpen" @click="menuOpen = !menuOpen"><MoreHorizontal :size="18" /></button>
        <div v-if="menuOpen" class="header-menu">
          <button type="button" @click="rename">重命名</button>
          <button type="button" class="danger-text" @click="remove">删除会话</button>
        </div>
      </div>
    </div>
  </header>
</template>
