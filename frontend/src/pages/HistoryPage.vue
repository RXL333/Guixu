<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type Task } from '../services/api'

const items = ref<Task[]>([])
const error = ref('')
const busy = ref('')
async function load() { items.value = (await api.tasks()).items }
function target(task: Task) { return task.phase === 'REPORT' ? `/tasks/${task.id}/report` : ['EXECUTE','UNDO'].includes(task.phase) ? `/tasks/${task.id}/run` : `/tasks/${task.id}/analyze` }
async function control(task: Task, action: 'recover'|'resume'|'cancel') {
  busy.value = task.id; error.value = ''
  try {
    if (action === 'recover') await api.recoverTask(task.id, task.revision)
    else if (action === 'resume') await api.resumeTask(task.id, task.revision)
    else await api.cancelTask(task.id, task.revision)
    await load()
  } catch (cause) { error.value = String(cause) } finally { busy.value = '' }
}
onMounted(() => load().catch(cause => { error.value = String(cause) }))
</script>
<template><section class="page"><p class="eyebrow">LOCAL TASK HISTORY</p><h1>任务记录</h1><p class="lead">历史状态保存在本机；未闭合任务先核对磁盘事实，不会盲目重跑移动。</p><p v-if="error" class="notice danger-notice">{{error}}</p><div v-if="!items.length" class="state-card">尚无任务记录。</div><article v-for="item in items" :key="item.id" class="task-row"><RouterLink :to="target(item)"><b>{{item.name}}</b><small>{{item.settings.scan_mode}} · {{item.settings.operation_mode}} · {{item.updated_at}}</small></RouterLink><span class="task-status">{{item.status}} / {{item.phase}}</span><div class="button-row"><button v-if="item.status==='RECOVERY_REQUIRED'" class="primary-button" :disabled="busy===item.id" @click="control(item,'recover')">核对并恢复</button><button v-if="item.status==='PAUSED'" class="secondary-button" :disabled="busy===item.id" @click="control(item,'resume')">恢复调度</button><button v-if="!['COMPLETED','COMPLETED_WITH_ISSUES','CANCELLED','FAILED'].includes(item.status)" class="secondary-button" :disabled="busy===item.id" @click="control(item,'cancel')">安全取消</button></div></article></section></template>
