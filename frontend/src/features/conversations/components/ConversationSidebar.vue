<script setup lang="ts">
import { confirmAction, promptAction } from '../../../components/dialogState'
import { computed, onMounted, ref } from 'vue'
import { Archive, ChevronLeft, ChevronRight, Clock3, FileClock, MoreHorizontal, Plus, Search, Settings2, Trash2 } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import { chooseSource } from '../../../services/api'
import { useConversationStore } from '../store'

const router = useRouter()
const route = useRoute()
const store = useConversationStore()
const query = ref('')
const menuId = ref('')
const collapsed = ref(false)
const busy = ref(false)

const filtered = computed(() => store.conversations.filter(item => item.title.toLowerCase().includes(query.value.trim().toLowerCase())))
const activityDate = (item: typeof store.conversations[number]) => item.last_message_at || item.updated_at || item.created_at
const today = computed(() => filtered.value.filter(item => new Date(activityDate(item)).toDateString() === new Date().toDateString()))
const yesterday = computed(() => filtered.value.filter(item => isYesterday(activityDate(item))))
const earlier = computed(() => filtered.value.filter(item => !today.value.includes(item) && !yesterday.value.includes(item)))

function isWithin(value: string, days: number) {
  const date = new Date(value).getTime()
  return Number.isFinite(date) && Date.now() - date < days * 86_400_000
}
function isYesterday(value: string) {
  const now = new Date(); const date = new Date(value)
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1).getTime()
  const end = start + 86_400_000
  return date.getTime() >= start && date.getTime() < end
}
function timeLabel(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  return isWithin(value, 1) ? date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}
function select(id: string) {
  menuId.value = ''
  router.push(`/conversations/${id}`)
}
async function create() {
  if (busy.value) return
  busy.value = true
  try {
    const grant = await chooseSource()
    if (grant.cancelled || !grant.grant_id) return
    const conversation = await store.createConversation(grant.grant_id)
    if (conversation) await router.push(`/conversations/${conversation.id}`)
  } finally { busy.value = false }
}
async function rename(id: string, title: string) {
  const next = (await promptAction('重命名对话', title))?.trim()
  menuId.value = ''
  if (next) await store.renameConversation(id, next)
}
async function remove(id: string, title: string) {
  menuId.value = ''
  if (!await confirmAction(`只删除“${title}”这条归序会话记录，不会删除或移动磁盘上的文件。是否继续？`)) return
  await store.deleteConversation(id)
  if (route.params.id === id) await router.push('/')
}
function isActive(id: string) { return route.params.id === id || store.currentConversation?.id === id }

onMounted(async () => {
  if (import.meta.env.DEV && route.path === '/__ui-review') return
  await store.loadConversations()
  await store.loadModels()
})
</script>

<template>
  <aside @keydown.esc="menuId = ''" class="conversation-sidebar" :class="{ 'is-collapsed': collapsed }" aria-label="对话导航">
    <div class="sidebar-brand-row">
      <RouterLink class="sidebar-brand" to="/" aria-label="归序工作台">
        <span class="brand-symbol"><Archive :size="18" /></span>
        <span v-if="!collapsed"><strong>归序</strong><small>Guixu</small></span>
      </RouterLink>
      <button class="sidebar-collapse" type="button" :aria-label="collapsed ? '展开侧栏' : '收起侧栏'" @click="collapsed = !collapsed">
        <ChevronRight v-if="collapsed" :size="16" /><ChevronLeft v-else :size="16" />
      </button>
    </div>

    <button class="new-conversation-button" type="button" aria-label="新建对话" :disabled="busy" @click="create">
      <Plus :size="18" /><span v-if="!collapsed">新建对话</span>
    </button>

    <label v-if="!collapsed" class="conversation-search">
      <Search :size="16" aria-hidden="true" />
      <span class="sr-only">搜索对话</span>
      <input v-model="query" type="search" placeholder="搜索对话…" />
    </label>

    <div v-if="!collapsed" class="conversation-list" aria-live="polite">
      <div v-if="store.loadingConversations" class="conversation-skeleton" aria-label="正在加载对话">
        <span v-for="n in 4" :key="n" class="skeleton-line" />
      </div>
      <p v-else-if="store.error && !store.conversations.length" class="sidebar-error">{{ store.error }}</p>
      <template v-else>
        <section v-for="group in [{ title: '今天', items: today }, { title: '昨天', items: yesterday }, { title: '更早', items: earlier }]" :key="group.title" v-show="group.items.length" class="conversation-group">
          <h2>{{ group.title }}</h2>
          <div v-for="item in group.items" :key="item.id" class="conversation-item" :class="{ active: isActive(item.id) }">
            <button type="button" class="conversation-select" :title="item.title" @click="select(item.id)">
            <span class="conversation-item-icon"><FileClock :size="15" /></span>
            <span class="conversation-item-copy"><strong>{{ item.title }}</strong><small>{{ item.status === 'ARCHIVED' ? '已归档' : '整理会话' }}</small></span>
            <time>{{ timeLabel(item.last_message_at || item.updated_at) }}</time>
            </button><span class="conversation-item-menu">
              <button type="button" class="menu-anchor" :aria-label="`${item.title} 更多操作`" @click.stop="menuId = menuId === item.id ? '' : item.id" @keydown.enter.stop="menuId = menuId === item.id ? '' : item.id"><MoreHorizontal :size="16" /></button>
              <span v-if="menuId === item.id" class="conversation-menu" @click.stop>
                <button type="button" @click="rename(item.id, item.title)">重命名</button>
                <button type="button" class="danger-text" @click="remove(item.id, item.title)"><Trash2 :size="14" />删除对话</button>
              </span>
            </span>
          </div>
        </section>
        <p v-if="!filtered.length" class="sidebar-empty">还没有对话记录</p>
      </template>
    </div>

    <nav class="sidebar-secondary" aria-label="其他入口">
      <RouterLink to="/trash" aria-label="最近删除"><Trash2 :size="17" /><span v-if="!collapsed">最近删除</span></RouterLink>
      <RouterLink to="/history" aria-label="操作历史"><Clock3 :size="17" /><span v-if="!collapsed">操作历史</span></RouterLink>
      <RouterLink to="/models" aria-label="模型与设置"><Settings2 :size="17" /><span v-if="!collapsed">模型与设置</span></RouterLink>
    </nav>
  </aside>
</template>
