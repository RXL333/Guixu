<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { MoreHorizontal, RotateCcw, Trash2 } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import { api, type Task } from '../services/api'

const route=useRoute()
const items=ref<Task[]>([])
const selected=ref(new Set<string>())
const query=ref('')
const error=ref('')
const busy=ref(false)
const menu=ref('')
const deletedView=computed(()=>route.path==='/trash')
const visible=computed(()=>items.value.filter(item=>`${item.name} ${item.source_root||''} ${item.status}`.toLowerCase().includes(query.value.trim().toLowerCase())))
const allSelected=computed(()=>visible.value.length>0&&visible.value.every(item=>selected.value.has(item.id)))
const blocked=(task:Task)=>['RUNNING','PAUSE_REQUESTED','RECOVERY_REQUIRED'].includes(task.status)
function target(task:Task){return task.phase==='REPORT'?`/tasks/${task.id}/report`:['EXECUTE','UNDO'].includes(task.phase)?`/tasks/${task.id}/run`:`/tasks/${task.id}/analyze`}
async function load(){items.value=(await api.tasks(deletedView.value?'deleted':'active')).items;selected.value=new Set();menu.value=''}
function toggle(id:string){const next=new Set(selected.value);next.has(id)?next.delete(id):next.add(id);selected.value=next}
function toggleAll(){selected.value=allSelected.value?new Set():new Set(visible.value.filter(item=>deletedView.value||!blocked(item)).map(item=>item.id))}
async function remove(tasks:Task[]){
  if(!tasks.length)return
  if(tasks.some(blocked)){error.value='运行中或待恢复任务必须先安全取消并等待结束。';return}
  if(!window.confirm(`只删除归序中的 ${tasks.length} 条任务记录，不会删除或移动磁盘上的文件。是否继续？`))return
  busy.value=true;error.value=''
  try{tasks.length===1?await api.deleteTask(tasks[0].id,tasks[0].revision):await api.batchDeleteTasks(tasks.map(item=>item.id));await load()}catch(cause){error.value=String(cause)}finally{busy.value=false}
}
async function restore(tasks:Task[]){if(!tasks.length)return;busy.value=true;error.value='';try{tasks.length===1?await api.restoreTask(tasks[0].id,tasks[0].revision):await api.batchRestoreTasks(tasks.map(item=>item.id));await load()}catch(cause){error.value=String(cause)}finally{busy.value=false}}
async function rename(task:Task){const value=window.prompt('新的任务名称',task.name)?.trim();if(!value)return;busy.value=true;try{await api.renameTask(task.id,task.revision,value);await load()}catch(cause){error.value=String(cause)}finally{busy.value=false}}
async function purge(tasks:Task[]){
  if(!tasks.length)return
  if(!window.confirm('永久删除此任务记录后，部分历史信息可能无法恢复。不会删除磁盘上的文件。存在计划、操作日志或 Undo 安全依赖时，归序会阻止此次操作。是否继续？'))return
  busy.value=true;error.value='';try{tasks.length===1?await api.permanentlyDeleteTask(tasks[0].id,tasks[0].revision):await api.batchPermanentlyDeleteTasks(tasks.map(item=>item.id));await load()}catch(cause){error.value=String(cause)}finally{busy.value=false}
}
async function control(task:Task,action:'recover'|'resume'|'cancel'){busy.value=true;error.value='';try{if(action==='recover')await api.recoverTask(task.id,task.revision);else if(action==='resume')await api.resumeTask(task.id,task.revision);else await api.cancelTask(task.id,task.revision);await load()}catch(cause){error.value=String(cause)}finally{busy.value=false}}
watch(()=>route.path,()=>load().catch(cause=>{error.value=String(cause)}))
onMounted(()=>load().catch(cause=>{error.value=String(cause)}))
</script>

<template><section class="page history-page"><p class="eyebrow">LOCAL ORGANIZATION HISTORY</p><h1>{{deletedView?'最近删除':'整理记录'}}</h1>
  <p class="lead">{{deletedView?'这里只删除应用内任务记录；磁盘文件、操作日志和 Undo 安全边界不会被静默处理。':'整理记录用于查看过去的 AI 分析与文件操作；它不是新的整理入口。'}}</p>
  <p v-if="error" class="notice danger-notice">{{error}}</p>
  <div class="history-toolbar"><input v-model="query" aria-label="筛选任务" placeholder="筛选名称、目录或状态"/><button class="secondary-button" @click="toggleAll">{{allSelected?'取消选择':'选择全部当前筛选结果'}}</button><span>已选 {{selected.size}}</span><button v-if="!deletedView" class="danger-button" :disabled="!selected.size||busy" @click="remove(items.filter(item=>selected.has(item.id)))">批量删除</button><template v-else><button class="secondary-button" :disabled="!selected.size||busy" @click="restore(items.filter(item=>selected.has(item.id)))">批量恢复</button><button class="danger-button" :disabled="!selected.size||busy" @click="purge(items.filter(item=>selected.has(item.id)))">批量永久删除</button></template></div>
  <div v-if="!visible.length" class="state-card">{{deletedView?'最近删除中没有任务。':'尚无整理记录。'}}</div>
  <article v-for="item in visible" :key="item.id" class="task-row history-row">
    <input type="checkbox" :aria-label="`选择 ${item.name}`" :checked="selected.has(item.id)" :disabled="!deletedView&&blocked(item)" @change="toggle(item.id)"/>
    <RouterLink :to="target(item)"><b>{{item.name}}</b><small>{{item.source_root||'尚未扫描目录'}} · {{item.created_at}}</small><small>{{item.counters?.discovered||0}} 个文件 · {{item.model_name||'历史模型未知'}} · 最近：{{item.recent_operation||'创建任务'}}</small></RouterLink>
    <span class="task-status">{{item.status}} / {{item.phase}}</span>
    <div v-if="!deletedView" class="button-row"><button v-if="item.status==='RECOVERY_REQUIRED'" class="primary-button" :disabled="busy" @click="control(item,'recover')">核对并恢复</button><button v-if="item.status==='PAUSED'" class="secondary-button" :disabled="busy" @click="control(item,'resume')">恢复调度</button><button v-if="!['COMPLETED','COMPLETED_WITH_ISSUES','CANCELLED','FAILED'].includes(item.status)" class="secondary-button" :disabled="busy" @click="control(item,'cancel')">安全取消</button></div>
    <div class="task-menu"><button class="icon-button" :aria-label="`${item.name} 更多操作`" @click="menu=menu===item.id?'':item.id"><MoreHorizontal :size="18"/></button><div v-if="menu===item.id" class="menu-popover"><button v-if="!deletedView" @click="rename(item)">重命名</button><button v-if="!deletedView" :disabled="blocked(item)" @click="remove([item])"><Trash2 :size="15"/>删除任务</button><button v-if="deletedView" @click="restore([item])"><RotateCcw :size="15"/>恢复</button><button v-if="deletedView" class="danger-text" @click="purge([item])"><Trash2 :size="15"/>永久删除记录</button></div></div>
  </article>
</section></template>
